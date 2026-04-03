"""
Patent processing pipeline: deduplication, enrichment, classification.
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime

from config import (
    COUNTRY_TO_REGION, DOMAIN_RULES, DOMAIN_FALLBACK,
    ENTITY_TO_PARENT, PARENT_GROUPS, RELEVANCE_KEYWORDS_STRONG,
    ASSIGNEE_PATTERNS,
)

logger = logging.getLogger(__name__)


@dataclass
class PatentRow:
    """A single row in the Patent Activity sheet."""
    timing: datetime | None
    domain: str
    description: str
    region: str
    source: str
    confidence: str
    confidence_rationale: str
    descriptors: str
    # Internal tracking (not written to Excel)
    patent_id: str = ""
    assignee_raw: str = ""
    query_sources: list = field(default_factory=list)


def deduplicate_patents(raw_results: list[dict]) -> list[dict]:
    """Deduplicate by publication_number, merging query metadata."""
    seen = {}
    for r in raw_results:
        key = r.get("publication_number") or r.get("patent_id", "")
        if not key:
            continue
        if key in seen:
            # Merge query sources
            existing = seen[key]
            existing_qs = existing.setdefault("_all_queries", [])
            existing_qs.append(r.get("_query_q", ""))
        else:
            r["_all_queries"] = [r.get("_query_q", "")]
            seen[key] = r

    deduped = list(seen.values())
    logger.info(f"Deduplication: {len(raw_results)} → {len(deduped)} unique patents")
    return deduped


def extract_country_code(patent: dict) -> str:
    """Extract country code from publication_number (e.g., 'US20260012345A1' → 'US')."""
    pub_num = patent.get("publication_number", "") or patent.get("patent_id", "")
    match = re.match(r"^([A-Z]{2})", pub_num)
    return match.group(1) if match else ""


def map_region(patent: dict) -> str:
    """Map patent jurisdiction to geographic region."""
    code = extract_country_code(patent)
    return COUNTRY_TO_REGION.get(code, "Global")


def classify_domain(patent: dict) -> str:
    """Classify patent into a domain based on title + snippet keywords."""
    text = (
        (patent.get("title", "") or "") + " " +
        (patent.get("snippet", "") or "")
    ).lower()

    for keywords, domain_name in DOMAIN_RULES:
        if any(kw in text for kw in keywords):
            return domain_name
    return DOMAIN_FALLBACK


def identify_assignee_parent(patent: dict) -> str | None:
    """Match assignee to a parent group. Returns parent name or None."""
    assignee = (patent.get("assignee", "") or "").lower()
    if not assignee:
        return None

    for entity_lower, parent in ENTITY_TO_PARENT.items():
        if entity_lower in assignee:
            return parent

    return None


def _clean_title(title: str) -> str:
    """Clean patent title for presentation."""
    if not title:
        return "an undisclosed technology"
    # Remove trailing legal boilerplate
    title = re.sub(r"\s*and\s+method(?:s)?\s+thereof\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*and\s+system(?:s)?\s+thereof\s*$", "", title, flags=re.IGNORECASE)
    # Capitalize first letter
    title = title.strip()
    if title:
        title = title[0].upper() + title[1:]
    return title


def _clean_snippet(snippet: str) -> str:
    """Clean snippet whitespace, keep full text."""
    if not snippet:
        return ""
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if snippet and not snippet.endswith("."):
        snippet += "."
    return snippet


def build_description(patent: dict) -> str:
    """Build a presentation-ready description sentence."""
    assignee = patent.get("assignee", "") or ""
    pub_number = patent.get("publication_number", "") or patent.get("patent_id", "")
    title = _clean_title(patent.get("title", ""))
    snippet = _clean_snippet(patent.get("snippet", ""))

    # Determine filing action
    grant_date = patent.get("grant_date")
    filing_date = patent.get("filing_date")
    if grant_date:
        action = "was granted"
    elif filing_date:
        action = "filed"
    else:
        action = "published"

    # Build sentence
    if assignee:
        desc = f"{assignee} {action} a patent ({pub_number}) titled '{title}'"
    else:
        desc = f"A patent {action} ({pub_number}) titled '{title}'"

    if snippet:
        desc += f", describing {snippet[0].lower() + snippet[1:] if snippet else snippet}"

    # Ensure ends with period
    if not desc.endswith("."):
        desc += "."

    return desc


def assess_confidence(patent: dict) -> tuple[str, str]:
    """Assess confidence level and provide rationale."""
    query_count = len(patent.get("_all_queries", []))
    grant_date = patent.get("grant_date")

    if query_count >= 2:
        return (
            "High",
            f"Patent appeared across {query_count} independent search queries on Google Patents, indicating strong relevance to the research scope."
        )
    elif grant_date:
        return (
            "High",
            "Granted patent verified on Google Patents with confirmed grant status."
        )
    else:
        status = patent.get("status", "")
        if "application" in str(status).lower():
            return (
                "Medium",
                "Single patent application identified via Google Patents; not yet granted."
            )
        return (
            "Medium",
            "Single source (Google Patents). No independent corroboration."
        )


def build_descriptors(patent: dict) -> str:
    """Build the Kearney descriptor string."""
    parts = []

    # Companies
    parent = identify_assignee_parent(patent)
    if parent:
        entities = PARENT_GROUPS.get(parent, [])
        assignee_raw = patent.get("assignee", "") or ""
        matched = [e for e in entities if e.lower() in assignee_raw.lower()]
        if matched:
            parts.append(f"Companies: {', '.join(matched)}")
        else:
            parts.append(f"Companies: {parent}")

    # Technology descriptors from query hints
    query_config = patent.get("_query_config", {})
    hint = query_config.get("descriptor_hint", "")
    if hint:
        parts.append(f"Technology: {hint}")

    # Always include patent DB
    parts.append("Patent DB: Google Patents")

    return " | ".join(parts)


def select_timing(patent: dict) -> datetime | None:
    """Select the best date for the Timing column."""
    date_fields = ["publication_date", "grant_date", "filing_date", "priority_date"]
    formats = ["%Y-%m-%d", "%b %d, %Y", "%Y%m%d", "%d %b %Y", "%m/%d/%Y"]

    for field_name in date_fields:
        raw = patent.get(field_name)
        if not raw:
            continue
        if isinstance(raw, datetime):
            return raw
        raw = str(raw).strip()
        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue

    logger.warning(f"No parseable date for patent {patent.get('publication_number', '?')}")
    return None


# Normalize all assignee name variants to clean English names
ASSIGNEE_NORMALIZATION = {
    # Apple
    "apple inc.": "Apple Inc.",
    "apple inc": "Apple Inc.",
    "apple, inc.": "Apple Inc.",
    "苹果公司": "Apple Inc.",
    "アップル インコーポレイテッド": "Apple Inc.",
    "애플 인크.": "Apple Inc.",
    # Meta
    "meta platforms technologies, llc": "Meta Platforms Technologies",
    "meta platforms technologies, llc": "Meta Platforms Technologies",
    "meta platform technologies, llc": "Meta Platforms Technologies",
    "meta platforms, inc.": "Meta Platforms, Inc.",
    "元平台技术有限公司": "Meta Platforms Technologies",
    # Samsung
    "samsung electronics co., ltd.": "Samsung Electronics",
    "samsung display co., ltd.": "Samsung Display",
    "samsung bioepis co., ltd.": "Samsung Bioepis",
    "삼성전자주식회사": "Samsung Electronics",
    "삼성전자 주식회사": "Samsung Electronics",
    "삼성디스플레이 주식회사": "Samsung Display",
    "三星电子株式会社": "Samsung Electronics",
    "三星显示有限公司": "Samsung Display",
    "三星电子（中国）研发中心": "Samsung Electronics (China R&D)",
    # EssilorLuxottica
    "essilor international": "Essilor International (EssilorLuxottica)",
    "依视路国际公司": "Essilor International (EssilorLuxottica)",
    "에씰로 앙터나시오날": "Essilor International (EssilorLuxottica)",
    # Google / Alphabet
    "verily life sciences llc": "Verily Life Sciences (Alphabet)",
    "verily life sciences, llc": "Verily Life Sciences (Alphabet)",
    "google llc": "Google (Alphabet)",
    "google, llc": "Google (Alphabet)",
    # TCL
    "惠州tcl云创科技有限公司": "TCL",
    "tcl驭新智行科技(宁波)有限公司": "TCL",
    "惠州tcl移动通信有限公司": "TCL",
    "huizhou tcl mobile communication co., ltd.": "TCL",
    "tcl华星光电技术有限公司": "TCL CSOT (TCL)",
    # Facebook (legacy filings now under Meta)
    "facebook technologies, llc": "Meta (Reality Labs)",
    "facebook, inc.": "Meta",
}


def normalize_assignee(assignee: str) -> str:
    """Normalize assignee name to clean English form."""
    if not assignee:
        return ""
    key = assignee.lower().strip()
    return ASSIGNEE_NORMALIZATION.get(key, assignee)


def _is_target_company(patent: dict) -> tuple[bool, str]:
    """Check if patent assignee matches one of the target companies.
    Returns (is_match, parent_group_name).
    """
    assignee = (patent.get("assignee", "") or "").lower()
    if not assignee:
        return False, ""

    for parent, patterns in ASSIGNEE_PATTERNS.items():
        for pattern in patterns:
            if pattern in assignee:
                return True, parent
    return False, ""


def _is_relevant(patent: dict) -> bool:
    """Relevance check: at least one STRONG keyword in title or snippet.
    Since we already filter by target company, this is a lighter sanity check.
    """
    text = (
        (patent.get("title", "") or "") + " " +
        (patent.get("snippet", "") or "")
    ).lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS_STRONG)


def process_all(raw_results: list[dict]) -> list[PatentRow]:
    """Full processing pipeline: dedup → relevance filter → enrich → classify → sort."""
    deduped = deduplicate_patents(raw_results)

    # Company filter: only keep patents from the 19 target entities
    target_company_patents = []
    for p in deduped:
        is_target, parent = _is_target_company(p)
        if is_target:
            p["_matched_parent"] = parent
            target_company_patents.append(p)
    logger.info(f"Company filter: {len(deduped)} -> {len(target_company_patents)} "
                f"({len(deduped) - len(target_company_patents)} non-target companies removed)")

    # Relevance filter: topic must be related to myopia / NIR / smart glasses
    relevant = [p for p in target_company_patents if _is_relevant(p)]
    filtered_out = len(target_company_patents) - len(relevant)
    logger.info(f"Relevance filter: {len(target_company_patents)} -> {len(relevant)} "
                f"({filtered_out} off-topic patents removed)")

    rows = []
    for patent in relevant:
        timing = select_timing(patent)
        domain = classify_domain(patent)
        description = build_description(patent)
        region = map_region(patent)
        source = patent.get("patent_link", "") or ""
        confidence, rationale = assess_confidence(patent)
        descriptors = build_descriptors(patent)

        row = PatentRow(
            timing=timing,
            domain=domain,
            description=description,
            region=region,
            source=source,
            confidence=confidence,
            confidence_rationale=rationale,
            descriptors=descriptors,
            patent_id=patent.get("publication_number", "") or patent.get("patent_id", ""),
            assignee_raw=normalize_assignee(patent.get("assignee", "") or ""),
            query_sources=patent.get("_all_queries", []),
        )
        rows.append(row)

    # Sort by timing descending (newest first), None dates at end
    rows.sort(key=lambda r: r.timing or datetime.min, reverse=True)

    # Log distribution stats
    domain_counts = {}
    region_counts = {}
    for r in rows:
        domain_counts[r.domain] = domain_counts.get(r.domain, 0) + 1
        region_counts[r.region] = region_counts.get(r.region, 0) + 1

    logger.info(f"Processed {len(rows)} patent rows")
    logger.info(f"Domain distribution: {domain_counts}")
    logger.info(f"Region distribution: {region_counts}")

    return rows
