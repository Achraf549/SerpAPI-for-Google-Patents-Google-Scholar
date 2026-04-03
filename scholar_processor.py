"""
Google Scholar processing pipeline: deduplication, enrichment, classification.
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime

from config import (
    DOMAIN_RULES, DOMAIN_FALLBACK,
    RELEVANCE_KEYWORDS_STRONG, ASSIGNEE_PATTERNS,
    SCHOLAR_PILLAR_MYOPIA, SCHOLAR_PILLAR_GLASSES, SCHOLAR_PILLAR_NIR,
)
from patent_processor import normalize_assignee

logger = logging.getLogger(__name__)


@dataclass
class ScholarRow:
    """A single row in the Google Scholar sheet."""
    timing: datetime | str | None  # Exact date if resolved via CrossRef, else year string
    authors: str
    domain: str
    description: str
    region: str
    source: str
    confidence: str
    confidence_rationale: str
    descriptors: str
    # Internal tracking
    title_raw: str = ""
    query_sources: list = field(default_factory=list)


# ── Region inference from publication info ────────────────────────────────────

REGION_KEYWORDS = {
    "China": ["china", "chinese", "beijing", "shanghai", "shenzhen",
              "guangzhou", "wuhan", "nanjing", "hangzhou", "chongqing",
              "zhongshan", "tianjin", "hong kong"],
    "Europe": ["europe", "european", "germany", "france", "uk",
               "united kingdom", "spain", "italy", "netherlands",
               "sweden", "denmark", "switzerland", "ireland"],
    "North America": ["united states", "u.s.", "usa", "canada",
                      "american", "boston", "new york", "houston",
                      "california", "ohio", "maryland"],
    "Asia": ["japan", "korea", "singapore", "taiwan", "india",
             "australia", "thailand", "malaysia"],
    "MENA": ["middle east", "saudi", "uae", "israel", "iran", "turkey"],
}


def _infer_region(result: dict) -> str:
    """Infer region from publication info and snippet."""
    text = (
        (result.get("publication_info", {}).get("summary", "") or "") + " " +
        (result.get("snippet", "") or "") + " " +
        (result.get("title", "") or "")
    ).lower()

    for region, keywords in REGION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return region
    return "Global"


# ── Domain classification ─────────────────────────────────────────────────────

SCHOLAR_DOMAIN_RULES = [
    (["clinical trial", "randomized", "randomised", "rct", "phase i",
      "phase ii", "phase iii", "efficacy", "cohort study",
      "meta-analysis", "systematic review"], "Clinical Trial / Review"),
    (["near-infrared", "nir", "photobiomodulation", "pbm", "red light",
      "rlrl", "light therapy", "retinal stimulation", "low-level light",
      "infrared"], "NIR/PBM"),
    (["myopia", "myopic", "defocus", "axial elongation", "myopia control",
      "spectacle lens", "dims", "halt", "lenslet"], "Myopia Control"),
    (["waveguide", "holographic", "micro-led", "micro-oled",
      "augmented reality", "ar display", "ar glasses"], "Optics"),
    (["smart glasses", "wearable", "eyewear"], "Wearable"),
    (["therapeutic", "medical", "ophthalmic", "retina", "eye health",
      "ocular", "choroid"], "Therapeutic / Ophthalmic"),
]


def _classify_domain(result: dict) -> str:
    text = (
        (result.get("title", "") or "") + " " +
        (result.get("snippet", "") or "")
    ).lower()
    for keywords, domain_name in SCHOLAR_DOMAIN_RULES:
        if any(kw in text for kw in keywords):
            return domain_name
    return "Scientific Paper"


# ── Relevance filter ──────────────────────────────────────────────────────────

def _is_relevant(result: dict) -> bool:
    """Two-pillar relevance filter: paper must touch at least 2 of the 3 pillars:
    Pillar 1: Myopia, Pillar 2: Smart/intelligent glasses, Pillar 3: NIR/light therapy.
    """
    text = (
        (result.get("title", "") or "") + " " +
        (result.get("snippet", "") or "")
    ).lower()

    has_myopia = any(kw in text for kw in SCHOLAR_PILLAR_MYOPIA)
    has_glasses = any(kw in text for kw in SCHOLAR_PILLAR_GLASSES)
    has_nir = any(kw in text for kw in SCHOLAR_PILLAR_NIR)

    pillars_hit = sum([has_myopia, has_glasses, has_nir])
    return pillars_hit >= 2


# ── Author / affiliation extraction ──────────────────────────────────────────

def _extract_authors(result: dict) -> str:
    """Extract author names from publication_info."""
    pub_info = result.get("publication_info", {})
    summary = pub_info.get("summary", "") or ""
    # Summary typically looks like: "A Smith, B Jones - Journal Name, 2025 - publisher.com"
    # Take the part before the first " - "
    if " - " in summary:
        authors_part = summary.split(" - ")[0].strip()
        return authors_part
    return summary[:100] if summary else ""


def _extract_year(result: dict) -> str:
    """Extract publication year from result. Returns year string (e.g. '2025')
    since Google Scholar only provides year, not exact date."""
    pub_info = result.get("publication_info", {})
    summary = pub_info.get("summary", "") or ""
    match = re.search(r"\b(202[5-6])\b", summary)
    if match:
        return match.group(1)

    snippet = result.get("snippet", "") or ""
    match = re.search(r"\b(202[5-6])\b", snippet)
    if match:
        return match.group(1)

    return ""


# ── Confidence assessment ─────────────────────────────────────────────────────

HIGH_QUALITY_SOURCES = [
    "nature", "lancet", "nejm", "bmj", "jama", "science",
    "ophthalmology", "iovs", "bjo", "arvo", "ieee",
    "acm", "springer", "wiley", "elsevier", "frontiers",
    "plos", "cell", "acs.org", "pnas",
]


def _assess_confidence(result: dict, query_count: int) -> tuple[str, str]:
    pub_info = result.get("publication_info", {}).get("summary", "").lower()
    link = (result.get("link", "") or "").lower()

    is_high_quality = any(s in pub_info or s in link for s in HIGH_QUALITY_SOURCES)

    if query_count >= 2 and is_high_quality:
        return ("High", f"Paper found across {query_count} queries; published in a high-impact journal.")
    elif is_high_quality:
        return ("High", "Published in a high-impact peer-reviewed journal.")
    elif query_count >= 2:
        return ("Medium", f"Paper found across {query_count} queries; journal impact not confirmed.")
    else:
        return ("Medium", "Single source; peer-review status not independently confirmed.")


# ── Description builder ───────────────────────────────────────────────────────

def _build_description(result: dict) -> str:
    """Build presentation-ready description."""
    title = (result.get("title", "") or "").strip()
    snippet = (result.get("snippet", "") or "").strip()
    snippet = re.sub(r"\s+", " ", snippet)

    pub_info = result.get("publication_info", {}).get("summary", "") or ""

    parts = []
    if title:
        parts.append(f'"{title}"')
    if pub_info:
        # Extract journal part (after authors, before year)
        journal_part = pub_info.split(" - ")[-1].strip() if " - " in pub_info else ""
        if journal_part:
            parts.append(f"published in {journal_part}")
    if snippet:
        parts.append(f"— {snippet}")

    desc = " ".join(parts)
    if not desc.endswith("."):
        desc += "."
    return desc


# ── Build descriptors ─────────────────────────────────────────────────────────

def _build_descriptors(result: dict) -> str:
    parts = []
    query_config = result.get("_query_config", {})
    hint = query_config.get("descriptor_hint", "")
    if hint:
        parts.append(f"Technology: {hint}")
    parts.append("Scientific Papers: Google Scholar")
    return " | ".join(parts)


# ── Main processing ──────────────────────────────────────────────────────────

def deduplicate_scholar(raw_results: list[dict]) -> list[dict]:
    """Deduplicate by title (lowercased), merging query metadata."""
    seen = {}
    for r in raw_results:
        title = (r.get("title", "") or "").lower().strip()
        if not title:
            continue
        if title in seen:
            seen[title].setdefault("_all_queries", []).append(r.get("_query_q", ""))
        else:
            r["_all_queries"] = [r.get("_query_q", "")]
            seen[title] = r

    deduped = list(seen.values())
    logger.info(f"Scholar dedup: {len(raw_results)} -> {len(deduped)} unique papers")
    return deduped


def process_scholar(raw_results: list[dict], date_map: dict = None) -> list[ScholarRow]:
    """Full processing pipeline for Google Scholar results.
    date_map: optional {title_lower: "YYYY-MM-DD"} from CrossRef enrichment.
    """
    deduped = deduplicate_scholar(raw_results)

    # Relevance filter
    relevant = [r for r in deduped if _is_relevant(r)]
    logger.info(f"Scholar relevance filter: {len(deduped)} -> {len(relevant)} "
                f"({len(deduped) - len(relevant)} off-topic removed)")

    date_map = date_map or {}

    rows = []
    for result in relevant:
        query_count = len(result.get("_all_queries", []))

        # Try exact date from CrossRef enrichment, fall back to year
        title_key = (result.get("title", "") or "").strip().lower()
        exact_date_str = date_map.get(title_key)
        if exact_date_str:
            try:
                timing = datetime.strptime(exact_date_str[:10], "%Y-%m-%d")
            except ValueError:
                timing = _extract_year(result)
        else:
            timing = _extract_year(result)
        authors = _extract_authors(result)
        domain = _classify_domain(result)
        description = _build_description(result)
        region = _infer_region(result)
        source = result.get("link", "") or ""
        confidence, rationale = _assess_confidence(result, query_count)
        descriptors = _build_descriptors(result)

        row = ScholarRow(
            timing=timing,
            authors=authors,
            domain=domain,
            description=description,
            region=region,
            source=source,
            confidence=confidence,
            confidence_rationale=rationale,
            descriptors=descriptors,
            title_raw=result.get("title", "") or "",
            query_sources=result.get("_all_queries", []),
        )
        rows.append(row)

    # Sort by timing descending — handle both datetime and string types
    def sort_key(r):
        if isinstance(r.timing, datetime):
            return r.timing.isoformat()
        return str(r.timing or "0000")
    rows.sort(key=sort_key, reverse=True)

    # Log stats
    domain_counts = {}
    region_counts = {}
    for r in rows:
        domain_counts[r.domain] = domain_counts.get(r.domain, 0) + 1
        region_counts[r.region] = region_counts.get(r.region, 0) + 1

    logger.info(f"Processed {len(rows)} scholar rows")
    logger.info(f"Domain distribution: {domain_counts}")
    logger.info(f"Region distribution: {region_counts}")

    return rows
