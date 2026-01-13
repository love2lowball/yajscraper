#!/usr/bin/env python3
"""
YAJScraper - Yahoo Auctions Japan Wheel Scraper

Entry point for running the scraper.
"""

import argparse
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
from src.database import ListingsDatabase
from src.notifier import DiscordNotifier


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
        description="Scrape Yahoo Auctions Japan for rare JDM wheels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py                         # Run with all default keywords
    python run.py --keywords "希少,メッキ" # Specific keywords only
    python run.py --dry-run               # No Discord notifications
    python run.py --verbose               # Debug logging
    python run.py --test-webhook          # Test Discord connection
        """,
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

    return parser.parse_args()


def get_keywords(args: argparse.Namespace) -> list[str]:
    """Get keywords to search based on arguments."""
    if args.keywords:
        return [k.strip() for k in args.keywords.split(",")]
    return config.PRIMARY_KEYWORDS


def get_categories(args: argparse.Namespace) -> list[str]:
    """Get categories to search based on arguments."""
    cat_arg = args.categories.lower()

    if cat_arg == "both":
        return list(config.CATEGORIES.values())
    elif cat_arg == "tire_wheel_sets":
        return [config.CATEGORIES["tire_wheel_sets"]]
    else:
        return [config.CATEGORIES["wheels_only"]]


def run_scraper(
    keywords: list[str],
    categories: list[str],
    dry_run: bool = False,
    logger: logging.Logger = None,
) -> int:
    """
    Main scraper execution.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    if logger is None:
        logger = logging.getLogger("yajscraper")

    logger.info("=" * 60)
    logger.info("YAJScraper starting")
    logger.info(f"Keywords: {len(keywords)}")
    logger.info(f"Categories: {categories}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)

    scraper = YahooAuctionsScraper()
    parser = YahooAuctionsParser()
    notifier = DiscordNotifier()

    all_listings = []
    failed_searches = []

    # Run searches
    total_searches = len(keywords) * len(categories)
    current = 0

    for keyword in keywords:
        for category in categories:
            current += 1
            logger.info(f"[{current}/{total_searches}] Searching '{keyword}' in {category}")

            try:
                html = scraper.search(keyword, category)

                if html:
                    listings = parser.parse_search_results(html, keyword)
                    logger.info(f"  Found {len(listings)} listings")
                    all_listings.extend(listings)
                else:
                    logger.warning(f"  No response received")
                    failed_searches.append((keyword, category))

            except Exception as e:
                logger.error(f"  Search failed: {e}")
                failed_searches.append((keyword, category))

    logger.info(f"Total listings found: {len(all_listings)}")

    if failed_searches:
        logger.warning(f"Failed searches: {len(failed_searches)}")
        for kw, cat in failed_searches:
            logger.warning(f"  - {kw} in {cat}")

    # Deduplicate and store
    with ListingsDatabase() as db:
        new_listings = db.insert_listings(all_listings)
        stats = db.get_stats()

        logger.info(f"New listings: {len(new_listings)}")
        logger.info(f"Database stats: {stats}")

        # Send notifications
        if new_listings:
            success = notifier.send_listings(new_listings, stats, dry_run=dry_run)

            if success:
                # Mark as notified
                auction_ids = [
                    l.auction_id if hasattr(l, 'auction_id') else l['auction_id']
                    for l in new_listings
                ]
                db.mark_as_notified(auction_ids)
            else:
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

        # Run main scraper
        keywords = get_keywords(args)
        categories = get_categories(args)

        return run_scraper(
            keywords=keywords,
            categories=categories,
            dry_run=args.dry_run,
            logger=logger,
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
