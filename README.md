# SERP API Toolkit for Google Patents & Google Scholar

A Python toolkit that leverages [SERP API](https://serpapi.com/) to programmatically search and extract structured data from **Google Patents** and **Google Scholar**. Built for technology intelligence and competitive analysis workflows.

## What This Does

This toolkit provides two parallel pipelines:

1. **Google Patents** (`engine=google_patents`) — Search patent filings by query terms, assignee (company), jurisdiction, and date range. Results are deduplicated, filtered for relevance, and enriched with normalized assignee names.

2. **Google Scholar** (`engine=google_scholar`) — Search academic papers by topic keywords and date range. Results are deduplicated, filtered using a multi-pillar relevance system, and enriched with exact publication dates via the CrossRef API.

Both pipelines return clean, structured Python dataclass objects ready for downstream consumption (dashboards, Excel, databases, etc.).

## Architecture

```
config.py                  # API key, search queries, company mappings, relevance filters
serp_client.py             # Google Patents API client (SERP API)
patent_processor.py        # Patent processing: dedup, company filter, relevance filter, normalization
scholar_client.py          # Google Scholar API client (SERP API)
scholar_processor.py       # Scholar processing: dedup, multi-pillar relevance, classification
scholar_date_enricher.py   # CrossRef API integration for exact publication dates
```

## Setup

### Prerequisites

- Python 3.12+
- A SERP API key ([get one here](https://serpapi.com/))

### Install Dependencies

```bash
pip install requests
```

### Configure API Key

Set your SERP API key as an environment variable:

```bash
export SERP_API_KEY="your_api_key_here"
```

Or set it directly in `config.py` for local development.

## Usage

### Google Patents

```python
from config import ALL_PATENT_QUERIES
from serp_client import SerpApiClient
from patent_processor import process_all

# Run all patent queries
client = SerpApiClient()
raw_results = client.run_all_queries(ALL_PATENT_QUERIES)

# Process: dedup → company filter → relevance filter → normalize
patent_rows = process_all(raw_results)

# Each row is a PatentRow dataclass with:
#   timing, domain, description, region, source, confidence,
#   confidence_rationale, descriptors, patent_id, assignee_raw
for row in patent_rows:
    print(f"{row.assignee_raw} | {row.domain} | {row.description[:80]}")
```

### Google Scholar

```python
from config import SCHOLAR_QUERIES
from scholar_client import ScholarApiClient
from scholar_processor import process_scholar
from scholar_date_enricher import enrich_dates

# Run all scholar queries
client = ScholarApiClient()
raw_results = client.run_all_queries(SCHOLAR_QUERIES)

# Enrich with exact publication dates from CrossRef
date_map = enrich_dates(raw_results)

# Process: dedup → 2-pillar relevance filter → classify → enrich dates
scholar_rows = process_scholar(raw_results, date_map=date_map)

# Each row is a ScholarRow dataclass with:
#   timing, authors, domain, description, region, source,
#   confidence, confidence_rationale, descriptors
for row in scholar_rows:
    print(f"{row.timing} | {row.authors} | {row.domain}")
```

## API Reference

### SERP API — Google Patents

**Endpoint:** `https://serpapi.com/search?engine=google_patents`

Key parameters used:
| Parameter | Description |
|-----------|-------------|
| `q` | Search query with Boolean operators (AND, OR) |
| `assignee` | Filter by patent assignee (company name) |
| `after` | Date filter, e.g. `publication:20251001` |
| `before` | Date filter, e.g. `publication:20260401` |
| `num` | Results per page (max 100) |
| `page` | Page number for pagination |
| `country` | Filter by jurisdiction (e.g. `CN`, `US`) |
| `type` | `PATENT` or `DESIGN` |
| `sort` | `new` (newest first) or `old` |

Response fields per result: `title`, `snippet`, `patent_id`, `publication_number`, `assignee`, `inventor`, `filing_date`, `publication_date`, `grant_date`, `patent_link`, `country_status`.

Full documentation: [serpapi.com/google-patents-api](https://serpapi.com/google-patents-api)

### SERP API — Google Scholar

**Endpoint:** `https://serpapi.com/search?engine=google_scholar`

Key parameters used:
| Parameter | Description |
|-----------|-------------|
| `q` | Search query |
| `as_ylo` | Start year (e.g. `2025`) |
| `as_yhi` | End year (e.g. `2026`) |
| `num` | Results per page (max 20) |
| `start` | Result offset for pagination |
| `as_sdt` | `0` to exclude patents from results |

Response fields per result: `title`, `link`, `snippet`, `publication_info.summary` (authors, journal, year), `inline_links.cited_by`.

Full documentation: [serpapi.com/google-scholar-api](https://serpapi.com/google-scholar-api)

### CrossRef API (for date enrichment)

**Endpoint:** `https://api.crossref.org/works`

Used to resolve exact publication dates for Google Scholar results, which only provide the year. Two lookup strategies:
1. **DOI-based** — extract DOI from article URL, query CrossRef directly
2. **Title-based** — search CrossRef by paper title, validate year matches

No API key required. Rate-limited to ~0.5s between requests.

## Processing Pipeline

### Patent Processing (`patent_processor.py`)

1. **Deduplication** — by `publication_number`
2. **Company filter** — only keeps patents from target companies (configurable in `config.py` via `ASSIGNEE_PATTERNS`). Matches across English, Chinese, Korean, and Japanese name variants.
3. **Relevance filter** — requires at least one strong keyword in title or snippet (configurable via `RELEVANCE_KEYWORDS_STRONG`)
4. **Assignee normalization** — maps all name variants (e.g. `苹果公司`, `アップル インコーポレイテッド`, `Apple Inc.`) to clean English names
5. **Domain classification** — keyword-based categorization (NIR/PBM, Myopia Control, Optics, Wearable, etc.)
6. **Region mapping** — from patent jurisdiction code (US, CN, EP, WO, JP, KR, etc.)

### Scholar Processing (`scholar_processor.py`)

1. **Deduplication** — by title
2. **Two-pillar relevance filter** — paper must contain keywords from at least 2 of 3 technology pillars (configurable via `SCHOLAR_PILLAR_*` lists)
3. **Date enrichment** — exact dates from CrossRef API
4. **Domain classification** — keyword-based categorization
5. **Confidence assessment** — based on journal quality (Nature, JAMA, etc.) and cross-query corroboration

## Configuration

All queries, company lists, and filters are centralized in `config.py`. To adapt this toolkit for a different domain:

1. Update `PARENT_GROUPS` and `ASSIGNEE_PATTERNS` with your target companies
2. Update `ALL_PATENT_QUERIES` with your patent search terms
3. Update `SCHOLAR_QUERIES` with your scholar search terms
4. Update `RELEVANCE_KEYWORDS_STRONG` and `SCHOLAR_PILLAR_*` with your relevance keywords
5. Adjust `DATE_AFTER` / `DATE_BEFORE` for your time period

## Rate Limiting & Costs

- **SERP API**: 2-second delay between calls, exponential backoff on 429/5xx errors. Each search counts as one API credit. Typical run: ~60 API calls (25 patent + 24 scholar + pagination).
- **CrossRef API**: Free, no key required. 0.5s delay between calls.
