"""HTTP request handling for Yahoo Auctions Japan scraper."""

import random
import time
import logging
from urllib.parse import urlencode
from typing import Optional

import requests

from . import config

logger = logging.getLogger(__name__)


class YahooAuctionsScraper:
    """Handles HTTP requests to Yahoo Auctions Japan."""

    def __init__(self, proxy_url: Optional[str] = None):
        self.session = requests.Session()
        self.proxy_url = proxy_url or config.PROXY_URL

        if self.proxy_url:
            self.session.proxies = {
                "http": self.proxy_url,
                "https": self.proxy_url,
            }

    def _get_random_user_agent(self) -> str:
        """Return a random user agent string."""
        return random.choice(config.USER_AGENTS)

    def _get_headers(self) -> dict:
        """Build request headers."""
        return {
            "User-Agent": self._get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _random_delay(self) -> None:
        """Sleep for a random duration between requests."""
        delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)
        logger.debug(f"Sleeping for {delay:.2f} seconds")
        time.sleep(delay)

    def _request_with_retry(self, url: str) -> Optional[requests.Response]:
        """Make a GET request with retry logic and exponential backoff."""
        for attempt in range(config.MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=config.REQUEST_TIMEOUT,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = config.BACKOFF_FACTOR ** (attempt + 1)
                    logger.warning(f"Rate limited (429). Waiting {wait_time}s before retry.")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                wait_time = config.BACKOFF_FACTOR ** attempt
                logger.warning(f"Request failed (attempt {attempt + 1}/{config.MAX_RETRIES}): {e}")

                if attempt < config.MAX_RETRIES - 1:
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {config.MAX_RETRIES} attempts failed for URL: {url}")
                    return None

        return None

    def build_search_url(self, keyword: str, category: str, sort: str = "new") -> str:
        """
        Build a Yahoo Auctions search URL.

        Args:
            keyword: Search term (Japanese)
            category: Category ID (e.g., "2084199064")
            sort: Sort order - "new" for newest first

        Returns:
            Full search URL
        """
        # Sort options: new = newest, cbids = bids, cprice = price
        sort_map = {
            "new": "new",
            "bids": "cbids",
            "price": "cprice",
        }

        params = {
            "p": keyword,
            "auccat": category,
            "va": keyword,
            "exflg": "1",  # Exclude ended auctions
            "b": "1",      # Start from first result
            "n": "100",    # Results per page
            "s1": sort_map.get(sort, "new"),
            "o1": "d",     # Descending (newest first)
        }

        return f"{config.SEARCH_BASE_URL}?{urlencode(params)}"

    def search(self, keyword: str, category: str = None) -> Optional[str]:
        """
        Execute a search and return the HTML response.

        Args:
            keyword: Search term
            category: Category ID (defaults to wheels_only)

        Returns:
            HTML content of search results page, or None on failure
        """
        if category is None:
            category = config.CATEGORIES["wheels_only"]

        url = self.build_search_url(keyword, category)
        logger.info(f"Searching: '{keyword}' in category {category}")
        logger.debug(f"URL: {url}")

        response = self._request_with_retry(url)

        if response is None:
            return None

        # Yahoo Auctions uses UTF-8
        response.encoding = "utf-8"
        return response.text

    def search_all_keywords(
        self,
        keywords: list[str] = None,
        categories: list[str] = None
    ) -> dict[str, str]:
        """
        Search for all keywords across all categories.

        Args:
            keywords: List of search terms (defaults to PRIMARY_KEYWORDS)
            categories: List of category IDs (defaults to all)

        Returns:
            Dict mapping (keyword, category) to HTML content
        """
        if keywords is None:
            keywords = config.PRIMARY_KEYWORDS

        if categories is None:
            categories = list(config.CATEGORIES.values())

        results = {}
        total_searches = len(keywords) * len(categories)
        current = 0

        for keyword in keywords:
            for category in categories:
                current += 1
                logger.info(f"Progress: {current}/{total_searches}")

                html = self.search(keyword, category)
                if html:
                    results[(keyword, category)] = html

                # Delay between requests (except for last one)
                if current < total_searches:
                    self._random_delay()

        return results


def test_basic_search():
    """Test function to verify basic search is working."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    scraper = YahooAuctionsScraper()

    # Test with a single keyword
    keyword = "希少 ホイール"
    print(f"\n{'='*60}")
    print(f"Testing search for: {keyword}")
    print(f"{'='*60}\n")

    html = scraper.search(keyword)

    if html:
        print(f"SUCCESS: Received {len(html):,} bytes of HTML")
        print(f"\nFirst 500 characters:")
        print("-" * 40)
        print(html[:500])
        print("-" * 40)

        # Quick check for expected content
        if "Product" in html or "件" in html or "auction" in html.lower():
            print("\n✓ Response appears to contain auction data")
        else:
            print("\n⚠ Response may not contain expected auction data")

        return html
    else:
        print("FAILED: No response received")
        return None


if __name__ == "__main__":
    test_basic_search()
