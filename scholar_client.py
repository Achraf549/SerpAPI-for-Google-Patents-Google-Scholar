"""
SERP API client for Google Scholar with rate limiting, pagination, and retry.
"""

import time
import logging
import requests

from config import (
    SERP_API_KEY, SERP_BASE_URL,
    SERP_RATE_LIMIT_SECONDS, SERP_MAX_RETRIES, SERP_BACKOFF_BASE,
)

logger = logging.getLogger(__name__)

# Google Scholar: max 20 results per page, offset-based pagination
SCHOLAR_RESULTS_PER_PAGE = 20
SCHOLAR_MAX_PAGES = 2  # 2 pages x 20 = 40 results max per query


class ScholarApiClient:
    def __init__(self, api_key: str = SERP_API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.total_requests = 0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < SERP_RATE_LIMIT_SECONDS:
            time.sleep(SERP_RATE_LIMIT_SECONDS - elapsed)

    def _make_request(self, params: dict) -> dict | None:
        for attempt in range(SERP_MAX_RETRIES):
            self._rate_limit()
            try:
                self.last_request_time = time.time()
                self.total_requests += 1
                resp = self.session.get(SERP_BASE_URL, params=params, timeout=30)

                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    wait = SERP_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(f"Rate limited (429). Waiting {wait}s...")
                    time.sleep(wait)
                elif resp.status_code >= 500:
                    wait = SERP_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(f"Server error {resp.status_code}. Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"API error {resp.status_code}: {resp.text[:200]}")
                    return None
            except requests.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < SERP_MAX_RETRIES - 1:
                    time.sleep(SERP_BACKOFF_BASE * (2 ** attempt))

        logger.error("All retries exhausted.")
        return None

    def search_scholar(self, query_config: dict) -> list[dict]:
        """Run a single scholar query with pagination. Returns list of raw results."""
        params = {
            "engine": "google_scholar",
            "api_key": self.api_key,
            "q": query_config["q"],
            "as_ylo": "2025",  # From 2025
            "as_yhi": "2026",  # To 2026
            "num": SCHOLAR_RESULTS_PER_PAGE,
            "as_sdt": "0",  # Exclude patents (we already have those)
        }
        if "hl" in query_config:
            params["hl"] = query_config["hl"]

        all_results = []
        for page in range(SCHOLAR_MAX_PAGES):
            params["start"] = page * SCHOLAR_RESULTS_PER_PAGE
            data = self._make_request(params)
            if not data:
                break

            results = data.get("organic_results", [])
            if not results:
                break

            # Tag each result with the query that found it
            for r in results:
                r["_query_config"] = query_config
                r["_query_q"] = query_config["q"]

            all_results.extend(results)

            total_results = data.get("search_information", {}).get("total_results", 0)
            logger.info(
                f"  Page {page + 1}: {len(results)} results "
                f"(total available: {total_results})"
            )

            # Stop if we got fewer than a full page
            if len(results) < SCHOLAR_RESULTS_PER_PAGE:
                break

        return all_results

    def run_all_queries(self, queries: list[dict], progress_callback=None) -> list[dict]:
        """Run all scholar queries sequentially."""
        all_results = []
        total = len(queries)

        for idx, query_config in enumerate(queries, 1):
            q = query_config["q"]
            logger.info(f"[{idx}/{total}] q={q[:70]}...")
            if progress_callback:
                progress_callback(idx, total, q)

            results = self.search_scholar(query_config)
            logger.info(f"  -> {len(results)} results")
            all_results.extend(results)

        logger.info(f"Total raw scholar results: {len(all_results)} from {self.total_requests} API calls")
        return all_results
