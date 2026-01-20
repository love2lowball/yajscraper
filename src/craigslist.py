"""Craigslist scraper for US wheel listings."""

import json
import re
import logging
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from .base import BaseScraper, Listing
from . import config

logger = logging.getLogger(__name__)

# Craigslist categories
CRAIGSLIST_CATEGORIES = {
    "wheels_tires": "wta",   # wheels+tires section
    "auto_parts": "pta",     # auto parts section (also has wheels)
}

# Major US Craigslist markets (comprehensive list)
# Organized by region for potential regional filtering later
CRAIGSLIST_CITIES = [
    # California (major market)
    "sfbay", "losangeles", "sandiego", "sacramento", "fresno", "bakersfield",
    "orangecounty", "inlandempire", "ventura", "stockton", "modesto",
    # Texas
    "dallas", "houston", "sanantonio", "austin", "elpaso", "mcallen",
    # Florida
    "miami", "tampa", "orlando", "jacksonville", "fortlauderdale",
    # Northeast
    "newyork", "boston", "philadelphia", "washingtondc", "baltimore",
    "hartford", "providence", "newjersey", "longisland", "hudsonvalley",
    # Midwest
    "chicago", "detroit", "minneapolis", "stlouis", "indianapolis",
    "columbus", "cincinnati", "cleveland", "milwaukee", "kansascity",
    # Southeast
    "atlanta", "charlotte", "raleigh", "nashville", "memphis",
    "neworleans", "birmingham", "richmond",
    # Southwest
    "phoenix", "lasvegas", "tucson", "albuquerque",
    # Pacific Northwest
    "seattle", "portland", "eugene", "spokane",
    # Mountain
    "denver", "boulder", "cosprings", "saltlakecity",
    # Other major markets
    "honolulu", "anchorage", "pittsburgh", "buffalo", "rochester",
    "albany", "syracuse", "louisville", "oklahomacity", "tulsa",
    "omaha", "wichita", "desmoines", "madison", "grandrapids",
]

# Craigslist-specific settings (conservative due to bot protection)
CRAIGSLIST_MIN_DELAY = 5.0
CRAIGSLIST_MAX_DELAY = 10.0
CRAIGSLIST_RESULTS_PER_PAGE = 120


class CraigslistScraper(BaseScraper):
    """
    Scraper for Craigslist US listings.

    Craigslist doesn't have a nationwide search, so we iterate through
    major US cities. Uses conservative rate limiting due to bot protection.
    """

    PLATFORM_NAME = "craigslist"
    BASE_URL = "https://{city}.craigslist.org"
    RESULTS_PER_PAGE = CRAIGSLIST_RESULTS_PER_PAGE

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        min_delay: float = CRAIGSLIST_MIN_DELAY,
        max_delay: float = CRAIGSLIST_MAX_DELAY,
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
        """Build request headers for Craigslist."""
        return {
            "User-Agent": self._get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

    def build_search_url(
        self,
        city: str,
        keyword: str = "",
        category: str = "wta",
        page: int = 0,
        price_min: int = None,
        price_max: int = None,
        **kwargs
    ) -> str:
        """
        Build a Craigslist search URL.

        Args:
            city: City subdomain (e.g., "sfbay", "losangeles")
            keyword: Search term (optional)
            category: Category code (wta=wheels+tires, pta=auto parts)
            page: Page offset (0-indexed, increments by 120)
            price_min: Minimum price in USD
            price_max: Maximum price in USD

        Returns:
            Full search URL
        """
        base_url = self.BASE_URL.format(city=city)
        path = f"/search/{category}"

        # Build query parameters
        params = [
            "purveyor=owner",           # By owner only
            "bundleDuplicates=1",       # Hide duplicates
        ]

        if keyword:
            params.append(f"query={keyword}")
        if price_min is not None:
            params.append(f"min_price={price_min}")
        if price_max is not None:
            params.append(f"max_price={price_max}")
        if page > 0:
            params.append(f"s={page * self.RESULTS_PER_PAGE}")

        url = f"{base_url}{path}?{'&'.join(params)}"
        return url

    def search(
        self,
        city: str,
        keyword: str = "",
        category: str = "wta",
        page: int = 0,
        price_min: int = None,
        price_max: int = None,
    ) -> Optional[str]:
        """
        Execute a search for a single city and return the HTML response.

        Args:
            city: City subdomain
            keyword: Search term
            category: Category code
            page: Page number (0-indexed)
            price_min: Minimum price
            price_max: Maximum price

        Returns:
            HTML content of search results page, or None on failure
        """
        url = self.build_search_url(
            city=city,
            keyword=keyword,
            category=category,
            page=page,
            price_min=price_min,
            price_max=price_max,
        )

        logger.debug(f"Searching Craigslist: city={city} keyword='{keyword}' category={category}")
        logger.debug(f"URL: {url}")

        response = self.request_with_retry(url)

        if response is None:
            return None

        response.encoding = "utf-8"
        return response.text

    def search_with_pagination(
        self,
        city: str,
        keyword: str = "",
        category: str = "wta",
        price_min: int = None,
        price_max: int = None,
        max_pages: int = 2,
        parser=None,
        db=None,
        duplicate_threshold: float = 1.0,
    ) -> list[str]:
        """
        Search through multiple pages of results for a city.

        Args:
            city: City subdomain
            keyword: Search term
            category: Category code
            price_min: Minimum price
            price_max: Maximum price
            max_pages: Maximum pages to fetch per city
            parser: Optional parser instance to get result count
            db: Optional database instance for duplicate-based early termination
            duplicate_threshold: Stop when 100% of page is duplicates (default 1.0)

        Returns:
            List of HTML contents from all pages
        """
        results = []
        page = 0
        calculated_max_pages = max_pages

        while page < calculated_max_pages:
            html = self.search(
                city=city,
                keyword=keyword,
                category=category,
                page=page,
                price_min=price_min,
                price_max=price_max,
            )

            if not html:
                logger.warning(f"No response for {city} page {page}, stopping pagination")
                break

            results.append(html)

            # On first page, determine total results
            if page == 0 and parser:
                total_results = parser.get_result_count(html)
                if total_results:
                    total_pages = (total_results + self.RESULTS_PER_PAGE - 1) // self.RESULTS_PER_PAGE
                    calculated_max_pages = min(max_pages, total_pages)
                    logger.debug(f"Total results: {total_results}, will fetch {calculated_max_pages} pages")
                elif total_results == 0:
                    # No results, stop
                    break

            # Check for duplicates to enable early termination
            if db and parser and html:
                listings = parser.parse_search_results(html, keyword, city)
                if listings:
                    listing_ids = [l.listing_id for l in listings]
                    dup_ratio = db.get_duplicate_ratio(listing_ids)
                    new_count = len(listings) - int(len(listings) * dup_ratio)
                    logger.info(f"{city} page {page}: {new_count}/{len(listings)} new listings ({dup_ratio:.0%} duplicates)")

                    if dup_ratio >= duplicate_threshold:
                        logger.info(f"Stopping {city}: {dup_ratio:.0%} duplicates exceeds threshold")
                        break

            if page >= calculated_max_pages - 1:
                break

            page += 1
            self.random_delay()

        return results

    def search_all_cities(
        self,
        keywords: list[str],
        cities: list[str] = None,
        categories: list[str] = None,
        price_min: int = None,
        price_max: int = None,
        max_pages_per_city: int = 2,
        parser=None,
        db=None,
    ) -> dict[tuple[str, str, str], list[str]]:
        """
        Search all cities for all keywords.

        Args:
            keywords: List of search terms
            cities: List of city subdomains (defaults to all major cities)
            categories: List of category codes (defaults to wheels+tires only)
            price_min: Minimum price
            price_max: Maximum price
            max_pages_per_city: Max pages per city/keyword combo
            parser: Parser instance for result counts
            db: Optional database instance for duplicate-based early termination

        Returns:
            Dict mapping (city, keyword, category) to list of HTML contents
        """
        if cities is None:
            cities = CRAIGSLIST_CITIES
        if categories is None:
            categories = ["wta"]  # wheels+tires by default

        results = {}
        total_searches = len(cities) * len(keywords) * len(categories)
        current = 0

        for city in cities:
            for keyword in keywords:
                for category in categories:
                    current += 1
                    logger.info(f"[Craigslist {current}/{total_searches}] {city}: '{keyword}' in {category}")

                    html_pages = self.search_with_pagination(
                        city=city,
                        keyword=keyword,
                        category=category,
                        price_min=price_min,
                        price_max=price_max,
                        max_pages=max_pages_per_city,
                        parser=parser,
                        db=db,
                    )

                    if html_pages:
                        results[(city, keyword, category)] = html_pages

                    # Delay between searches
                    if current < total_searches:
                        self.random_delay()

        return results


class CraigslistParser:
    """
    Parser for Craigslist search results.

    Extracts listings from HTML using JSON-LD structured data.
    """

    PLATFORM_NAME = "craigslist"

    def parse_search_results(
        self,
        html: str,
        search_keyword: str = "",
        city: str = "",
    ) -> list[Listing]:
        """
        Parse search results page and extract all listings.

        Args:
            html: Raw HTML content from search page
            search_keyword: The keyword used for this search
            city: The city subdomain searched

        Returns:
            List of Listing objects
        """
        soup = BeautifulSoup(html, "lxml")
        listings = []
        scraped_at = datetime.now()

        # Try to extract from JSON-LD structured data first
        json_ld = self._extract_json_ld(soup)
        if json_ld and "itemListElement" in json_ld:
            for item in json_ld["itemListElement"]:
                try:
                    listing = self._parse_json_ld_item(item, search_keyword, city, scraped_at)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.warning(f"Failed to parse Craigslist JSON-LD item: {e}")
                    continue

        # Fallback to HTML parsing if no JSON-LD
        if not listings:
            listings = self._parse_html_listings(soup, search_keyword, city, scraped_at)

        logger.info(f"Parsed {len(listings)} listings from Craigslist {city}")
        return listings

    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extract JSON-LD structured data from page."""
        script = soup.find("script", type="application/ld+json")
        if script:
            try:
                return json.loads(script.string)
            except json.JSONDecodeError:
                pass
        return None

    def _parse_json_ld_item(
        self,
        item: dict,
        search_keyword: str,
        city: str,
        scraped_at: datetime,
    ) -> Optional[Listing]:
        """Parse a single JSON-LD item into a Listing."""
        # Extract from nested structure
        if "item" in item:
            item = item["item"]

        # Get listing URL and extract ID
        listing_url = item.get("url", "")
        listing_id = self._extract_listing_id(listing_url)
        if not listing_id:
            return None

        # Get title
        title = item.get("name", "")
        if not title:
            return None

        # Get price
        offers = item.get("offers", {})
        price = 0
        if isinstance(offers, dict):
            price_str = str(offers.get("price", "0"))
            try:
                price = int(float(price_str))
            except ValueError:
                price = 0

        # Get location
        location = ""
        region = city  # Use city as region
        available_at = offers.get("availableAtOrFrom", {})
        if isinstance(available_at, dict):
            address = available_at.get("address", {})
            if isinstance(address, dict):
                locality = address.get("addressLocality", "")
                state = address.get("addressRegion", "")
                if locality and state:
                    location = f"{locality}, {state}"
                elif locality:
                    location = locality
                elif state:
                    location = state

        # Get thumbnail
        images = item.get("image", [])
        thumbnail_url = ""
        if isinstance(images, list) and images:
            thumbnail_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")
        elif isinstance(images, str):
            thumbnail_url = images

        return Listing(
            listing_id=listing_id,
            platform=self.PLATFORM_NAME,
            title=title,
            current_price=price,
            currency="USD",
            thumbnail_url=thumbnail_url,
            listing_url=listing_url,
            search_keyword=search_keyword,
            location=location,
            region=region,
            scraped_at=scraped_at,
        )

    def _parse_html_listings(
        self,
        soup: BeautifulSoup,
        search_keyword: str,
        city: str,
        scraped_at: datetime,
    ) -> list[Listing]:
        """Fallback HTML parsing for listings."""
        listings = []

        # Look for listing links
        listing_links = soup.find_all("a", class_="cl-app-anchor")
        if not listing_links:
            listing_links = soup.find_all("a", href=re.compile(r"/[a-z]+/d/"))

        for link in listing_links:
            try:
                href = link.get("href", "")
                listing_id = self._extract_listing_id(href)
                if not listing_id:
                    continue

                # Get title
                title_elem = link.find("span", class_="label") or link
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Get price
                price = 0
                price_elem = link.find_parent().find(class_="priceinfo") if link.find_parent() else None
                if price_elem:
                    price_text = price_elem.get_text()
                    price_match = re.search(r"\$([0-9,]+)", price_text)
                    if price_match:
                        price = int(price_match.group(1).replace(",", ""))

                # Build full URL
                if href.startswith("http"):
                    listing_url = href
                else:
                    listing_url = f"https://{city}.craigslist.org{href}"

                listings.append(Listing(
                    listing_id=listing_id,
                    platform=self.PLATFORM_NAME,
                    title=title,
                    current_price=price,
                    currency="USD",
                    listing_url=listing_url,
                    search_keyword=search_keyword,
                    region=city,
                    scraped_at=scraped_at,
                ))

            except Exception as e:
                logger.warning(f"Failed to parse HTML listing: {e}")
                continue

        return listings

    def _extract_listing_id(self, url: str) -> Optional[str]:
        """Extract listing ID from Craigslist URL."""
        # URL format: .../d/title-slug/1234567890.html
        match = re.search(r"/(\d{8,12})\.html", url)
        if match:
            return match.group(1)
        return None

    def get_result_count(self, html: str) -> int:
        """Extract total number of search results."""
        soup = BeautifulSoup(html, "lxml")

        # Try JSON-LD first
        json_ld = self._extract_json_ld(soup)
        if json_ld and "itemListElement" in json_ld:
            return len(json_ld["itemListElement"])

        # Try result count element
        count_elem = soup.find(class_="cl-results-count")
        if count_elem:
            text = count_elem.get_text()
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))

        return 0


# Test function
def test_craigslist_search():
    """Test function to verify Craigslist search is working."""
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    with CraigslistScraper() as scraper:
        parser = CraigslistParser()

        # Test with a single city and keyword
        city = "losangeles"
        keyword = "wheels"

        print(f"\n{'='*60}")
        print(f"Testing Craigslist search for: {keyword}")
        print(f"City: {city}")
        print(f"{'='*60}\n")

        html = scraper.search(
            city=city,
            keyword=keyword,
            category="wta",
            price_min=150,
            price_max=1200,
        )

        if html:
            print(f"SUCCESS: Received {len(html):,} bytes of HTML")

            # Get result count
            count = parser.get_result_count(html)
            print(f"Total results: {count}")

            # Parse listings
            listings = parser.parse_search_results(html, keyword, city)
            print(f"Parsed {len(listings)} listings")

            if listings:
                print("\nFirst 3 listings:")
                for listing in listings[:3]:
                    print(f"  - {listing.title[:60]}...")
                    print(f"    Price: ${listing.current_price:,}")
                    print(f"    Location: {listing.location}")
                    print(f"    URL: {listing.listing_url}")

            return html
        else:
            print("FAILED: No response received")
            return None


if __name__ == "__main__":
    test_craigslist_search()
