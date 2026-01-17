"""JMTY (ジモティー) scraper for Japanese classifieds."""

import re
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import BaseScraper, Listing
from . import config

logger = logging.getLogger(__name__)

# JMTY categories
JMTY_CATEGORIES = {
    "tire_wheel": "g-2429",  # タイヤ、ホイール
}

# JMTY-specific settings (more conservative due to bot protection)
JMTY_MIN_DELAY = 5.0
JMTY_MAX_DELAY = 10.0
JMTY_RESULTS_PER_PAGE = 50


class JMTYScraper(BaseScraper):
    """
    Scraper for JMTY (ジモティー) classifieds.

    JMTY is a Japanese classifieds site similar to Craigslist.
    Uses server-rendered HTML with bot protection.
    """

    PLATFORM_NAME = "jmty"
    BASE_URL = "https://jmty.jp"
    RESULTS_PER_PAGE = JMTY_RESULTS_PER_PAGE

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        min_delay: float = JMTY_MIN_DELAY,
        max_delay: float = JMTY_MAX_DELAY,
    ):
        super().__init__(
            proxy_url=proxy_url or config.PROXY_URL,
            request_timeout=config.REQUEST_TIMEOUT,
            min_delay=min_delay,
            max_delay=max_delay,
            max_retries=config.MAX_RETRIES,
            backoff_factor=config.BACKOFF_FACTOR,
        )

    def get_user_agents(self) -> list[str]:
        """Return list of user agent strings."""
        return config.USER_AGENTS

    def get_headers(self) -> dict:
        """Build request headers for JMTY."""
        return {
            "User-Agent": self._get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

    def build_search_url(
        self,
        keyword: str = "",
        category: str = "",
        region: str = "all",
        page: int = 1,
        price_min: int = None,
        price_max: int = None,
        **kwargs
    ) -> str:
        """
        Build a JMTY search URL.

        Args:
            keyword: Search term (optional)
            category: Category code (e.g., "g-2429" for tires/wheels)
            region: Region code ("all" for nationwide, or prefecture like "tokyo")
            page: Page number (1-indexed)
            price_min: Minimum price in yen
            price_max: Maximum price in yen

        Returns:
            Full search URL
        """
        # Base path
        if category:
            path = f"/{region}/sale-auto/{category}"
        else:
            path = f"/{region}/sale-auto"

        # Add pagination to path
        if page > 1:
            path += f"/p-{page}"

        # Build query parameters
        params = {}
        # Keyword is a query parameter, not path segment
        if keyword:
            params["keyword"] = keyword
        if price_min is not None:
            params["min"] = price_min
        if price_max is not None:
            params["max"] = price_max

        url = f"{self.BASE_URL}{path}"
        if params:
            url += f"?{urlencode(params)}"

        return url

    def search(
        self,
        keyword: str = "",
        category: str = None,
        region: str = "all",
        page: int = 1,
        price_min: int = None,
        price_max: int = None,
    ) -> Optional[str]:
        """
        Execute a search and return the HTML response.

        Args:
            keyword: Search term
            category: Category code
            region: Region code
            page: Page number
            price_min: Minimum price
            price_max: Maximum price

        Returns:
            HTML content of search results page, or None on failure
        """
        if category is None:
            category = JMTY_CATEGORIES["tire_wheel"]

        url = self.build_search_url(
            keyword=keyword,
            category=category,
            region=region,
            page=page,
            price_min=price_min,
            price_max=price_max,
        )

        logger.info(f"Searching JMTY: keyword='{keyword}' category={category} region={region} (page {page})")
        logger.debug(f"URL: {url}")

        response = self.request_with_retry(url)

        if response is None:
            return None

        response.encoding = "utf-8"
        return response.text

    def search_with_pagination(
        self,
        keyword: str = "",
        category: str = None,
        region: str = "all",
        price_min: int = None,
        price_max: int = None,
        max_pages: int = 5,
        parser=None,
    ) -> list[str]:
        """
        Search through multiple pages of results.

        Args:
            keyword: Search term
            category: Category code
            region: Region code
            price_min: Minimum price
            price_max: Maximum price
            max_pages: Maximum pages to fetch
            parser: Optional parser instance to get result count

        Returns:
            List of HTML contents from all pages
        """
        if category is None:
            category = JMTY_CATEGORIES["tire_wheel"]

        results = []
        page = 1
        total_results = None
        calculated_max_pages = max_pages

        while page <= calculated_max_pages:
            logger.info(f"Fetching JMTY page {page}/{calculated_max_pages} for '{keyword}'")

            html = self.search(
                keyword=keyword,
                category=category,
                region=region,
                page=page,
                price_min=price_min,
                price_max=price_max,
            )

            if not html:
                logger.warning(f"No response for page {page}, stopping pagination")
                break

            results.append(html)

            # On first page, determine total results
            if page == 1 and parser:
                total_results = parser.get_result_count(html)
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
        keywords: list[str],
        category: str = None,
        region: str = "all",
        price_min: int = None,
        price_max: int = None,
        max_pages_per_search: int = 5,
        parser=None,
    ) -> dict[tuple[str, str], list[str]]:
        """
        Search all keywords.

        Args:
            keywords: List of search terms
            category: Category code
            region: Region code
            price_min: Minimum price
            price_max: Maximum price
            max_pages_per_search: Max pages per keyword
            parser: Parser instance for result counts

        Returns:
            Dict mapping (keyword, category) to list of HTML contents
        """
        if category is None:
            category = JMTY_CATEGORIES["tire_wheel"]

        results = {}
        total_searches = len(keywords)
        current = 0

        for keyword in keywords:
            current += 1
            logger.info(f"Progress: {current}/{total_searches} - '{keyword}' in {category}")

            html_pages = self.search_with_pagination(
                keyword=keyword,
                category=category,
                region=region,
                price_min=price_min,
                price_max=price_max,
                max_pages=max_pages_per_search,
                parser=parser,
            )

            if html_pages:
                results[(keyword, category)] = html_pages

            # Delay between different keyword searches
            if current < total_searches:
                self.random_delay()

        return results


class JMTYParser:
    """
    Parser for JMTY search results.

    Parses server-rendered HTML into Listing objects.
    """

    PLATFORM_NAME = "jmty"

    def parse_search_results(self, html: str, search_keyword: str = "") -> list[Listing]:
        """
        Parse search results page and extract all listings.

        Args:
            html: Raw HTML content from search page
            search_keyword: The keyword used for this search

        Returns:
            List of Listing objects
        """
        soup = BeautifulSoup(html, "lxml")
        listings = []
        scraped_at = datetime.now()

        # JMTY listings are in <li> elements with article links
        # Look for listing containers - they have links to /all/sale-auto/ articles
        listing_links = soup.find_all("a", href=re.compile(r"/[^/]+/sale-auto/article-\w+"))

        # Deduplicate by href (same listing may appear multiple times)
        seen_urls = set()
        unique_containers = []

        for link in listing_links:
            href = link.get("href", "")
            if href and href not in seen_urls:
                seen_urls.add(href)
                # Get parent container that has all listing info
                parent = link.find_parent("li") or link.find_parent("div")
                if parent and parent not in unique_containers:
                    unique_containers.append((parent, href))

        logger.info(f"Found {len(unique_containers)} listing containers")

        for container, href in unique_containers:
            try:
                listing = self._parse_single_listing(container, href, search_keyword, scraped_at)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Failed to parse JMTY listing: {e}")
                continue

        logger.info(f"Successfully parsed {len(listings)} listings")
        return listings

    def _parse_single_listing(
        self,
        container,
        href: str,
        search_keyword: str,
        scraped_at: datetime
    ) -> Optional[Listing]:
        """Parse a single listing container."""

        # Extract listing ID from URL
        # URL format: /prefecture/sale-auto/article-xxxxx
        match = re.search(r"article-(\w+)", href)
        if not match:
            return None
        listing_id = match.group(1)

        # Extract title
        title = self._extract_title(container)
        if not title:
            return None

        # Extract price
        price = self._extract_price(container)

        # Extract location
        location, region = self._extract_location(container)

        # Extract thumbnail
        thumbnail_url = self._extract_thumbnail(container)

        # Build listing URL
        listing_url = f"https://jmty.jp{href}"

        return Listing(
            listing_id=listing_id,
            platform=self.PLATFORM_NAME,
            title=title,
            current_price=price,
            currency="JPY",
            thumbnail_url=thumbnail_url,
            listing_url=listing_url,
            search_keyword=search_keyword,
            location=location,
            region=region,
            scraped_at=scraped_at,
        )

    def _extract_title(self, container) -> Optional[str]:
        """Extract the listing title."""
        # Try finding title in various elements
        # JMTY typically has title in the link text or a heading

        # Look for the main link text
        link = container.find("a", href=re.compile(r"article-"))
        if link:
            # Get text, but exclude child elements that might have extra info
            title_elem = link.find("p") or link.find("span") or link
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title and len(title) > 3:
                    return title

        # Fallback: any text content
        text = container.get_text(strip=True)
        if text:
            # Take first line as title
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if len(line) > 5 and '円' not in line[:10]:
                    return line[:200]  # Limit length

        return None

    def _extract_price(self, container) -> int:
        """Extract price in yen."""
        text = container.get_text()

        # Look for price patterns
        # Common formats: "8,000円", "¥8,000", "8000円"
        patterns = [
            r"([\d,]+)\s*円",
            r"[¥￥]\s*([\d,]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(",", "")
                try:
                    return int(price_str)
                except ValueError:
                    continue

        # Check for free items
        if "無料" in text or "0円" in text:
            return 0

        return 0

    def _extract_location(self, container) -> tuple[str, str]:
        """Extract location and region."""
        text = container.get_text()

        # Japanese prefectures
        prefectures = [
            "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島",
            "茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川",
            "新潟", "富山", "石川", "福井", "山梨", "長野", "岐阜",
            "静岡", "愛知", "三重", "滋賀", "京都", "大阪", "兵庫",
            "奈良", "和歌山", "鳥取", "島根", "岡山", "広島", "山口",
            "徳島", "香川", "愛媛", "高知", "福岡", "佐賀", "長崎",
            "熊本", "大分", "宮崎", "鹿児島", "沖縄"
        ]

        region = ""
        location = ""

        for pref in prefectures:
            if pref in text:
                region = pref
                # Try to find city after prefecture
                pref_idx = text.find(pref)
                after_pref = text[pref_idx:pref_idx+20]
                # Look for city pattern (ends with 市, 区, 町, 村)
                city_match = re.search(r"([^\s]{2,}[市区町村])", after_pref)
                if city_match:
                    location = f"{region} {city_match.group(1)}"
                else:
                    location = region
                break

        return location, region

    def _extract_thumbnail(self, container) -> str:
        """Extract thumbnail image URL."""
        img = container.find("img")
        if img:
            # Prioritize lazy-loaded image URLs over placeholder src
            # JMTY uses data-original for actual images, src is often a placeholder
            src = img.get("data-original") or img.get("data-src") or img.get("src")
            if src:
                # Skip placeholder images
                if "no_img" in src or "placeholder" in src:
                    return ""
                # Make sure it's a full URL
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = "https://jmty.jp" + src
                return src
        return ""

    def get_result_count(self, html: str) -> int:
        """Extract total number of search results."""
        soup = BeautifulSoup(html, "lxml")

        # JMTY shows "全XXX件" format
        text = soup.get_text()
        match = re.search(r"全\s*([\d,]+)\s*件", text)
        if match:
            return int(match.group(1).replace(",", ""))

        return 0


# Test function
def test_jmty_search():
    """Test function to verify JMTY search is working."""
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    with JMTYScraper() as scraper:
        parser = JMTYParser()

        # Test with a single keyword
        keyword = "BBS"
        category = JMTY_CATEGORIES["tire_wheel"]

        print(f"\n{'='*60}")
        print(f"Testing JMTY search for: {keyword}")
        print(f"Category: {category}")
        print(f"{'='*60}\n")

        html = scraper.search(
            keyword=keyword,
            category=category,
            price_min=5000,
            price_max=2000000,
        )

        if html:
            print(f"SUCCESS: Received {len(html):,} bytes of HTML")

            # Get result count
            count = parser.get_result_count(html)
            print(f"Total results: {count}")

            # Parse listings
            listings = parser.parse_search_results(html, keyword)
            print(f"Parsed {len(listings)} listings")

            if listings:
                print("\nFirst 3 listings:")
                for listing in listings[:3]:
                    print(f"  - {listing.title[:50]}...")
                    print(f"    Price: {listing.current_price:,}円")
                    print(f"    Location: {listing.location}")
                    print(f"    URL: {listing.listing_url}")

            return html
        else:
            print("FAILED: No response received")
            return None


if __name__ == "__main__":
    test_jmty_search()
