"""HTML parsing for Yahoo Auctions Japan search results."""

import re
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Listing:
    """Represents a single auction listing."""
    auction_id: str
    title: str
    current_price: int
    buyout_price: Optional[int]
    bids: int
    time_remaining: str
    end_time: Optional[datetime]
    seller_id: str
    seller_rating: str
    thumbnail_url: str
    listing_url: str
    search_keyword: str
    scraped_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        if data["end_time"]:
            data["end_time"] = data["end_time"].isoformat()
        data["scraped_at"] = data["scraped_at"].isoformat()
        return data


class YahooAuctionsParser:
    """Parses Yahoo Auctions Japan search result pages."""

    def __init__(self):
        self.listing_url_base = "https://page.auctions.yahoo.co.jp/jp/auction"

    def parse_search_results(self, html: str, search_keyword: str) -> list[Listing]:
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
        product_containers = (
            soup.select(".Product") or
            soup.select(".ProductList .Product") or
            soup.select("[data-auction-id]") or
            soup.select(".SearchResults .Product")
        )

        if not product_containers:
            # Fallback: look for anchor tags with auction links
            product_containers = self._find_product_containers_fallback(soup)

        logger.info(f"Found {len(product_containers)} product containers")

        for container in product_containers:
            try:
                listing = self._parse_single_listing(container, search_keyword, scraped_at)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Failed to parse listing: {e}")
                continue

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
            return None

        # Extract title
        title = self._extract_title(container)
        if not title:
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
            auction_id=auction_id,
            title=title,
            current_price=current_price,
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
        # Try common title selectors
        title_selectors = [
            ".Product__title",
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
        price_selectors = [
            ".Product__priceValue",
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
            ".Product__bid",
            ".Product__bidCount",
            "[data-auction-bids]",
        ]

        for selector in bid_selectors:
            elem = container.select_one(selector)
            if elem:
                match = re.search(r"(\d+)", elem.get_text())
                if match:
                    return int(match.group(1))

        return 0

    def _extract_time_remaining(self, container) -> str:
        """Extract time remaining string."""
        time_selectors = [
            ".Product__time",
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
        seller_selectors = [
            ".Product__seller a",
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
        rating_selectors = [
            ".Product__sellerRating",
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
        img_selectors = [
            ".Product__imageData img",
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

        # Look for result count element
        count_selectors = [
            ".SearchResult__count",
            ".ResultCount__number",
            "[data-result-count]",
        ]

        for selector in count_selectors:
            elem = soup.select_one(selector)
            if elem:
                match = re.search(r"([\d,]+)", elem.get_text())
                if match:
                    return int(match.group(1).replace(",", ""))

        # Fallback: search for pattern in page
        text = soup.get_text()
        match = re.search(r"([\d,]+)\s*件", text)
        if match:
            return int(match.group(1).replace(",", ""))

        return 0
