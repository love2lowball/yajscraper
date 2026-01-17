"""Admin commands cog for the Discord bot."""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.database import ListingsDatabase
from src import config

logger = logging.getLogger("wheelbot.admin")

# Get admin user IDs from environment
ADMIN_USER_IDS = [int(id.strip()) for id in os.getenv("ADMIN_USER_IDS", "").split(",") if id.strip()]


def is_admin():
    """Check if user is an admin."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not ADMIN_USER_IDS:
            return True  # No admins configured, allow all
        return interaction.user.id in ADMIN_USER_IDS
    return app_commands.check(predicate)


class AdminCog(commands.Cog):
    """Admin commands for bot management."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="schedule", description="View or modify the scraping schedule")
    @app_commands.describe(
        action="Action to perform",
        hour="Hour to run (0-23, PST) - for 'set' action",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="View current schedule", value="view"),
        app_commands.Choice(name="Set new time", value="set"),
        app_commands.Choice(name="Pause scheduled runs", value="pause"),
        app_commands.Choice(name="Resume scheduled runs", value="resume"),
        app_commands.Choice(name="Run now", value="now"),
    ])
    @is_admin()
    async def schedule(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        hour: Optional[int] = None,
    ):
        """Manage the scraping schedule."""
        scraper_cog = self.bot.get_cog("ScraperCog")
        if not scraper_cog:
            await interaction.response.send_message("Scraper cog not loaded!", ephemeral=True)
            return

        if action.value == "view":
            task = scraper_cog.japan_scheduled_task
            embed = discord.Embed(
                title="Scraping Schedule",
                description="Japan platforms run daily at scheduled time",
                color=discord.Color.blue(),
                timestamp=datetime.now(),
            )

            if task.is_running():
                embed.add_field(name="Status", value="✅ Active", inline=True)
                embed.add_field(name="Schedule", value="Daily at 3:00 AM PST", inline=True)
                if task.next_iteration:
                    embed.add_field(
                        name="Next Run",
                        value=f"<t:{int(task.next_iteration.timestamp())}:F>\n(<t:{int(task.next_iteration.timestamp())}:R>)",
                        inline=False,
                    )
            else:
                embed.add_field(name="Status", value="⏸️ Paused", inline=True)

            embed.add_field(
                name="Platforms",
                value="🔴 Yahoo Auctions\n🔵 Mercari\n🟢 JMTY",
                inline=False,
            )

            await interaction.response.send_message(embed=embed)

        elif action.value == "set":
            if hour is None or hour < 0 or hour > 23:
                await interaction.response.send_message(
                    "Please specify an hour between 0 and 23 (PST)",
                    ephemeral=True,
                )
                return

            # Note: Changing the time requires restarting the task with new time
            # For simplicity, we'll just inform the user to update the config
            await interaction.response.send_message(
                f"To change the schedule time, update `JAPAN_SCHEDULE_TIME` in "
                f"`src/bot/cogs/scraper.py` to `time(hour={hour}, minute=0, tzinfo=PST)` "
                f"and restart the bot.\n\nCurrent schedule: **3:00 AM PST**",
            )

        elif action.value == "pause":
            scraper_cog.japan_scheduled_task.cancel()
            await interaction.response.send_message("Scheduled Japan runs paused")

        elif action.value == "resume":
            if not scraper_cog.japan_scheduled_task.is_running():
                scraper_cog.japan_scheduled_task.start()
            await interaction.response.send_message("Scheduled Japan runs resumed")

        elif action.value == "now":
            if self.bot.is_scraping:
                await interaction.response.send_message(
                    "A scrape is already in progress!",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message("Starting Japan scrape now...")
            # Manually trigger the scheduled task logic
            await scraper_cog._run_scraper(
                channel=interaction.channel,
                platforms=["yahoo", "mercari", "jmty"],
                keywords=config.PRIMARY_KEYWORDS,
                us_keywords=[],
                max_pages=5,
                scheduled=False,
                user=interaction.user,
            )

    @app_commands.command(name="stats", description="View detailed database statistics")
    async def stats(self, interaction: discord.Interaction):
        """Show detailed statistics."""
        try:
            with ListingsDatabase() as db:
                stats = db.get_stats()

                embed = discord.Embed(
                    title="Database Statistics",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(),
                )

                embed.add_field(name="Total Listings", value=f"{stats['total']:,}", inline=True)
                embed.add_field(name="New Today", value=f"{stats['new_today']:,}", inline=True)
                embed.add_field(name="Unnotified", value=f"{stats['unnotified']:,}", inline=True)
                embed.add_field(name="Keywords Used", value=str(stats['keywords_searched']), inline=True)

                # Platform breakdown (if available)
                # This would require adding a method to get platform counts

                await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(f"Error getting stats: {e}", ephemeral=True)

    @app_commands.command(name="cleanup", description="Delete old listings from database")
    @app_commands.describe(days="Delete listings older than this many days")
    @is_admin()
    async def cleanup(self, interaction: discord.Interaction, days: int = 30):
        """Clean up old listings."""
        if days < 7:
            await interaction.response.send_message(
                "Minimum cleanup age is 7 days",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            with ListingsDatabase() as db:
                deleted = db.delete_old_listings(days)

            embed = discord.Embed(
                title="Cleanup Complete",
                description=f"Deleted **{deleted:,}** listings older than {days} days",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"Cleanup failed: {e}")

    @app_commands.command(name="config", description="View current configuration")
    @is_admin()
    async def view_config(self, interaction: discord.Interaction):
        """View current bot configuration."""
        embed = discord.Embed(
            title="Bot Configuration",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        # Japan settings
        embed.add_field(
            name="Japan Keywords",
            value=f"{len(config.PRIMARY_KEYWORDS)} keywords",
            inline=True,
        )
        embed.add_field(
            name="Japan Price Range",
            value=f"¥{config.MIN_PRICE:,} - ¥{config.MAX_PRICE:,}",
            inline=True,
        )
        embed.add_field(
            name="Japan Excludes",
            value=f"{len(config.EXCLUDE_KEYWORDS)} terms",
            inline=True,
        )

        # US settings
        embed.add_field(
            name="US Keywords",
            value=f"{len(config.US_PRIMARY_KEYWORDS)} keywords",
            inline=True,
        )
        embed.add_field(
            name="US Price Range",
            value=f"${config.US_MIN_PRICE:,} - ${config.US_MAX_PRICE:,}",
            inline=True,
        )
        embed.add_field(
            name="US Excludes",
            value=f"{len(config.US_EXCLUDE_KEYWORDS)} terms",
            inline=True,
        )

        # Show first few keywords
        jp_preview = ", ".join(config.PRIMARY_KEYWORDS[:5])
        if len(config.PRIMARY_KEYWORDS) > 5:
            jp_preview += f" ... (+{len(config.PRIMARY_KEYWORDS) - 5} more)"
        embed.add_field(name="Japan Keyword Preview", value=jp_preview, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Show bot help and commands")
    async def help_command(self, interaction: discord.Interaction):
        """Show help information."""
        embed = discord.Embed(
            title="Wheel Scraper Bot Help",
            description="Search for rare JDM wheels across multiple platforms",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="🔍 Search Commands",
            value=(
                "`/search <keywords>` - Quick search (comma-separated)\n"
                "  Example: `/search BBS,SSR,Work Equip`\n"
                "`/run <platform>` - Run full scraper on platform(s)\n"
                "`/stop` - Stop current scraping operation"
            ),
            inline=False,
        )

        embed.add_field(
            name="📊 Status Commands",
            value=(
                "`/status` - Check scraper status and stats\n"
                "`/stats` - View detailed database statistics\n"
                "`/config` - View current configuration"
            ),
            inline=False,
        )

        embed.add_field(
            name="⚙️ Admin Commands",
            value=(
                "`/schedule view` - View current schedule\n"
                "`/schedule now` - Run Japan scrape immediately\n"
                "`/schedule pause/resume` - Control auto-scraping\n"
                "`/cleanup <days>` - Delete old listings"
            ),
            inline=False,
        )

        embed.add_field(
            name="🌏 Platforms",
            value=(
                "🔴 **Yahoo Auctions** - Japanese auctions\n"
                "🔵 **Mercari** - Japanese marketplace\n"
                "🟢 **JMTY** - Japanese classifieds\n"
                "🟣 **Craigslist** - US classifieds"
            ),
            inline=False,
        )

        embed.set_footer(text="Japan scraping runs daily at 3:00 AM PST")

        await interaction.response.send_message(embed=embed)

    @schedule.error
    @cleanup.error
    @view_config.error
    async def admin_error(self, interaction: discord.Interaction, error):
        """Handle admin command errors."""
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True,
            )
        else:
            logger.error(f"Admin command error: {error}")
            await interaction.response.send_message(
                f"An error occurred: {error}",
                ephemeral=True,
            )


async def setup(bot):
    """Load the cog."""
    await bot.add_cog(AdminCog(bot))
