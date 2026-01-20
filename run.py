#!/usr/bin/env python3
"""
Multi-Platform JDM Wheel Scraper

Entry point for running scrapers for Yahoo Auctions Japan and Mercari Japan.
"""

import argparse
import asyncio
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import config
from src.scraper import YahooAuctionsScraper
from src.parser import YahooAuctionsParser
from src.mercari import MercariScraper, MercariParser, MERCARI_CATEGORIES
from src.jmty import JMTYScraper, JMTYParser, JMTY_CATEGORIES
from src.craigslist import CraigslistScraper, CraigslistParser, CRAIGSLIST_CITIES
from src.database import ListingsDatabase
from src.notifier import DiscordNotifier
from src.filters import filter_listings, get_filter_stats


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging."""
    log_level = logging.DEBUG if verbose else getattr(logging, config.LOG_LEVEL, logging.INFO)

    # Create logs directory
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Log file with date
    log_file = config.LOGS_DIR / f"scraper_{datetime.now().strftime('%Y%m%d')}.log"

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger = logging.getLogger("yajscraper")
    logger.info(f"Logging to {log_file}")

    return logger


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape Yahoo Auctions Japan and Mercari Japan for rare JDM wheels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py                              # Run Yahoo Auctions (default, 1 day filter)
    python run.py --platform mercari           # Run Mercari Japan only
    python run.py --platform both              # Run both platforms
    python run.py --keywords "BBS,SSR"         # Specific keywords only
    python run.py --max-days 7                 # Include listings from past 7 days
    python run.py --dry-run                    # No Discord notifications
    python run.py --verbose                    # Debug logging
    python run.py --test-webhook               # Test Discord connection
        """,
    )

    parser.add_argument(
        "--platform",
        type=str,
        default="yahoo",
        choices=["yahoo", "mercari", "jmty", "craigslist", "japan", "us", "all"],
        help="Platform to scrape: yahoo, mercari, jmty, craigslist, japan (JP platforms), us (Craigslist), or all (default: yahoo)",
    )

    parser.add_argument(
        "--keywords",
        type=str,
        help="Comma-separated keywords to search (overrides defaults)",
    )

    parser.add_argument(
        "--categories",
        type=str,
        default="wheels_only",
        help="Categories to search: wheels_only, tire_wheel_sets, or both (default: wheels_only)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending Discord notifications",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Send a test message to Discord and exit",
    )

    parser.add_argument(
        "--cleanup",
        type=int,
        metavar="DAYS",
        help="Delete listings older than N days and exit",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics and exit",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Maximum pages to fetch per keyword/category for Yahoo (default: 1 for 12-hour runs)",
    )

    parser.add_argument(
        "--mercari-max-pages",
        type=int,
        default=5,
        help="Maximum pages to fetch per keyword/category for Mercari (default: 5, stops after 2 consecutive pages with no new listings)",
    )

    parser.add_argument(
        "--jmty-max-pages",
        type=int,
        default=1,
        help="Maximum pages to fetch per keyword for JMTY (default: 1 for 12-hour runs)",
    )

    parser.add_argument(
        "--craigslist-max-pages",
        type=int,
        default=1,
        help="Maximum pages to fetch per city/keyword for Craigslist (default: 1 for 12-hour runs)",
    )

    parser.add_argument(
        "--craigslist-cities",
        type=str,
        help="Comma-separated list of Craigslist cities to search (default: all major US cities)",
    )

    parser.add_argument(
        "--us-keywords",
        type=str,
        help="Comma-separated keywords for US Craigslist search (overrides config)",
    )

    parser.add_argument(
        "--max-days",
        type=int,
        default=1,
        help="Only include listings from the past N days (default: 1 for daily runs)",
    )

    return parser.parse_args()


def get_keywords(args: argparse.Namespace) -> list[str]:
    """Get keywords to search based on arguments (for Japan platforms)."""
    if args.keywords:
        return [k.strip() for k in args.keywords.split(",")]
    return config.PRIMARY_KEYWORDS


def get_us_keywords(args: argparse.Namespace) -> list[str]:
    """Get keywords for US Craigslist search."""
    if args.us_keywords:
        return [k.strip() for k in args.us_keywords.split(",")]
    return config.US_PRIMARY_KEYWORDS


def get_craigslist_cities(args: argparse.Namespace) -> list[str]:
    """Get Craigslist cities to search."""
    if args.craigslist_cities:
        return [c.strip() for c in args.craigslist_cities.split(",")]
    return CRAIGSLIST_CITIES


def get_yahoo_categories(args: argparse.Namespace) -> list[str]:
    """Get Yahoo Auctions categories to search based on arguments."""
    cat_arg = args.categories.lower()

    if cat_arg == "both":
        return list(config.CATEGORIES.values())
    elif cat_arg == "tire_wheel_sets":
        return [config.CATEGORIES["tire_wheel_sets"]]
    else:
        return [config.CATEGORIES["wheels_only"]]


def get_mercari_categories(args: argparse.Namespace) -> list[int]:
    """Get Mercari categories to search based on arguments."""
    cat_arg = args.categories.lower()

    if cat_arg == "both":
        return list(MERCARI_CATEGORIES.values())
    elif cat_arg == "tire_wheel_sets":
        return [MERCARI_CATEGORIES["tire_wheel_sets"]]
    else:
        return [MERCARI_CATEGORIES["wheels_only"]]


def run_yahoo_scraper(
    keywords: list[str],
    categories: list[str],
    max_pages: int = 1,
    db=None,
    logger: logging.Logger = None,
) -> list:
    """
    Run Yahoo Auctions scraper.

    Args:
        keywords: Search terms
        categories: Category IDs
        max_pages: Max pages per keyword (default 2 for frequent runs)
        db: Database instance for duplicate-based early termination
        logger: Logger instance

    Returns:
        List of Listing objects
    """
    if logger is None:
        logger = logging.getLogger("yajscraper")

    logger.info("-" * 40)
    logger.info("Yahoo Auctions Japan")
    logger.info("-" * 40)

    parser = YahooAuctionsParser()
    all_listings = []
    failed_searches = []

    # Use context manager to ensure session is closed
    with YahooAuctionsScraper() as scraper:
        total_searches = len(keywords) * len(categories)
        current = 0

        for keyword in keywords:
            for category in categories:
                current += 1
                logger.info(f"[Yahoo {current}/{total_searches}] Searching '{keyword}' in {category}")

                try:
                    html_pages = scraper.search_with_pagination(
                        keyword,
                        category,
                        max_pages=max_pages,
                        parser=parser,
                        db=db,
                    )

                    if html_pages:
                        keyword_listings = []
                        for page_num, html in enumerate(html_pages, 1):
                            listings = parser.parse_search_results(html, keyword)
                            keyword_listings.extend(listings)

                        logger.info(f"  Found {len(keyword_listings)} listings across {len(html_pages)} page(s)")
                        all_listings.extend(keyword_listings)
                    else:
                        logger.warning(f"  No response received")
                        failed_searches.append(("yahoo", keyword, category))

                except Exception as e:
                    logger.error(f"  Search failed: {e}")
                    logger.debug(traceback.format_exc())
                    failed_searches.append(("yahoo", keyword, category))

    logger.info(f"Yahoo Auctions: {len(all_listings)} listings found")

    if failed_searches:
        logger.warning(f"Yahoo failed searches: {len(failed_searches)}")

    return all_listings


async def run_mercari_scraper_async(
    keywords: list[str],
    categories: list[int],
    max_pages: int = 5,
    max_age_days: int = None,
    logger: logging.Logger = None,
) -> list:
    """
    Run Mercari scraper (async).

    Returns:
        List of Listing objects
    """
    if logger is None:
        logger = logging.getLogger("yajscraper")

    logger.info("-" * 40)
    logger.info("Mercari Japan")
    logger.info("-" * 40)

    scraper = MercariScraper()
    parser = MercariParser()
    all_listings = []

    try:
        results = await scraper.search_all_keywords(
            keywords=keywords,
            categories=categories,
            price_min=config.MIN_PRICE,
            price_max=config.MAX_PRICE,
            max_pages_per_search=max_pages,
            max_age_days=max_age_days,
        )

        for (keyword, category), search_results_list in results.items():
            for search_results in search_results_list:
                listings = parser.parse_search_results(search_results, keyword)
                all_listings.extend(listings)

    except Exception as e:
        logger.error(f"Mercari scraper failed: {e}")
        logger.debug(traceback.format_exc())

    logger.info(f"Mercari: {len(all_listings)} listings found")
    return all_listings


def run_mercari_scraper(
    keywords: list[str],
    categories: list[int],
    max_pages: int = 5,
    max_age_days: int = None,
    logger: logging.Logger = None,
) -> list:
    """Synchronous wrapper for Mercari scraper."""
    return asyncio.run(run_mercari_scraper_async(keywords, categories, max_pages, max_age_days, logger))


def run_jmty_scraper(
    keywords: list[str],
    max_pages: int = 1,
    db=None,
    logger: logging.Logger = None,
) -> list:
    """
    Run JMTY scraper.

    Args:
        keywords: Search terms
        max_pages: Max pages per keyword (default 2 for frequent runs)
        db: Database instance for duplicate-based early termination
        logger: Logger instance

    Returns:
        List of Listing objects
    """
    if logger is None:
        logger = logging.getLogger("yajscraper")

    logger.info("-" * 40)
    logger.info("JMTY (Jimoty)")
    logger.info("-" * 40)

    parser = JMTYParser()
    all_listings = []

    category = JMTY_CATEGORIES["tire_wheel"]

    with JMTYScraper() as scraper:
        total_searches = len(keywords)
        current = 0

        for keyword in keywords:
            current += 1
            logger.info(f"[JMTY {current}/{total_searches}] Searching '{keyword}'")

            try:
                html_pages = scraper.search_with_pagination(
                    keyword=keyword,
                    category=category,
                    region="all",
                    price_min=config.MIN_PRICE,
                    price_max=config.MAX_PRICE,
                    max_pages=max_pages,
                    parser=parser,
                    db=db,
                )

                if html_pages:
                    keyword_listings = []
                    for page_num, html in enumerate(html_pages, 1):
                        listings = parser.parse_search_results(html, keyword)
                        keyword_listings.extend(listings)

                    logger.info(f"  Found {len(keyword_listings)} listings across {len(html_pages)} page(s)")
                    all_listings.extend(keyword_listings)
                else:
                    logger.warning(f"  No response received")

            except Exception as e:
                logger.error(f"  Search failed: {e}")
                logger.debug(traceback.format_exc())

    logger.info(f"JMTY: {len(all_listings)} listings found")
    return all_listings


def run_craigslist_scraper(
    keywords: list[str],
    cities: list[str],
    max_pages: int = 1,
    db=None,
    logger: logging.Logger = None,
) -> list:
    """
    Run Craigslist US scraper.

    Args:
        keywords: Search terms
        cities: Craigslist city subdomains
        max_pages: Max pages per city (default 2 for frequent runs)
        db: Database instance for duplicate-based early termination
        logger: Logger instance

    Returns:
        List of Listing objects
    """
    if logger is None:
        logger = logging.getLogger("yajscraper")

    logger.info("-" * 40)
    logger.info("Craigslist US")
    logger.info("-" * 40)
    logger.info(f"Searching {len(cities)} cities with {len(keywords)} keywords")

    parser = CraigslistParser()
    all_listings = []

    with CraigslistScraper() as scraper:
        results = scraper.search_all_cities(
            keywords=keywords,
            cities=cities,
            categories=["wta"],  # wheels+tires
            price_min=config.US_MIN_PRICE,
            price_max=config.US_MAX_PRICE,
            max_pages_per_city=max_pages,
            parser=parser,
            db=db,
        )

        for (city, keyword, category), html_pages in results.items():
            for html in html_pages:
                listings = parser.parse_search_results(html, keyword, city)
                all_listings.extend(listings)

    logger.info(f"Craigslist: {len(all_listings)} listings found")
    return all_listings


def run_scraper(
    keywords: list[str],
    yahoo_categories: list[str],
    mercari_categories: list[int],
    platforms: list[str],
    dry_run: bool = False,
    logger: logging.Logger = None,
    yahoo_max_pages: int = 1,
    mercari_max_pages: int = 5,
    jmty_max_pages: int = 1,
    us_keywords: list[str] = None,
    craigslist_cities: list[str] = None,
    craigslist_max_pages: int = 1,
    max_days: int = 1,
) -> int:
    """
    Main scraper execution.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    if logger is None:
        logger = logging.getLogger("yajscraper")

    logger.info("=" * 60)
    logger.info("Multi-Platform Wheel Scraper")
    logger.info(f"Platforms: {', '.join(platforms)}")
    if keywords and any(p in platforms for p in ["yahoo", "mercari", "jmty"]):
        logger.info(f"Japan Keywords: {len(keywords)}")
    if us_keywords and "craigslist" in platforms:
        logger.info(f"US Keywords: {len(us_keywords)}")
    logger.info(f"Max listing age: {max_days} day(s)")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)

    notifier = DiscordNotifier()
    all_listings = []

    # Open database early for duplicate-based early termination
    with ListingsDatabase() as db:
        # Run Yahoo Auctions scraper
        if "yahoo" in platforms:
            yahoo_listings = run_yahoo_scraper(
                keywords=keywords,
                categories=yahoo_categories,
                max_pages=yahoo_max_pages,
                db=db,
                logger=logger,
            )
            all_listings.extend(yahoo_listings)

        # Run Mercari scraper
        if "mercari" in platforms:
            mercari_listings = run_mercari_scraper(
                keywords=keywords,
                categories=mercari_categories,
                max_pages=mercari_max_pages,
                max_age_days=max_days,
                logger=logger,
            )
            all_listings.extend(mercari_listings)

        # Run JMTY scraper
        if "jmty" in platforms:
            jmty_listings = run_jmty_scraper(
                keywords=keywords,
                max_pages=jmty_max_pages,
                db=db,
                logger=logger,
            )
            all_listings.extend(jmty_listings)

        # Run Craigslist US scraper
        if "craigslist" in platforms:
            if not us_keywords:
                logger.warning("No US keywords configured for Craigslist")
            elif not craigslist_cities:
                logger.warning("No Craigslist cities configured")
            else:
                craigslist_listings = run_craigslist_scraper(
                    keywords=us_keywords,
                    cities=craigslist_cities,
                    max_pages=craigslist_max_pages,
                    db=db,
                    logger=logger,
                )
                all_listings.extend(craigslist_listings)

        logger.info(f"Total listings found across all platforms: {len(all_listings)}")

        # Apply filters
        pre_filter_count = len(all_listings)
        all_listings = filter_listings(all_listings, max_age_days=max_days)
        logger.info(f"After filtering: {len(all_listings)} listings ({pre_filter_count - len(all_listings)} filtered out)")

        # Deduplicate and store (db already open)
        new_listings = db.insert_listings(all_listings)
        stats = db.get_stats()

        logger.info(f"New listings: {len(new_listings)}")
        logger.info(f"Database stats: {stats}")

        # Send notifications
        if new_listings:
            success = notifier.send_listings(new_listings, stats, dry_run=dry_run)

            if success and not dry_run:
                # Mark as notified (only if actually sent)
                auction_ids = []
                for l in new_listings:
                    if hasattr(l, 'listing_id'):
                        auction_ids.append(l.listing_id)
                    elif hasattr(l, 'auction_id'):
                        auction_ids.append(l.auction_id)
                    else:
                        auction_ids.append(l.get('listing_id') or l.get('auction_id'))
                db.mark_as_notified(auction_ids)
            elif not success:
                logger.error("Failed to send some notifications")
                return 1

    # Retry any queued notifications
    if not dry_run:
        notifier.retry_queued()

    logger.info("Scraper completed successfully")
    return 0


def main() -> int:
    """Main entry point."""
    args = parse_args()
    logger = setup_logging(args.verbose)

    try:
        # Handle special commands
        if args.test_webhook:
            notifier = DiscordNotifier()
            if notifier.send_test_message():
                logger.info("Test message sent successfully")
                return 0
            else:
                logger.error("Failed to send test message")
                return 1

        if args.stats:
            with ListingsDatabase() as db:
                stats = db.get_stats()
                print("\nDatabase Statistics:")
                print(f"  Total listings: {stats['total']:,}")
                print(f"  New today: {stats['new_today']:,}")
                print(f"  Unnotified: {stats['unnotified']:,}")
                print(f"  Keywords searched: {stats['keywords_searched']}")
            return 0

        if args.cleanup:
            with ListingsDatabase() as db:
                deleted = db.delete_old_listings(args.cleanup)
                print(f"Deleted {deleted} listings older than {args.cleanup} days")
            return 0

        # Determine platforms to run
        if args.platform == "all":
            platforms = ["yahoo", "mercari", "jmty", "craigslist"]
        elif args.platform == "japan":
            platforms = ["yahoo", "mercari", "jmty"]
        elif args.platform == "us":
            platforms = ["craigslist"]
        elif args.platform == "both":
            # Legacy: "both" means yahoo + mercari
            platforms = ["yahoo", "mercari"]
        else:
            platforms = [args.platform]

        # Get keywords and categories for Japan platforms
        keywords = get_keywords(args)
        yahoo_categories = get_yahoo_categories(args)
        mercari_categories = get_mercari_categories(args)

        # Get keywords and cities for US platforms
        us_keywords = get_us_keywords(args)
        craigslist_cities = get_craigslist_cities(args)

        return run_scraper(
            keywords=keywords,
            yahoo_categories=yahoo_categories,
            mercari_categories=mercari_categories,
            platforms=platforms,
            dry_run=args.dry_run,
            logger=logger,
            yahoo_max_pages=args.max_pages,
            mercari_max_pages=args.mercari_max_pages,
            jmty_max_pages=args.jmty_max_pages,
            us_keywords=us_keywords,
            craigslist_cities=craigslist_cities,
            craigslist_max_pages=args.craigslist_max_pages,
            max_days=args.max_days,
        )

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())

        # Try to send error alert
        try:
            notifier = DiscordNotifier()
            notifier.send_error_alert(f"{type(e).__name__}: {e}")
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())
