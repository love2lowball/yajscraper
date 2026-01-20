"""Scraper commands cog for the Discord bot."""

import asyncio
import logging
import traceback
from datetime import datetime, time, timezone, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src import config
from src.scraper import YahooAuctionsScraper
from src.parser import YahooAuctionsParser
from src.mercari import MercariScraper, MercariParser, MERCARI_CATEGORIES
from src.jmty import JMTYScraper, JMTYParser, JMTY_CATEGORIES
from src.craigslist import CraigslistScraper, CraigslistParser, CRAIGSLIST_CITIES
from src.database import ListingsDatabase
from src.filters import filter_listings

logger = logging.getLogger("wheelbot.scraper")

# PST timezone (UTC-8)
PST = timezone(timedelta(hours=-8))

# Scheduled run times (5am and 5pm Pacific)
JAPAN_SCHEDULE_TIMES = [
    time(hour=5, minute=0, tzinfo=PST),   # 5:00 AM PST
    time(hour=17, minute=0, tzinfo=PST),  # 5:00 PM PST
]

# Platform choices for slash commands
PLATFORM_CHOICES = [
    app_commands.Choice(name="Japan (Yahoo + Mercari + JMTY)", value="japan"),
    app_commands.Choice(name="US (Craigslist)", value="us"),
    app_commands.Choice(name="All Platforms", value="all"),
    app_commands.Choice(name="Yahoo Auctions", value="yahoo"),
    app_commands.Choice(name="Mercari", value="mercari"),
    app_commands.Choice(name="JMTY", value="jmty"),
    app_commands.Choice(name="Craigslist", value="craigslist"),
]

# Platform colors for embeds
PLATFORM_COLORS = {
    "yahoo_auctions": discord.Color.red(),
    "mercari": discord.Color.blue(),
    "jmty": discord.Color.green(),
    "craigslist": discord.Color.purple(),
}

PLATFORM_EMOJIS = {
    "yahoo_auctions": "🔴",
    "mercari": "🔵",
    "jmty": "🟢",
    "craigslist": "🟣",
}


class ScraperCog(commands.Cog):
    """Commands for running the wheel scraper."""

    def __init__(self, bot):
        self.bot = bot
        self.japan_scheduled_task.start()

    def cog_unload(self):
        self.japan_scheduled_task.cancel()

    @tasks.loop(time=JAPAN_SCHEDULE_TIMES)
    async def japan_scheduled_task(self):
        """Run Japan scraping at 5:00 AM and 5:00 PM PST."""
        if not self.bot.notification_channel:
            return

        logger.info("Starting scheduled Japan scrape...")

        # Send notification that scheduled run is starting
        embed = discord.Embed(
            title="Scheduled Scrape Starting",
            description="Running scheduled Japan market search",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="Platforms", value="Yahoo, Mercari, JMTY", inline=True)
        embed.add_field(name="Keywords", value=str(len(config.PRIMARY_KEYWORDS)), inline=True)
        await self.bot.notification_channel.send(embed=embed)

        await self._run_scraper(
            channel=self.bot.notification_channel,
            platforms=["yahoo", "mercari", "jmty"],
            keywords=config.PRIMARY_KEYWORDS,
            us_keywords=[],
            max_pages=5,
            scheduled=True,
        )

    @japan_scheduled_task.before_loop
    async def before_japan_scheduled_task(self):
        """Wait for bot to be ready before starting scheduled tasks."""
        await self.bot.wait_until_ready()
        logger.info("Japan scheduled task ready. Runs at 5:00 AM and 5:00 PM PST")

    @app_commands.command(name="run", description="Run the scraper on specified platforms")
    @app_commands.describe(
        platform="Platform(s) to scrape",
        keywords="Custom keywords (comma-separated, e.g., 'BBS,SSR,Work Equip')",
        max_pages="Maximum pages per search (default: 5)",
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def run_scraper(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        keywords: Optional[str] = None,
        max_pages: Optional[int] = 5,
    ):
        """Run the scraper manually."""
        # Check if already scraping
        if self.bot.is_scraping:
            await interaction.response.send_message(
                "A scrape is already in progress! Use `/status` to check progress.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Determine platforms
        platform_value = platform.value
        if platform_value == "all":
            platforms = ["yahoo", "mercari", "jmty", "craigslist"]
        elif platform_value == "japan":
            platforms = ["yahoo", "mercari", "jmty"]
        elif platform_value == "us":
            platforms = ["craigslist"]
        else:
            platforms = [platform_value]

        # Parse keywords - support comma-separated multiple keywords
        jp_keywords = config.PRIMARY_KEYWORDS
        us_keywords = config.US_PRIMARY_KEYWORDS
        if keywords:
            custom_kw = [k.strip() for k in keywords.split(",") if k.strip()]
            jp_keywords = custom_kw
            us_keywords = custom_kw

        # Determine which keywords to show based on platform
        is_japan = any(p in platforms for p in ["yahoo", "mercari", "jmty"])
        is_us = "craigslist" in platforms

        # Build keywords display
        kw_display = []
        if is_japan:
            kw_display.append(f"Japan: {len(jp_keywords)} keywords")
        if is_us:
            kw_display.append(f"US: {len(us_keywords)} keywords")

        # Send starting message
        embed = discord.Embed(
            title="Starting Scraper",
            description=f"Searching **{platform.name}**",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        # Show keywords if custom ones provided
        if keywords:
            kw_preview = ", ".join(jp_keywords[:5])
            if len(jp_keywords) > 5:
                kw_preview += f" (+{len(jp_keywords) - 5} more)"
            embed.add_field(name="Keywords", value=kw_preview, inline=False)
        else:
            embed.add_field(name="Keywords", value=" | ".join(kw_display), inline=True)

        embed.add_field(name="Max Pages", value=str(max_pages), inline=True)
        embed.set_footer(text=f"Requested by {interaction.user.name}")

        await interaction.followup.send(embed=embed)

        # Run scraper
        await self._run_scraper(
            channel=interaction.channel,
            platforms=platforms,
            keywords=jp_keywords,
            us_keywords=us_keywords,
            max_pages=max_pages,
            scheduled=False,
            user=interaction.user,
        )

    @app_commands.command(name="search", description="Quick search with keyword(s)")
    @app_commands.describe(
        keywords="Keyword(s) to search for (comma-separated, e.g., 'BBS,SSR,Rays')",
        platform="Platform to search (default: Japan)",
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def quick_search(
        self,
        interaction: discord.Interaction,
        keywords: str,
        platform: Optional[app_commands.Choice[str]] = None,
    ):
        """Quick search with one or more keywords."""
        if self.bot.is_scraping:
            await interaction.response.send_message(
                "A scrape is already in progress!",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Parse comma-separated keywords
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not keyword_list:
            await interaction.followup.send("Please provide at least one keyword.", ephemeral=True)
            return

        # Default to Japan if not specified
        platform_value = platform.value if platform else "japan"
        if platform_value == "all":
            platforms = ["yahoo", "mercari", "jmty", "craigslist"]
        elif platform_value == "japan":
            platforms = ["yahoo", "mercari", "jmty"]
        elif platform_value == "us":
            platforms = ["craigslist"]
        else:
            platforms = [platform_value]

        # Display keywords nicely
        if len(keyword_list) == 1:
            kw_display = keyword_list[0]
        elif len(keyword_list) <= 5:
            kw_display = ", ".join(keyword_list)
        else:
            kw_display = ", ".join(keyword_list[:5]) + f" (+{len(keyword_list) - 5} more)"

        embed = discord.Embed(
            title=f"Searching: {kw_display}",
            description=f"Platform: **{platform.name if platform else 'Japan'}**",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="Keywords", value=str(len(keyword_list)), inline=True)
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        await interaction.followup.send(embed=embed)

        await self._run_scraper(
            channel=interaction.channel,
            platforms=platforms,
            keywords=keyword_list,
            us_keywords=keyword_list,
            max_pages=3,  # Quick search uses fewer pages
            scheduled=False,
            user=interaction.user,
        )

    @app_commands.command(name="status", description="Check scraper status and statistics")
    async def status(self, interaction: discord.Interaction):
        """Show current status and statistics."""
        embed = discord.Embed(
            title="Scraper Status",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        # Current status
        if self.bot.is_scraping:
            embed.add_field(name="Status", value="🔄 **Scraping in progress...**", inline=False)
        else:
            embed.add_field(name="Status", value="✅ **Idle**", inline=False)

        # Last run info
        if self.bot.last_run:
            embed.add_field(name="Last Run", value=self.bot.last_run.strftime("%Y-%m-%d %H:%M:%S"), inline=True)

        # Last run stats
        if self.bot.last_run_stats:
            stats = self.bot.last_run_stats
            embed.add_field(name="Last Run Results", value=(
                f"Found: {stats.get('total_found', 0)}\n"
                f"New: {stats.get('new_listings', 0)}\n"
                f"Filtered: {stats.get('filtered', 0)}"
            ), inline=True)

        # Database stats
        try:
            with ListingsDatabase() as db:
                db_stats = db.get_stats()
                embed.add_field(name="Database", value=(
                    f"Total: {db_stats['total']:,}\n"
                    f"Today: {db_stats['new_today']:,}\n"
                    f"Pending: {db_stats['unnotified']:,}"
                ), inline=True)
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")

        # Next scheduled run (Japan - daily at 3am PST)
        if self.japan_scheduled_task.next_iteration:
            next_run = self.japan_scheduled_task.next_iteration
            embed.add_field(
                name="Next Japan Scrape",
                value=f"<t:{int(next_run.timestamp())}:F>\n(<t:{int(next_run.timestamp())}:R>)",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stop", description="Stop the current scraping operation")
    async def stop_scraper(self, interaction: discord.Interaction):
        """Stop the current scraping operation."""
        if not self.bot.is_scraping:
            await interaction.response.send_message("No scrape is currently running.", ephemeral=True)
            return

        self.bot.is_scraping = False
        if self.bot.current_task:
            self.bot.current_task.cancel()

        embed = discord.Embed(
            title="Scraper Stopped",
            description="The current scraping operation has been cancelled.",
            color=discord.Color.orange(),
            timestamp=datetime.now(),
        )
        embed.set_footer(text=f"Stopped by {interaction.user.name}")

        await interaction.response.send_message(embed=embed)

    async def _run_scraper(
        self,
        channel: discord.TextChannel,
        platforms: list[str],
        keywords: list[str],
        us_keywords: list[str],
        max_pages: int,
        scheduled: bool = False,
        user: Optional[discord.User] = None,
    ):
        """Internal method to run the scraper."""
        self.bot.is_scraping = True
        start_time = datetime.now()
        all_listings = []
        stats = {"total_found": 0, "new_listings": 0, "filtered": 0}

        try:
            # Yahoo Auctions
            if "yahoo" in platforms:
                await self._send_progress(channel, "Searching Yahoo Auctions...", "yahoo_auctions")
                yahoo_listings = await asyncio.to_thread(
                    self._run_yahoo, keywords, max_pages
                )
                all_listings.extend(yahoo_listings)
                await self._send_progress(
                    channel,
                    f"Yahoo Auctions: Found {len(yahoo_listings)} listings",
                    "yahoo_auctions",
                )

            # Mercari
            if "mercari" in platforms:
                await self._send_progress(channel, "Searching Mercari...", "mercari")
                mercari_listings = await self._run_mercari(keywords, max_pages)
                all_listings.extend(mercari_listings)
                await self._send_progress(
                    channel,
                    f"Mercari: Found {len(mercari_listings)} listings",
                    "mercari",
                )

            # JMTY
            if "jmty" in platforms:
                await self._send_progress(channel, "Searching JMTY...", "jmty")
                jmty_listings = await asyncio.to_thread(
                    self._run_jmty, keywords, max_pages
                )
                all_listings.extend(jmty_listings)
                await self._send_progress(
                    channel,
                    f"JMTY: Found {len(jmty_listings)} listings",
                    "jmty",
                )

            # Craigslist
            if "craigslist" in platforms:
                await self._send_progress(channel, "Searching Craigslist (this may take a while)...", "craigslist")
                # Use fewer cities for interactive searches
                cities = CRAIGSLIST_CITIES[:20] if not scheduled else CRAIGSLIST_CITIES
                cl_listings = await asyncio.to_thread(
                    self._run_craigslist, us_keywords, cities, max_pages
                )
                all_listings.extend(cl_listings)
                await self._send_progress(
                    channel,
                    f"Craigslist: Found {len(cl_listings)} listings",
                    "craigslist",
                )

            stats["total_found"] = len(all_listings)

            # Filter listings
            pre_filter = len(all_listings)
            all_listings = filter_listings(all_listings)
            stats["filtered"] = pre_filter - len(all_listings)

            # Store in database and get new listings
            with ListingsDatabase() as db:
                new_listings = db.insert_listings(all_listings)
                stats["new_listings"] = len(new_listings)

                # Mark as notified
                if new_listings:
                    listing_ids = [l.listing_id for l in new_listings]
                    db.mark_as_notified(listing_ids)

            # Send results
            await self._send_results(channel, new_listings, stats, start_time, user, scheduled)

            self.bot.last_run = datetime.now()
            self.bot.last_run_stats = stats

        except asyncio.CancelledError:
            logger.info("Scraping cancelled")
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            logger.error(traceback.format_exc())
            await self._send_error(channel, str(e))
        finally:
            self.bot.is_scraping = False

    def _run_yahoo(self, keywords: list[str], max_pages: int) -> list:
        """Run Yahoo Auctions scraper (sync)."""
        parser = YahooAuctionsParser()
        all_listings = []
        categories = list(config.CATEGORIES.values())

        with YahooAuctionsScraper() as scraper:
            for keyword in keywords:
                for category in categories:
                    try:
                        html_pages = scraper.search_with_pagination(
                            keyword, category, max_pages=max_pages, parser=parser
                        )
                        for html in html_pages:
                            listings = parser.parse_search_results(html, keyword)
                            all_listings.extend(listings)
                    except Exception as e:
                        logger.error(f"Yahoo search failed for '{keyword}': {e}")

        return all_listings

    async def _run_mercari(self, keywords: list[str], max_pages: int) -> list:
        """Run Mercari scraper (async)."""
        scraper = MercariScraper()
        parser = MercariParser()
        all_listings = []
        categories = list(MERCARI_CATEGORIES.values())

        try:
            results = await scraper.search_all_keywords(
                keywords=keywords,
                categories=categories,
                price_min=config.MIN_PRICE,
                price_max=config.MAX_PRICE,
                max_pages_per_search=max_pages,
            )

            for (keyword, category), search_results_list in results.items():
                for search_results in search_results_list:
                    listings = parser.parse_search_results(search_results, keyword)
                    all_listings.extend(listings)
        except Exception as e:
            logger.error(f"Mercari scraper failed: {e}")

        return all_listings

    def _run_jmty(self, keywords: list[str], max_pages: int) -> list:
        """Run JMTY scraper (sync)."""
        parser = JMTYParser()
        all_listings = []
        category = JMTY_CATEGORIES["tire_wheel"]

        with JMTYScraper() as scraper:
            for keyword in keywords:
                try:
                    html_pages = scraper.search_with_pagination(
                        keyword=keyword,
                        category=category,
                        price_min=config.MIN_PRICE,
                        price_max=config.MAX_PRICE,
                        max_pages=max_pages,
                        parser=parser,
                    )
                    for html in html_pages:
                        listings = parser.parse_search_results(html, keyword)
                        all_listings.extend(listings)
                except Exception as e:
                    logger.error(f"JMTY search failed for '{keyword}': {e}")

        return all_listings

    def _run_craigslist(self, keywords: list[str], cities: list[str], max_pages: int) -> list:
        """Run Craigslist scraper (sync)."""
        parser = CraigslistParser()
        all_listings = []

        with CraigslistScraper() as scraper:
            results = scraper.search_all_cities(
                keywords=keywords,
                cities=cities,
                categories=["wta"],
                price_min=config.US_MIN_PRICE,
                price_max=config.US_MAX_PRICE,
                max_pages_per_city=max_pages,
                parser=parser,
            )

            for (city, keyword, category), html_pages in results.items():
                for html in html_pages:
                    listings = parser.parse_search_results(html, keyword, city)
                    all_listings.extend(listings)

        return all_listings

    async def _send_progress(self, channel: discord.TextChannel, message: str, platform: str):
        """Send a progress update."""
        emoji = PLATFORM_EMOJIS.get(platform, "🔍")
        await channel.send(f"{emoji} {message}")

    async def _send_results(
        self,
        channel: discord.TextChannel,
        new_listings: list,
        stats: dict,
        start_time: datetime,
        user: Optional[discord.User],
        scheduled: bool,
    ):
        """Send scraping results."""
        duration = (datetime.now() - start_time).total_seconds()

        # Summary embed
        embed = discord.Embed(
            title="Scraping Complete",
            color=discord.Color.green() if new_listings else discord.Color.blue(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="Total Found", value=str(stats["total_found"]), inline=True)
        embed.add_field(name="Filtered Out", value=str(stats["filtered"]), inline=True)
        embed.add_field(name="New Listings", value=str(stats["new_listings"]), inline=True)
        embed.add_field(name="Duration", value=f"{duration:.1f}s", inline=True)

        if scheduled:
            embed.set_footer(text="Scheduled run")
        elif user:
            embed.set_footer(text=f"Requested by {user.name}")

        await channel.send(embed=embed)

        # Send all new listings (batched to respect Discord's 10 embeds per message limit)
        if new_listings:
            listing_embeds = []
            for listing in new_listings:
                listing_embed = self._create_listing_embed(listing)
                listing_embeds.append(listing_embed)

                # Send in batches of 10 (Discord limit)
                if len(listing_embeds) >= 10:
                    await channel.send(embeds=listing_embeds)
                    listing_embeds = []
                    await asyncio.sleep(1)  # Rate limit protection

            # Send remaining embeds
            if listing_embeds:
                await channel.send(embeds=listing_embeds)

    def _create_listing_embed(self, listing) -> discord.Embed:
        """Create a Discord embed for a single listing."""
        platform = getattr(listing, 'platform', 'yahoo_auctions')
        color = PLATFORM_COLORS.get(platform, discord.Color.blue())
        emoji = PLATFORM_EMOJIS.get(platform, "🔍")

        # Format price
        currency = getattr(listing, 'currency', 'JPY')
        price = listing.current_price
        price_str = f"${price:,}" if currency == "USD" else f"¥{price:,}"

        # Validate URL - Discord requires well-formed URLs
        listing_url = listing.listing_url
        if not listing_url or not listing_url.startswith(('http://', 'https://')):
            listing_url = None

        embed = discord.Embed(
            title=listing.title[:256],
            url=listing_url,
            color=color,
        )

        embed.add_field(name="Price", value=price_str, inline=True)

        if hasattr(listing, 'location') and listing.location:
            embed.add_field(name="Location", value=listing.location[:100], inline=True)

        embed.add_field(name="Platform", value=f"{emoji} {platform.replace('_', ' ').title()}", inline=True)

        # Validate thumbnail URL
        thumbnail_url = listing.thumbnail_url if listing.thumbnail_url else None
        if thumbnail_url and thumbnail_url.startswith(('http://', 'https://')):
            embed.set_thumbnail(url=thumbnail_url)

        return embed

    async def _send_error(self, channel: discord.TextChannel, error: str):
        """Send an error notification."""
        embed = discord.Embed(
            title="Scraping Error",
            description=f"```{error[:1000]}```",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        await channel.send(embed=embed)


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(ScraperCog(bot))
