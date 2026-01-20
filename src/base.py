"""Base classes for multi-platform scraper support."""

import random
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


@dataclass
class Listing:
    """
    Platform-agnostic listing representation.

    All platform-specific parsers should convert their data to this format.
    """
    # Core identifiers
    listing_id: str              # Unique ID on the platform
    platform: str                # e.g., "yahoo_auctions", "mercari", "jmty", "craigslist"

    # Listing details
    title: str
    current_price: int           # In smallest currency unit (yen, cents)
    currency: str = "JPY"        # ISO 4217 currency code

    # Optional pricing
    buyout_price: Optional[int] = None
    original_price: Optional[int] = None  # For discounted items

    # Auction-specific (may be None for fixed-price platforms)
    bids: int = 0
    time_remaining: str = ""
    end_time: Optional[datetime] = None

    # Seller info
    seller_id: str = ""
    seller_name: str = ""
    seller_rating: str = ""

    # Media
    thumbnail_url: str = ""
    image_urls: list[str] = field(default_factory=list)

    # URLs
    listing_url: str = ""

    # Search context
    search_keyword: str = ""
    category: str = ""

    # Location (useful for Craigslist, JMTY)
    location: str = ""
    region: str = ""

    # Metadata
    scraped_at: datetime = field(default_factory=datetime.now)
    posted_at: Optional[datetime] = None  # When the listing was posted

    # Condition/status
    condition: str = ""          # e.g., "used", "new", "like_new"
    shipping_info: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        if data["end_time"]:
            data["end_time"] = data["end_time"].isoformat()
        data["scraped_at"] = data["scraped_at"].isoformat()
        if data["posted_at"]:
            data["posted_at"] = data["posted_at"].isoformat()
        # Convert list to comma-separated string for simple storage
        data["image_urls"] = ",".join(data["image_urls"]) if data["image_urls"] else ""
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Listing":
        """Create a Listing from a dictionary."""
        # Handle datetime conversion
        if isinstance(data.get("end_time"), str) and data["end_time"]:
            data["end_time"] = datetime.fromisoformat(data["end_time"])
        if isinstance(data.get("scraped_at"), str):
            data["scraped_at"] = datetime.fromisoformat(data["scraped_at"])
        if isinstance(data.get("posted_at"), str) and data["posted_at"]:
            data["posted_at"] = datetime.fromisoformat(data["posted_at"])
        # Handle image_urls conversion
        if isinstance(data.get("image_urls"), str):
            data["image_urls"] = data["image_urls"].split(",") if data["image_urls"] else []
        return cls(**data)


class BaseScraper(ABC):
    """
    Abstract base class for platform scrapers.

    Provides common functionality for HTTP requests, rate limiting,
    and retry logic. Platform-specific scrapers should inherit from this.
    """

    # Override these in subclasses
    PLATFORM_NAME: str = "base"
    BASE_URL: str = ""
    RESULTS_PER_PAGE: int = 100

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        request_timeout: int = 30,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ):
        self.session = requests.Session()
        self.proxy_url = proxy_url
        self.request_timeout = request_timeout
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        if self.proxy_url:
            self.session.proxies = {
                "http": self.proxy_url,
                "https": self.proxy_url,
            }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the session and release resources."""
        if self.session:
            self.session.close()

    @abstractmethod
    def get_user_agents(self) -> list[str]:
        """Return list of user agent strings to rotate through."""
        pass

    def _get_random_user_agent(self) -> str:
        """Return a random user agent string."""
        return random.choice(self.get_user_agents())

    @abstractmethod
    def get_headers(self) -> dict:
        """Return headers for requests. Override for platform-specific headers."""
        pass

    def random_delay(self) -> None:
        """Sleep for a random duration between requests."""
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug(f"Sleeping for {delay:.2f} seconds")
        time.sleep(delay)

    def request_with_retry(self, url: str, method: str = "GET", **kwargs) -> Optional[requests.Response]:
        """
        Make an HTTP request with retry logic and exponential backoff.

        Args:
            url: The URL to request
            method: HTTP method (GET, POST, etc.)
            **kwargs: Additional arguments passed to requests

        Returns:
            Response object or None on failure
        """
        for attempt in range(self.max_retries):
            try:
                kwargs.setdefault("headers", self.get_headers())
                kwargs.setdefault("timeout", self.request_timeout)

                response = self.session.request(method, url, **kwargs)

                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = self.backoff_factor ** (attempt + 1)
                    logger.warning(f"Rate limited (429). Waiting {wait_time}s before retry.")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                wait_time = self.backoff_factor ** attempt
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")

                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {self.max_retries} attempts failed for URL: {url}")
                    return None

        return None

    @abstractmethod
    def build_search_url(self, keyword: str, category: str = "", page: int = 1, **kwargs) -> str:
        """
        Build a search URL for the platform.

        Args:
            keyword: Search term
            category: Category ID or name
            page: Page number (1-indexed)
            **kwargs: Platform-specific parameters

        Returns:
            Full search URL
        """
        pass

    @abstractmethod
    def search(self, keyword: str, category: str = "", page: int = 1) -> Optional[str]:
        """
        Execute a search and return the response content.

        Args:
            keyword: Search term
            category: Category ID or name
            page: Page number

        Returns:
            Response content (HTML, JSON, etc.) or None on failure
        """
        pass

    def search_all_pages(
        self,
        keyword: str,
        category: str = "",
        max_pages: int = 10,
        get_total_results: callable = None,
    ) -> list[str]:
        """
        Search through all pages of results.

        Args:
            keyword: Search term
            category: Category ID
            max_pages: Maximum pages to fetch (safety limit)
            get_total_results: Optional callable that takes response content
                              and returns total result count

        Returns:
            List of response contents from all pages
        """
        results = []
        page = 1
        total_results = None

        while page <= max_pages:
            logger.info(f"Fetching page {page} for '{keyword}'")

            content = self.search(keyword, category, page=page)
            if not content:
                break

            results.append(content)

            # Determine if more pages exist
            if get_total_results and total_results is None:
                total_results = get_total_results(content)
                if total_results:
                    total_pages = (total_results + self.RESULTS_PER_PAGE - 1) // self.RESULTS_PER_PAGE
                    max_pages = min(max_pages, total_pages)
                    logger.info(f"Total results: {total_results}, pages: {total_pages}")

            if page >= max_pages:
                break

            page += 1
            self.random_delay()

        return results


class BaseParser(ABC):
    """
    Abstract base class for platform parsers.

    Handles parsing of platform-specific response formats into
    standardized Listing objects.
    """

    PLATFORM_NAME: str = "base"

    @abstractmethod
    def parse_search_results(self, content: str, search_keyword: str = "") -> list[Listing]:
        """
        Parse search results into Listing objects.

        Args:
            content: Raw response content (HTML, JSON, etc.)
            search_keyword: The keyword used for this search

        Returns:
            List of Listing objects
        """
        pass

    @abstractmethod
    def get_result_count(self, content: str) -> int:
        """
        Extract total number of search results from response.

        Args:
            content: Raw response content

        Returns:
            Total result count, or 0 if not found
        """
        pass

    def parse_listing_page(self, content: str) -> Optional[Listing]:
        """
        Parse an individual listing page for detailed info.

        Override this for platforms where you need to fetch
        individual listing pages for more details.

        Args:
            content: Raw listing page content

        Returns:
            Listing object or None
        """
        raise NotImplementedError("Subclass must implement parse_listing_page")
