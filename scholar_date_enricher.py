"""
Enrich Google Scholar results with exact publication dates via CrossRef API.
Two-step approach: 1) DOI from URL → CrossRef, 2) Title search → CrossRef.
"""

import re
import time
import logging
import requests

logger = logging.getLogger(__name__)

CROSSREF_BASE = "https://api.crossref.org/works"
CROSSREF_HEADERS = {"User-Agent": "PatentsExtractor/1.0 (mailto:research@example.com)"}


def _extract_doi(result: dict) -> str | None:
    """Extract DOI from article URL."""
    link = result.get("link", "") or ""
    m = re.search(r"(10\.\d{4,}/[^\s\"<>]+)", link)
    if m:
        doi = m.group(1).rstrip("/")
        # Clean trailing URL fragments
        doi = re.sub(r"/full$", "", doi)
        doi = re.sub(r"/abstract$", "", doi)
        doi = re.sub(r"\?.*$", "", doi)
        return doi
    return None


def _crossref_by_doi(doi: str) -> str | None:
    """Get publication date from CrossRef by DOI."""
    try:
        resp = requests.get(f"{CROSSREF_BASE}/{doi}", timeout=15, headers=CROSSREF_HEADERS)
        if resp.status_code == 200:
            msg = resp.json().get("message", {})
            return _extract_date_from_crossref(msg)
    except Exception:
        pass
    return None


def _crossref_by_title(title: str, expected_year: str) -> str | None:
    """Search CrossRef by title, validate year matches."""
    try:
        params = {"query.title": title, "rows": 3}
        resp = requests.get(CROSSREF_BASE, params=params, timeout=15, headers=CROSSREF_HEADERS)
        if resp.status_code == 200:
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                date = _extract_date_from_crossref(item)
                if date and (not expected_year or date.startswith(expected_year)):
                    return date
    except Exception:
        pass
    return None


def _extract_date_from_crossref(msg: dict) -> str | None:
    """Extract best date from CrossRef work record."""
    for field in ["published-online", "published-print", "created"]:
        date_parts = msg.get(field, {}).get("date-parts", [[]])
        if date_parts and date_parts[0]:
            parts = date_parts[0]
            if len(parts) >= 3:
                return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
            elif len(parts) >= 2:
                return f"{parts[0]:04d}-{parts[1]:02d}-01"
    return None


def enrich_dates(raw_results: list[dict]) -> dict[str, str]:
    """Enrich all results with exact dates. Returns {title_lower: date_string}."""
    date_map = {}
    total = len(raw_results)
    success = 0
    doi_hits = 0
    title_hits = 0

    for idx, result in enumerate(raw_results, 1):
        title = (result.get("title", "") or "").strip()
        title_key = title.lower()
        if title_key in date_map:
            continue  # Already resolved

        # Extract expected year from publication_info
        pub_summary = result.get("publication_info", {}).get("summary", "") or ""
        year_match = re.search(r"\b(202[5-6])\b", pub_summary)
        expected_year = year_match.group(1) if year_match else ""

        date = None

        # Step 1: Try DOI from URL
        doi = _extract_doi(result)
        if doi:
            date = _crossref_by_doi(doi)
            if date:
                doi_hits += 1
            time.sleep(0.2)

        # Step 2: Fallback to title search
        if not date and title:
            date = _crossref_by_title(title, expected_year)
            if date:
                title_hits += 1
            time.sleep(0.5)  # Be polite for search queries

        if date:
            date_map[title_key] = date
            success += 1

        if idx % 20 == 0:
            logger.info(f"  Date enrichment: {idx}/{total} processed, {success} dates found")

    logger.info(f"Date enrichment complete: {success}/{total} dates resolved "
                f"(DOI: {doi_hits}, title search: {title_hits})")
    return date_map
