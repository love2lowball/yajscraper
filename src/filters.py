"""Filtering logic for auction listings."""

import logging
from typing import Union

from .parser import Listing
from . import config

logger = logging.getLogger(__name__)


def filter_listing(listing: Union[Listing, dict]) -> bool:
    """
    Check if a listing passes all filters.

    Args:
        listing: Listing object or dict

    Returns:
        True if listing should be kept, False if filtered out
    """
    # Get title and price
    if isinstance(listing, dict):
        title = listing.get("title", "")
        price = listing.get("current_price", 0)
    else:
        title = listing.title
        price = listing.current_price

    title_lower = title.lower()

    # Check exclude keywords
    for exclude in config.EXCLUDE_KEYWORDS:
        if exclude.lower() in title_lower or exclude in title:
            logger.debug(f"Filtered out (exclude '{exclude}'): {title[:50]}...")
            return False

    # Check price range
    if price < config.MIN_PRICE:
        logger.debug(f"Filtered out (price {price} < {config.MIN_PRICE}): {title[:50]}...")
        return False

    if price > config.MAX_PRICE:
        logger.debug(f"Filtered out (price {price} > {config.MAX_PRICE}): {title[:50]}...")
        return False

    # Check require keywords (if any are set)
    if config.REQUIRE_KEYWORDS:
        found = False
        for require in config.REQUIRE_KEYWORDS:
            if require.lower() in title_lower or require in title:
                found = True
                break
        if not found:
            logger.debug(f"Filtered out (missing required keyword): {title[:50]}...")
            return False

    return True


def filter_listings(listings: list[Union[Listing, dict]]) -> list[Union[Listing, dict]]:
    """
    Filter a list of listings, returning only those that pass all filters.

    Args:
        listings: List of Listing objects or dicts

    Returns:
        Filtered list
    """
    original_count = len(listings)
    filtered = [l for l in listings if filter_listing(l)]
    removed_count = original_count - len(filtered)

    if removed_count > 0:
        logger.info(f"Filtered out {removed_count} listings ({len(filtered)} remaining)")

    return filtered


def get_filter_stats(listings: list[Union[Listing, dict]]) -> dict:
    """
    Get statistics on what would be filtered.

    Args:
        listings: List of listings to analyze

    Returns:
        Dict with filter statistics
    """
    stats = {
        "total": len(listings),
        "passed": 0,
        "excluded_keyword": 0,
        "price_too_low": 0,
        "price_too_high": 0,
        "missing_required": 0,
        "exclude_reasons": {},
    }

    for listing in listings:
        if isinstance(listing, dict):
            title = listing.get("title", "")
            price = listing.get("current_price", 0)
        else:
            title = listing.title
            price = listing.current_price

        title_lower = title.lower()
        filtered = False

        # Check excludes
        for exclude in config.EXCLUDE_KEYWORDS:
            if exclude.lower() in title_lower or exclude in title:
                stats["excluded_keyword"] += 1
                stats["exclude_reasons"][exclude] = stats["exclude_reasons"].get(exclude, 0) + 1
                filtered = True
                break

        if not filtered and price < config.MIN_PRICE:
            stats["price_too_low"] += 1
            filtered = True

        if not filtered and price > config.MAX_PRICE:
            stats["price_too_high"] += 1
            filtered = True

        if not filtered and config.REQUIRE_KEYWORDS:
            found = any(r.lower() in title_lower or r in title for r in config.REQUIRE_KEYWORDS)
            if not found:
                stats["missing_required"] += 1
                filtered = True

        if not filtered:
            stats["passed"] += 1

    return stats
