"""HTML parsing for Yahoo Auctions Japan search results."""

import re
import logging
import traceback
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from .base import BaseParser, Listing

logger = logging.getLogger(__name__)


class YahooAuctionsParser(BaseParser):
    """Parses Yahoo Auctions Japan search result pages."""

    PLATFORM_NAME = "yahoo_auctions"

    def __init__(self):
        self.listing_url_base = "https://page.auctions.yahoo.co.jp/jp/auction"

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

        # Yahoo Auctions uses different container classes
        # Try multiple selectors for robustness
        # Note: Yahoo changed from "Product" to "Item" classes in 2025
        product_containers = (
            soup.select("li.Item") or  # New structure (2025+)
            soup.select(".Result__items > li") or  # Alternative new selector
            soup.select(".Product") or  # Old structure
            soup.select(".ProductList .Product") or
            soup.select("[data-auction-id]") or
            soup.select(".SearchResults .Product")
        )

        if not product_containers:
            # Fallback: look for anchor tags with auction links
            product_containers = self._find_product_containers_fallback(soup)

        logger.info(f"Found {len(product_containers)} product containers")

        for i, container in enumerate(product_containers):
            try:
                listing = self._parse_single_listing(container, search_keyword, scraped_at)
                if listing:
                    listings.append(listing)
            except Exception as e:
                # Log full details for debugging when Yahoo changes their HTML
                logger.warning(
                    f"Failed to parse listing {i+1}/{len(product_containers)}: {e}\n"
                    f"Traceback: {traceback.format_exc()}\n"
                    f"Container HTML (first 500 chars): {str(container)[:500]}"
                )
                continue

        logger.info(f"Successfully parsed {len(listings)} listings from {len(product_containers)} containers")
        return listings

    def _find_product_containers_fallback(self, soup: BeautifulSoup) -> list:
        """Fallback method to find product containers."""
        containers = []

        # Look for links to auction pages
        auction_links = soup.find_all("a", href=re.compile(r"/jp/auction/[a-zA-Z0-9]+"))

        for link in auction_links:
            # Get parent container that likely holds all listing info
            parent = link.find_parent("li") or link.find_parent("div", class_=True)
            if parent and parent not in containers:
                containers.append(parent)

        return containers

    def _parse_single_listing(
        self,
        container,
        search_keyword: str,
        scraped_at: datetime
    ) -> Optional[Listing]:
        """Parse a single listing container."""

        # Extract auction ID
        auction_id = self._extract_auction_id(container)
        if not auction_id:
            logger.debug("Skipping container: no auction ID found")
            return None

        # Extract title
        title = self._extract_title(container)
        if not title:
            logger.debug(f"Skipping auction {auction_id}: no title found")
            return None

        # Extract prices
        current_price = self._extract_current_price(container)
        buyout_price = self._extract_buyout_price(container)

        # Extract bids
        bids = self._extract_bids(container)

        # Extract time info
        time_remaining = self._extract_time_remaining(container)
        end_time = self._parse_end_time(time_remaining)

        # Extract seller info
        seller_id = self._extract_seller_id(container)
        seller_rating = self._extract_seller_rating(container)

        # Extract thumbnail
        thumbnail_url = self._extract_thumbnail(container)

        # Build listing URL
        listing_url = f"{self.listing_url_base}/{auction_id}"

        return Listing(
            listing_id=auction_id,
            platform=self.PLATFORM_NAME,
            title=title,
            current_price=current_price,
            currency="JPY",
            buyout_price=buyout_price,
            bids=bids,
            time_remaining=time_remaining,
            end_time=end_time,
            seller_id=seller_id,
            seller_rating=seller_rating,
            thumbnail_url=thumbnail_url,
            listing_url=listing_url,
            search_keyword=search_keyword,
            scraped_at=scraped_at,
        )

    def _extract_auction_id(self, container) -> Optional[str]:
        """Extract the unique auction ID."""
        # Try data attribute first
        if container.get("data-auction-id"):
            return container["data-auction-id"]

        # Try finding in links
        link = container.find("a", href=re.compile(r"/jp/auction/([a-zA-Z0-9]+)"))
        if link:
            match = re.search(r"/jp/auction/([a-zA-Z0-9]+)", link["href"])
            if match:
                return match.group(1)

        # Try data-cl-params attribute
        elem = container.find(attrs={"data-cl-params": True})
        if elem:
            match = re.search(r"auc_id=([a-zA-Z0-9]+)", elem.get("data-cl-params", ""))
            if match:
                return match.group(1)

        return None

    def _extract_title(self, container) -> Optional[str]:
        """Extract the listing title."""
        # First try data attribute (most reliable in new structure)
        elem_with_title = container.find(attrs={"data-auction-title": True})
        if elem_with_title:
            title = elem_with_title.get("data-auction-title")
            if title and len(title) > 3:
                return title

        # Try common title selectors (new Item classes first, then old Product classes)
        title_selectors = [
            ".Item__title",  # New structure (2025+)
            ".Item__link",  # New structure link element
            ".Product__title",  # Old structure
            ".Product__titleLink",
            "[data-auction-title]",
            "h3 a",
            ".ProductList__title a",
            "a[href*='/jp/auction/']",
        ]

        for selector in title_selectors:
            elem = container.select_one(selector)
            if elem:
                title = elem.get_text(strip=True)
                if title and len(title) > 3:  # Filter out empty/short titles
                    return title

        return None

    def _extract_current_price(self, container) -> int:
        """Extract current bid price in yen."""
        # First try data attribute (most reliable in new structure)
        elem_with_price = container.find(attrs={"data-auction-price": True})
        if elem_with_price:
            price_str = elem_with_price.get("data-auction-price")
            if price_str:
                try:
                    return int(price_str)
                except ValueError:
                    pass

        # Try selectors (new Item classes first, then old Product classes)
        price_selectors = [
            ".Item__priceValue",  # New structure (2025+)
            ".Item__price",  # New structure
            ".Product__priceValue",  # Old structure
            ".Product__price",
            "[data-auction-price]",
            ".Price__value",
        ]

        for selector in price_selectors:
            elem = container.select_one(selector)
            if elem:
                price = self._parse_price(elem.get_text())
                if price is not None:
                    return price

        # Fallback: search for yen pattern in container text
        text = container.get_text()
        match = re.search(r"[¥￥]?\s*([\d,]+)\s*円", text)
        if match:
            return int(match.group(1).replace(",", ""))

        return 0

    def _extract_buyout_price(self, container) -> Optional[int]:
        """Extract buy-it-now price if available."""
        buyout_selectors = [
            ".Product__buyoutPrice",
            ".Product__priceBuyout",
            "[data-auction-buyout]",
            ".Price--buyout",
        ]

        for selector in buyout_selectors:
            elem = container.select_one(selector)
            if elem:
                price = self._parse_price(elem.get_text())
                if price is not None:
                    return price

        # Look for 即決 (sokketsu = buy now) pattern
        text = container.get_text()
        match = re.search(r"即決[:\s]*[¥￥]?\s*([\d,]+)", text)
        if match:
            return int(match.group(1).replace(",", ""))

        return None

    def _parse_price(self, text: str) -> Optional[int]:
        """Parse a price string into integer yen."""
        if not text:
            return None

        # Remove currency symbols and whitespace
        clean = re.sub(r"[¥￥円\s,]", "", text)

        # Handle empty result
        if not clean:
            return None

        # Extract digits only
        match = re.search(r"(\d+)", clean)
        if match:
            return int(match.group(1))

        return None

    def _extract_bids(self, container) -> int:
        """Extract number of bids."""
        bid_selectors = [
            ".Item__bid .Item__text",  # New structure (2025+)
            ".Item__bid",  # New structure
            ".Product__bid",  # Old structure
            ".Product__bidCount",
            "[data-auction-bids]",
        ]

        for selector in bid_selectors:
            elem = container.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                # Skip "-" which means no bids
                if text == "-":
                    return 0
                match = re.search(r"(\d+)", text)
                if match:
                    return int(match.group(1))

        return 0

    def _extract_time_remaining(self, container) -> str:
        """Extract time remaining string."""
        time_selectors = [
            ".Item__time .Item__text",  # New structure (2025+)
            ".Item__time",  # New structure
            ".Product__time",  # Old structure
            ".Product__timeRemaining",
            "[data-auction-time]",
        ]

        for selector in time_selectors:
            elem = container.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Look for time patterns in text
        text = container.get_text()

        # Match patterns like "残り 2日" or "5時間"
        patterns = [
            r"残り\s*(\d+日\s*\d*時間?)",
            r"残り\s*(\d+時間)",
            r"(\d+日)",
            r"(\d+時間)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return ""

    def _parse_end_time(self, time_remaining: str) -> Optional[datetime]:
        """Convert time remaining string to end datetime."""
        if not time_remaining:
            return None

        now = datetime.now()

        # Parse days
        days = 0
        days_match = re.search(r"(\d+)\s*日", time_remaining)
        if days_match:
            days = int(days_match.group(1))

        # Parse hours
        hours = 0
        hours_match = re.search(r"(\d+)\s*時間", time_remaining)
        if hours_match:
            hours = int(hours_match.group(1))

        # Parse minutes
        minutes = 0
        minutes_match = re.search(r"(\d+)\s*分", time_remaining)
        if minutes_match:
            minutes = int(minutes_match.group(1))

        if days or hours or minutes:
            return now + timedelta(days=days, hours=hours, minutes=minutes)

        return None

    def _extract_seller_id(self, container) -> str:
        """Extract seller username."""
        # Try data attribute first (new structure uses encoded seller ID)
        elem_with_seller = container.find(attrs={"data-auction-auc-seller-id": True})
        if elem_with_seller:
            seller_id = elem_with_seller.get("data-auction-auc-seller-id")
            if seller_id:
                return seller_id

        seller_selectors = [
            ".Item__seller a",  # New structure (2025+)
            ".Item__sellerName",  # New structure
            ".Product__seller a",  # Old structure
            ".Product__sellerName",
            "[data-auction-seller]",
            ".Seller__name",
        ]

        for selector in seller_selectors:
            elem = container.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Try finding seller link pattern
        link = container.find("a", href=re.compile(r"/seller/|/rating\?"))
        if link:
            return link.get_text(strip=True)

        return ""

    def _extract_seller_rating(self, container) -> str:
        """Extract seller rating/feedback score."""
        # Try to extract from data-cl-params (new structure has grat=99.6 format)
        elem_with_params = container.find(attrs={"data-cl-params": True})
        if elem_with_params:
            params = elem_with_params.get("data-cl-params", "")
            # Look for grat (good rating percentage)
            match = re.search(r"grat:([\d.]+)", params)
            if match:
                return match.group(1)

        rating_selectors = [
            ".Item__sellerRating",  # New structure (2025+)
            ".Item__rating",  # New structure
            ".Product__sellerRating",  # Old structure
            ".Seller__rating",
            "[data-auction-rating]",
        ]

        for selector in rating_selectors:
            elem = container.select_one(selector)
            if elem:
                return elem.get_text(strip=True)

        # Look for rating pattern (number in parentheses)
        text = container.get_text()
        match = re.search(r"[\(（](\d+)[\)）]", text)
        if match:
            return match.group(1)

        return ""

    def _extract_thumbnail(self, container) -> str:
        """Extract thumbnail image URL."""
        # First try data attribute (most reliable in new structure)
        elem_with_img = container.find(attrs={"data-auction-img": True})
        if elem_with_img:
            img_url = elem_with_img.get("data-auction-img")
            if img_url:
                return img_url

        img_selectors = [
            "img.Item__imageData",  # New structure (2025+)
            ".Item__image img",  # New structure
            ".Product__imageData img",  # Old structure
            ".Product__image img",
            "img[src*='auctions.c.yimg.jp']",
            "img",
        ]

        for selector in img_selectors:
            elem = container.select_one(selector)
            if elem:
                src = elem.get("src") or elem.get("data-src")
                if src and ("yimg" in src or "yahoo" in src):
                    return src

        return ""

    def get_result_count(self, html: str) -> int:
        """Extract total number of search results."""
        soup = BeautifulSoup(html, "lxml")

        # Look for result count element (new structure first)
        count_selectors = [
            ".Tab__subText",  # New structure (2025+) - shows "24,233件"
            ".SearchResult__count",  # Old structure
            ".ResultCount__number",
            "[data-result-count]",
        ]

        for selector in count_selectors:
            elem = soup.select_one(selector)
            if elem:
                match = re.search(r"([\d,]+)", elem.get_text())
                if match:
                    count = int(match.group(1).replace(",", ""))
                    # Sanity check - return only if it's a reasonable count
                    if count >= 1:
                        return count

        # Fallback: search for specific pattern in page - look for "X件" at word boundary
        # Avoid matching notification text like "500件以上"
        text = soup.get_text()
        # Look for count in common result display patterns
        patterns = [
            r"全\s*([\d,]+)\s*件",  # "全 24,233件"
            r"約\s*([\d,]+)\s*件",  # "約 24,233件"
            r"([\d,]+)\s*件出品中",  # "24,233件出品中"
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1).replace(",", ""))

        return 0
