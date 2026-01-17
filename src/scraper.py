"""HTTP request handling for Yahoo Auctions Japan scraper."""

import logging
from typing import Optional
from urllib.parse import urlencode

from .base import BaseScraper
from . import config

logger = logging.getLogger(__name__)


class YahooAuctionsScraper(BaseScraper):
    """Handles HTTP requests to Yahoo Auctions Japan."""

    PLATFORM_NAME = "yahoo_auctions"
    BASE_URL = "https://auctions.yahoo.co.jp"
    RESULTS_PER_PAGE = 100

    def __init__(self, proxy_url: Optional[str] = None):
        super().__init__(
            proxy_url=proxy_url or config.PROXY_URL,
            request_timeout=config.REQUEST_TIMEOUT,
            min_delay=config.MIN_DELAY,
            max_delay=config.MAX_DELAY,
            max_retries=config.MAX_RETRIES,
            backoff_factor=config.BACKOFF_FACTOR,
        )

    def get_user_agents(self) -> list[str]:
        """Return list of user agent strings."""
        return config.USER_AGENTS

    def get_headers(self) -> dict:
        """Build request headers."""
        return {
            "User-Agent": self._get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def build_search_url(
        self,
        keyword: str,
        category: str = "",
        page: int = 1,
        sort: str = "new",
        **kwargs
    ) -> str:
        """
        Build a Yahoo Auctions search URL.

        Args:
            keyword: Search term (Japanese)
            category: Category ID (e.g., "2084199064")
            page: Page number (1-indexed)
            sort: Sort order - "new" for newest first

        Returns:
            Full search URL
        """
        if not category:
            category = config.CATEGORIES["wheels_only"]

        # Sort options: new = newest, cbids = bids, cprice = price
        sort_map = {
            "new": "new",
            "bids": "cbids",
            "price": "cprice",
        }

        # Calculate offset from page number
        # Yahoo uses 'b' parameter as 1-indexed offset
        # Page 1: b=1, Page 2: b=101, Page 3: b=201, etc.
        offset = ((page - 1) * self.RESULTS_PER_PAGE) + 1

        params = {
            "p": keyword,
            "auccat": category,
            "va": keyword,
            "exflg": "1",  # Exclude ended auctions
            "b": str(offset),
            "n": str(self.RESULTS_PER_PAGE),
            "s1": sort_map.get(sort, "new"),
            "o1": "d",  # Descending (newest first)
        }

        return f"{config.SEARCH_BASE_URL}?{urlencode(params)}"

    def search(self, keyword: str, category: str = None, page: int = 1) -> Optional[str]:
        """
        Execute a search and return the HTML response.

        Args:
            keyword: Search term
            category: Category ID (defaults to wheels_only)
            page: Page number (1-indexed)

        Returns:
            HTML content of search results page, or None on failure
        """
        if category is None:
            category = config.CATEGORIES["wheels_only"]

        url = self.build_search_url(keyword, category, page=page)
        logger.info(f"Searching: '{keyword}' in category {category} (page {page})")
        logger.debug(f"URL: {url}")

        response = self.request_with_retry(url)

        if response is None:
            return None

        # Yahoo Auctions uses UTF-8
        response.encoding = "utf-8"
        return response.text

    def search_with_pagination(
        self,
        keyword: str,
        category: str = None,
        max_pages: int = 10,
        parser=None,
    ) -> list[str]:
        """
        Search through all pages of results for a keyword.

        Args:
            keyword: Search term
            category: Category ID
            max_pages: Maximum pages to fetch (safety limit)
            parser: Optional parser instance to get result count

        Returns:
            List of HTML contents from all pages
        """
        if category is None:
            category = config.CATEGORIES["wheels_only"]

        def get_total_results(html: str) -> int:
            if parser:
                return parser.get_result_count(html)
            return 0

        results = []
        page = 1
        total_results = None
        calculated_max_pages = max_pages

        while page <= calculated_max_pages:
            logger.info(f"Fetching page {page}/{calculated_max_pages} for '{keyword}'")

            html = self.search(keyword, category, page=page)
            if not html:
                logger.warning(f"No response for page {page}, stopping pagination")
                break

            results.append(html)

            # On first page, determine total results and calculate pages needed
            if page == 1 and parser:
                total_results = get_total_results(html)
                if total_results:
                    total_pages = (total_results + self.RESULTS_PER_PAGE - 1) // self.RESULTS_PER_PAGE
                    calculated_max_pages = min(max_pages, total_pages)
                    logger.info(f"Total results: {total_results}, will fetch {calculated_max_pages} pages")

            if page >= calculated_max_pages:
                break

            page += 1
            self.random_delay()

        logger.info(f"Fetched {len(results)} pages for '{keyword}'")
        return results

    def search_all_keywords(
        self,
        keywords: list[str] = None,
        categories: list[str] = None,
        paginate: bool = True,
        max_pages_per_search: int = 10,
        parser=None,
    ) -> dict[tuple[str, str], list[str]]:
        """
        Search for all keywords across all categories with pagination.

        Args:
            keywords: List of search terms (defaults to PRIMARY_KEYWORDS)
            categories: List of category IDs (defaults to all)
            paginate: Whether to fetch all pages (True) or just first page (False)
            max_pages_per_search: Maximum pages per keyword/category combo
            parser: Parser instance for getting result counts

        Returns:
            Dict mapping (keyword, category) to list of HTML contents
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
                logger.info(f"Progress: {current}/{total_searches} - '{keyword}' in {category}")

                if paginate:
                    pages = self.search_with_pagination(
                        keyword,
                        category,
                        max_pages=max_pages_per_search,
                        parser=parser,
                    )
                    if pages:
                        results[(keyword, category)] = pages
                else:
                    html = self.search(keyword, category)
                    if html:
                        results[(keyword, category)] = [html]

                # Delay between different keyword searches (not between pages)
                if current < total_searches:
                    self.random_delay()

        return results


def test_basic_search():
    """Test function to verify basic search is working."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    with YahooAuctionsScraper() as scraper:
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
