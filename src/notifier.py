"""Discord webhook notifications for new listings."""

import json
import logging
from pathlib import Path
from typing import Optional

import requests

from .base import Listing
from . import config

logger = logging.getLogger(__name__)

# Discord limits
MAX_MESSAGE_LENGTH = 2000
MAX_EMBEDS_PER_MESSAGE = 10


class DiscordNotifier:
    """Sends notifications to Discord via webhook."""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or config.DISCORD_WEBHOOK_URL
        self.queue_file = config.DATA_DIR / "notification_queue.json"

    def _send_webhook(self, payload: dict) -> bool:
        """Send a webhook request to Discord."""
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return False

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            logger.debug("Discord webhook sent successfully")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Discord webhook: {e}")
            return False

    def _format_price(self, price: int, currency: str = "JPY") -> str:
        """Format price with thousands separator and currency symbol."""
        if currency == "USD":
            return f"${price:,}"
        return f"¥{price:,}"

    def _create_listing_embed(self, listing: Listing | dict) -> dict:
        """Create a Discord embed for a single listing."""
        # Handle both Listing objects and dicts
        if isinstance(listing, dict):
            title = listing.get("title", "")
            current_price = listing.get("current_price", 0)
            buyout_price = listing.get("buyout_price")
            currency = listing.get("currency", "JPY")
            time_remaining = listing.get("time_remaining", "")
            seller_id = listing.get("seller_id", "")
            seller_rating = listing.get("seller_rating", "")
            listing_url = listing.get("listing_url", "")
            thumbnail_url = listing.get("thumbnail_url", "")
            platform = listing.get("platform", "yahoo_auctions")
        else:
            title = listing.title
            current_price = listing.current_price
            buyout_price = listing.buyout_price
            currency = getattr(listing, 'currency', 'JPY')
            time_remaining = getattr(listing, 'time_remaining', '')
            seller_id = listing.seller_id
            seller_rating = listing.seller_rating
            listing_url = listing.listing_url
            thumbnail_url = listing.thumbnail_url
            platform = getattr(listing, 'platform', 'yahoo_auctions')

        # Build price line
        price_str = self._format_price(current_price, currency)
        if buyout_price:
            price_str += f" (即決: {self._format_price(buyout_price, currency)})"

        # Build seller line
        seller_str = seller_id if seller_id else "Unknown"
        if seller_rating:
            seller_str += f" (評価: {seller_rating})"

        # Platform-specific formatting
        platform_info = {
            "yahoo_auctions": {"emoji": "🔴", "name": "Yahoo", "color": 0xE63946},
            "mercari": {"emoji": "🔵", "name": "Mercari", "color": 0x4A90D9},
            "jmty": {"emoji": "🟢", "name": "JMTY", "color": 0x2ECC71},
            "craigslist": {"emoji": "🟣", "name": "Craigslist", "color": 0x9B59B6},
        }
        pinfo = platform_info.get(platform, platform_info["yahoo_auctions"])

        # Build description
        description_lines = [
            f"{pinfo['emoji']} **{pinfo['name']}**",
            f"💰 {price_str}",
            f"⏰ 残り {time_remaining}" if time_remaining else "",
            f"👤 {seller_str}",
            f"🔗 [View Listing]({listing_url})",
        ]
        description = "\n".join(line for line in description_lines if line)

        embed = {
            "title": title[:256],  # Discord title limit
            "description": description,
            "url": listing_url,
            "color": pinfo["color"],
        }

        # Add thumbnail if available
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}

        return embed

    def send_listings(
        self,
        listings: list[Listing | dict],
        stats: dict = None,
        dry_run: bool = False
    ) -> bool:
        """
        Send new listings to Discord.

        Args:
            listings: List of new listings to notify
            stats: Database statistics dict
            dry_run: If True, don't actually send (for testing)

        Returns:
            True if all notifications sent successfully
        """
        if not listings:
            logger.info("No new listings to notify")
            return True

        if dry_run:
            logger.info(f"[DRY RUN] Would send {len(listings)} listings to Discord")
            for listing in listings:
                title = listing.title if isinstance(listing, Listing) else listing.get("title", "")
                logger.info(f"  - {title[:60]}...")
            return True

        # Split into batches of MAX_EMBEDS_PER_MESSAGE
        batches = [
            listings[i:i + MAX_EMBEDS_PER_MESSAGE]
            for i in range(0, len(listings), MAX_EMBEDS_PER_MESSAGE)
        ]

        success = True
        total_batches = len(batches)

        for batch_num, batch in enumerate(batches, 1):
            embeds = [self._create_listing_embed(listing) for listing in batch]

            # Build content header
            if batch_num == 1:
                content = f"🔔 **New Yahoo Auctions Listings** — Found {len(listings)} new wheels"
            else:
                content = f"📦 Continued ({batch_num}/{total_batches})..."

            payload = {
                "content": content,
                "embeds": embeds,
            }

            if not self._send_webhook(payload):
                success = False
                # Queue failed notifications
                self._queue_notification(batch)

        # Send summary if stats provided
        if stats and success:
            self._send_summary(stats, len(listings))

        return success

    def _send_summary(self, stats: dict, new_count: int) -> None:
        """Send a summary message."""
        summary = (
            f"📊 **Summary**\n"
            f"Total active listings in DB: {stats.get('total', 0):,} | "
            f"New today: {stats.get('new_today', 0):,} | "
            f"Keywords searched: {stats.get('keywords_searched', 0)}"
        )

        payload = {"content": summary}
        self._send_webhook(payload)

    def _queue_notification(self, listings: list) -> None:
        """Queue failed notifications for retry."""
        try:
            # Load existing queue
            queue = []
            if self.queue_file.exists():
                with open(self.queue_file, "r") as f:
                    queue = json.load(f)

            # Add new items
            for listing in listings:
                if isinstance(listing, Listing):
                    queue.append(listing.to_dict())
                else:
                    queue.append(listing)

            # Save queue
            with open(self.queue_file, "w") as f:
                json.dump(queue, f, indent=2, ensure_ascii=False)

            logger.info(f"Queued {len(listings)} notifications for retry")

        except Exception as e:
            logger.error(f"Failed to queue notifications: {e}")

    def retry_queued(self) -> bool:
        """Retry sending queued notifications."""
        if not self.queue_file.exists():
            return True

        try:
            with open(self.queue_file, "r") as f:
                queue = json.load(f)

            if not queue:
                return True

            logger.info(f"Retrying {len(queue)} queued notifications")

            if self.send_listings(queue):
                # Clear queue on success
                self.queue_file.unlink()
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to retry queued notifications: {e}")
            return False

    def send_error_alert(self, error_message: str) -> bool:
        """Send an error alert to Discord."""
        payload = {
            "content": f"🚨 **Scraper Error**\n```\n{error_message[:1500]}\n```",
        }
        return self._send_webhook(payload)

    def send_test_message(self) -> bool:
        """Send a test message to verify webhook."""
        payload = {
            "content": "✅ **YAJScraper Test** — Webhook is working!",
        }
        return self._send_webhook(payload)
