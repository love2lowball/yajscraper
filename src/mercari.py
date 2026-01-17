"""Mercari Japan scraper using mercapi library."""

import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Optional

from .base import Listing

logger = logging.getLogger(__name__)

# Mercari categories
MERCARI_CATEGORIES = {
    "wheels_only": 1112,
    "tire_wheel_sets": 1109,
}

# Extra delay range for Mercari (more conservative than Yahoo)
MERCARI_MIN_DELAY = 3.0
MERCARI_MAX_DELAY = 7.0


class MercariScraper:
    """
    Scraper for Mercari Japan using the mercapi library.

    Note: mercapi handles the DPoP authentication tokens automatically.
    """

    PLATFORM_NAME = "mercari"
    RESULTS_PER_PAGE = 120  # Mercari's default page size

    def __init__(
        self,
        min_delay: float = MERCARI_MIN_DELAY,
        max_delay: float = MERCARI_MAX_DELAY,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._mercapi = None

    async def _get_client(self):
        """Lazy initialization of mercapi client."""
        if self._mercapi is None:
            from mercapi import Mercapi
            self._mercapi = Mercapi()
        return self._mercapi

    def _random_delay(self) -> None:
        """Sleep for a random duration between requests."""
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug(f"Sleeping for {delay:.2f} seconds")
        time.sleep(delay)

    async def search(
        self,
        keyword: str,
        category: int = None,
        price_min: int = None,
        price_max: int = None,
        page_token: str = None,
    ):
        """
        Execute a search on Mercari Japan.

        Args:
            keyword: Search term
            category: Mercari category ID (1112=wheels, 1109=tire+wheels)
            price_min: Minimum price in yen
            price_max: Maximum price in yen
            page_token: Token for pagination (from previous results)

        Returns:
            SearchResults object from mercapi, or None on failure
        """
        try:
            client = await self._get_client()

            # Build search parameters
            categories = [category] if category else []

            logger.info(f"Searching Mercari: '{keyword}' category={category}")

            results = await client.search(
                query=keyword,
                categories=categories,
                price_min=price_min,
                price_max=price_max,
                page_token=page_token,
                # Note: status filter removed - mercapi returns active listings by default
            )

            logger.info(f"Found {results.meta.num_found} total results")
            return results

        except Exception as e:
            logger.error(f"Mercari search failed: {e}")
            return None

    async def search_with_pagination(
        self,
        keyword: str,
        category: int = None,
        price_min: int = None,
        price_max: int = None,
        max_pages: int = 5,
    ) -> list:
        """
        Search through multiple pages of results.

        Args:
            keyword: Search term
            category: Category ID
            price_min: Minimum price
            price_max: Maximum price
            max_pages: Maximum pages to fetch

        Returns:
            List of all SearchResults objects
        """
        all_results = []
        page_token = None
        page = 0

        while page < max_pages:
            page += 1
            logger.info(f"Fetching Mercari page {page}/{max_pages} for '{keyword}'")

            results = await self.search(
                keyword=keyword,
                category=category,
                price_min=price_min,
                price_max=price_max,
                page_token=page_token,
            )

            if not results or not results.items:
                logger.info(f"No more results at page {page}")
                break

            all_results.append(results)

            # Check if there's a next page
            if not results.meta.next_page_token:
                logger.info(f"No more pages after page {page}")
                break

            page_token = results.meta.next_page_token

            # Delay between pages
            if page < max_pages:
                self._random_delay()

        logger.info(f"Fetched {len(all_results)} pages for '{keyword}'")
        return all_results

    async def search_all_keywords(
        self,
        keywords: list[str],
        categories: list[int] = None,
        price_min: int = None,
        price_max: int = None,
        max_pages_per_search: int = 5,
    ) -> dict:
        """
        Search all keywords across all categories.

        Args:
            keywords: List of search terms
            categories: List of category IDs
            price_min: Minimum price
            price_max: Maximum price
            max_pages_per_search: Max pages per keyword/category combo

        Returns:
            Dict mapping (keyword, category) to list of SearchResults
        """
        if categories is None:
            categories = list(MERCARI_CATEGORIES.values())

        results = {}
        total_searches = len(keywords) * len(categories)
        current = 0

        for keyword in keywords:
            for category in categories:
                current += 1
                logger.info(f"Progress: {current}/{total_searches} - '{keyword}' in category {category}")

                search_results = await self.search_with_pagination(
                    keyword=keyword,
                    category=category,
                    price_min=price_min,
                    price_max=price_max,
                    max_pages=max_pages_per_search,
                )

                if search_results:
                    results[(keyword, category)] = search_results

                # Delay between different keyword searches
                if current < total_searches:
                    self._random_delay()

        return results


class MercariParser:
    """
    Parser for Mercari search results.

    Converts mercapi SearchResults into our Listing format.
    """

    PLATFORM_NAME = "mercari"

    def parse_search_results(self, search_results, search_keyword: str = "") -> list[Listing]:
        """
        Parse mercapi SearchResults into Listing objects.

        Args:
            search_results: SearchResults object from mercapi
            search_keyword: The keyword used for this search

        Returns:
            List of Listing objects
        """
        listings = []
        scraped_at = datetime.now()

        if not search_results or not search_results.items:
            return listings

        for item in search_results.items:
            try:
                listing = self._parse_item(item, search_keyword, scraped_at)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Failed to parse Mercari item: {e}")
                continue

        logger.info(f"Parsed {len(listings)} listings from Mercari results")
        return listings

    def _parse_item(self, item, search_keyword: str, scraped_at: datetime) -> Optional[Listing]:
        """Parse a single mercapi item into a Listing."""
        # Extract item ID (mercapi uses id_ not id)
        item_id = getattr(item, 'id_', None) or getattr(item, 'id', None)
        if not item_id:
            return None

        # Extract basic info (mercapi uses 'name' for title)
        title = getattr(item, 'name', '') or ''
        if not title:
            return None

        # Extract price
        price = getattr(item, 'price', 0) or 0

        # Extract seller info
        seller = getattr(item, 'seller', None)
        seller_id = getattr(item, 'seller_id', '') or ''
        seller_name = ''
        seller_rating = ''
        if seller:
            seller_name = getattr(seller, 'name', '') or ''
            # Mercari uses ratings count
            ratings = getattr(seller, 'ratings', None)
            if ratings:
                seller_rating = str(getattr(ratings, 'good', 0))

        # Extract thumbnail
        thumbnails = getattr(item, 'thumbnails', []) or []
        thumbnail_url = thumbnails[0] if thumbnails else ''

        # Build listing URL
        listing_url = f"https://jp.mercari.com/item/{item_id}"

        # Extract condition (mercapi uses item_condition_id as int)
        condition_id = getattr(item, 'item_condition_id', 0) or 0
        condition = self._map_condition(condition_id)

        # Extract shipping info (mercapi uses shipping_payer_id as int)
        shipping_payer_id = getattr(item, 'shipping_payer_id', 0) or 0
        shipping_info = self._map_shipping(shipping_payer_id)

        return Listing(
            listing_id=str(item_id),
            platform=self.PLATFORM_NAME,
            title=title,
            current_price=int(price),
            currency="JPY",
            seller_id=str(seller_id),
            seller_name=seller_name,
            seller_rating=seller_rating,
            thumbnail_url=thumbnail_url,
            listing_url=listing_url,
            search_keyword=search_keyword,
            condition=condition,
            shipping_info=shipping_info,
            scraped_at=scraped_at,
        )

    def _map_condition(self, condition_id: int) -> str:
        """Map Mercari condition ID to readable string."""
        # Mercari condition IDs
        condition_map = {
            1: "new",
            2: "like_new",
            3: "good",
            4: "fair",
            5: "poor",
            6: "bad",
        }
        return condition_map.get(condition_id, "unknown")

    def _map_shipping(self, shipping_payer_id: int) -> str:
        """Map Mercari shipping payer ID to readable string."""
        # 1 = seller pays, 2 = buyer pays
        if shipping_payer_id == 1:
            return "seller_pays"
        elif shipping_payer_id == 2:
            return "buyer_pays"
        return "unknown"

    def get_result_count(self, search_results) -> int:
        """Get total result count from search results."""
        if not search_results:
            return 0
        meta = getattr(search_results, 'meta', None)
        if meta:
            return getattr(meta, 'num_found', 0) or 0
        return 0


def run_mercari_sync(
    keywords: list[str],
    categories: list[int] = None,
    price_min: int = None,
    price_max: int = None,
    max_pages: int = 5,
) -> list[Listing]:
    """
    Synchronous wrapper for running Mercari scraper.

    Use this from synchronous code (like run.py).
    """
    async def _run():
        scraper = MercariScraper()
        parser = MercariParser()

        all_listings = []

        results = await scraper.search_all_keywords(
            keywords=keywords,
            categories=categories,
            price_min=price_min,
            price_max=price_max,
            max_pages_per_search=max_pages,
        )

        for (keyword, category), search_results_list in results.items():
            for search_results in search_results_list:
                listings = parser.parse_search_results(search_results, keyword)
                all_listings.extend(listings)

        return all_listings

    return asyncio.run(_run())


# Test function
async def test_mercari_search():
    """Test function to verify Mercari search is working."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    scraper = MercariScraper()
    parser = MercariParser()

    # Test with a single keyword
    keyword = "希少"
    category = MERCARI_CATEGORIES["wheels_only"]

    print(f"\n{'='*60}")
    print(f"Testing Mercari search for: {keyword}")
    print(f"Category: {category}")
    print(f"{'='*60}\n")

    results = await scraper.search(
        keyword=keyword,
        category=category,
        price_min=5000,
        price_max=2000000,
    )

    if results:
        print(f"SUCCESS: Found {results.meta.num_found} total results")
        print(f"Items on this page: {len(results.items)}")

        listings = parser.parse_search_results(results, keyword)
        print(f"Parsed {len(listings)} listings")

        if listings:
            print("\nFirst 3 listings:")
            for listing in listings[:3]:
                print(f"  - {listing.title[:50]}... @ {listing.current_price:,}円")
                print(f"    URL: {listing.listing_url}")

        return results
    else:
        print("FAILED: No response received")
        return None


if __name__ == "__main__":
    asyncio.run(test_mercari_search())
