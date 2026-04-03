"""
SERP API client for Google Patents with rate limiting, pagination, and retry.
"""

import time
import logging
import requests

from config import (
    SERP_API_KEY, SERP_BASE_URL, SERP_RESULTS_PER_PAGE, SERP_MAX_PAGES,
    SERP_RATE_LIMIT_SECONDS, SERP_MAX_RETRIES, SERP_BACKOFF_BASE,
    DATE_AFTER, DATE_BEFORE,
)

logger = logging.getLogger(__name__)


class SerpApiClient:
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

    def search_patents(self, query_config: dict) -> list[dict]:
        """Run a single patent query with pagination. Returns list of raw results."""
        params = {
            "engine": "google_patents",
            "api_key": self.api_key,
            "q": query_config["q"],
            "after": DATE_AFTER,
            "before": DATE_BEFORE,
            "num": SERP_RESULTS_PER_PAGE,
            "sort": "new",
            "type": "PATENT",
        }
        if "assignee" in query_config:
            params["assignee"] = query_config["assignee"]
        if "country" in query_config:
            params["country"] = query_config["country"]

        all_results = []
        for page in range(1, SERP_MAX_PAGES + 1):
            params["page"] = page
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
                f"  Page {page}: {len(results)} results "
                f"(total available: {total_results})"
            )

            # Stop if we got fewer than a full page
            if len(results) < SERP_RESULTS_PER_PAGE:
                break

        return all_results

    def run_all_queries(self, queries: list[dict], progress_callback=None) -> list[dict]:
        """Run all patent queries sequentially. Returns flat list of all results."""
        all_results = []
        total = len(queries)

        for idx, query_config in enumerate(queries, 1):
            q = query_config["q"]
            category = query_config.get("category", "unknown")
            assignee = query_config.get("assignee", "any")

            logger.info(f"[{idx}/{total}] ({category}) assignee={assignee}")
            if progress_callback:
                progress_callback(idx, total, q)

            results = self.search_patents(query_config)
            logger.info(f"  -> {len(results)} results")
            all_results.extend(results)

        logger.info(f"Total raw results: {len(all_results)} from {self.total_requests} API calls")
        return all_results
