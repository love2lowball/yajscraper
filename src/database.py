"""SQLite database operations for listing storage and deduplication."""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .parser import Listing
from . import config

logger = logging.getLogger(__name__)


class ListingsDatabase:
    """Manages SQLite database for auction listings."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH

        # Ensure data directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.connection = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database and create tables if needed."""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row

        cursor = self.connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auction_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                current_price INTEGER,
                buyout_price INTEGER,
                bids INTEGER DEFAULT 0,
                time_remaining TEXT,
                end_time DATETIME,
                seller_id TEXT,
                seller_rating TEXT,
                thumbnail_url TEXT,
                listing_url TEXT NOT NULL,
                search_keyword TEXT,
                first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                notified BOOLEAN DEFAULT FALSE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_auction_id ON listings(auction_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_first_seen ON listings(first_seen_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notified ON listings(notified)
        """)

        self.connection.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def listing_exists(self, auction_id: str) -> bool:
        """Check if a listing already exists in the database."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT 1 FROM listings WHERE auction_id = ?",
            (auction_id,)
        )
        return cursor.fetchone() is not None

    def insert_listing(self, listing: Listing) -> bool:
        """
        Insert a new listing into the database.

        Returns:
            True if inserted (new listing), False if already exists
        """
        cursor = self.connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO listings (
                    auction_id, title, current_price, buyout_price, bids,
                    time_remaining, end_time, seller_id, seller_rating,
                    thumbnail_url, listing_url, search_keyword,
                    first_seen_at, last_seen_at, notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing.auction_id,
                listing.title,
                listing.current_price,
                listing.buyout_price,
                listing.bids,
                listing.time_remaining,
                listing.end_time.isoformat() if listing.end_time else None,
                listing.seller_id,
                listing.seller_rating,
                listing.thumbnail_url,
                listing.listing_url,
                listing.search_keyword,
                listing.scraped_at.isoformat(),
                listing.scraped_at.isoformat(),
                False,
            ))
            self.connection.commit()
            logger.debug(f"Inserted new listing: {listing.auction_id}")
            return True

        except sqlite3.IntegrityError:
            # Listing already exists, update last_seen_at
            self._update_last_seen(listing)
            return False

    def _update_last_seen(self, listing: Listing) -> None:
        """Update last_seen_at and price for existing listing."""
        cursor = self.connection.cursor()
        cursor.execute("""
            UPDATE listings
            SET last_seen_at = ?,
                current_price = ?,
                bids = ?,
                time_remaining = ?
            WHERE auction_id = ?
        """, (
            listing.scraped_at.isoformat(),
            listing.current_price,
            listing.bids,
            listing.time_remaining,
            listing.auction_id,
        ))
        self.connection.commit()

    def insert_listings(self, listings: list[Listing]) -> list[Listing]:
        """
        Insert multiple listings, returning only new ones.

        Args:
            listings: List of Listing objects to insert

        Returns:
            List of listings that were newly inserted (for notification)
        """
        new_listings = []

        for listing in listings:
            if self.insert_listing(listing):
                new_listings.append(listing)

        logger.info(f"Inserted {len(new_listings)} new listings out of {len(listings)} total")
        return new_listings

    def get_unnotified_listings(self) -> list[dict]:
        """Get all listings that haven't been notified yet."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM listings
            WHERE notified = FALSE
            ORDER BY first_seen_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def mark_as_notified(self, auction_ids: list[str]) -> None:
        """Mark listings as notified."""
        if not auction_ids:
            return

        cursor = self.connection.cursor()
        placeholders = ",".join("?" * len(auction_ids))
        cursor.execute(f"""
            UPDATE listings
            SET notified = TRUE
            WHERE auction_id IN ({placeholders})
        """, auction_ids)
        self.connection.commit()
        logger.info(f"Marked {len(auction_ids)} listings as notified")

    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.connection.cursor()

        # Total listings
        cursor.execute("SELECT COUNT(*) FROM listings")
        total = cursor.fetchone()[0]

        # New today
        today = datetime.now().date().isoformat()
        cursor.execute(
            "SELECT COUNT(*) FROM listings WHERE date(first_seen_at) = ?",
            (today,)
        )
        new_today = cursor.fetchone()[0]

        # Unnotified
        cursor.execute("SELECT COUNT(*) FROM listings WHERE notified = FALSE")
        unnotified = cursor.fetchone()[0]

        # Unique keywords
        cursor.execute("SELECT COUNT(DISTINCT search_keyword) FROM listings")
        keywords = cursor.fetchone()[0]

        return {
            "total": total,
            "new_today": new_today,
            "unnotified": unnotified,
            "keywords_searched": keywords,
        }

    def get_listing_by_id(self, auction_id: str) -> Optional[dict]:
        """Get a single listing by auction ID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM listings WHERE auction_id = ?", (auction_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def delete_old_listings(self, days: int = 30) -> int:
        """Delete listings older than specified days."""
        cursor = self.connection.cursor()
        cursor.execute("""
            DELETE FROM listings
            WHERE first_seen_at < datetime('now', ?)
        """, (f"-{days} days",))
        deleted = cursor.rowcount
        self.connection.commit()
        logger.info(f"Deleted {deleted} listings older than {days} days")
        return deleted
