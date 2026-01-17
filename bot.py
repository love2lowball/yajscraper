#!/usr/bin/env python3
"""
Multi-Platform Wheel Scraper Discord Bot

Interactive Discord bot for searching Yahoo Auctions, Mercari, JMTY, and Craigslist.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("wheelbot")

# Bot configuration
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
NOTIFICATION_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
ADMIN_USER_IDS = [int(id.strip()) for id in os.getenv("ADMIN_USER_IDS", "").split(",") if id.strip()]

# Intents
intents = discord.Intents.default()
intents.message_content = True


class WheelBot(commands.Bot):
    """Main bot class for wheel scraper."""

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Multi-Platform JDM Wheel Scraper Bot",
        )
        self.notification_channel = None
        self.is_scraping = False
        self.current_task = None
        self.last_run = None
        self.last_run_stats = {}

    async def setup_hook(self):
        """Called when the bot is starting up."""
        # Load cogs
        await self.load_extension("src.bot.cogs.scraper")
        await self.load_extension("src.bot.cogs.admin")

        # Sync slash commands
        logger.info("Syncing slash commands...")
        await self.tree.sync()
        logger.info("Slash commands synced!")

    async def on_ready(self):
        """Called when bot is connected and ready."""
        logger.info(f"Bot connected as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

        # Get notification channel
        if NOTIFICATION_CHANNEL_ID:
            self.notification_channel = self.get_channel(NOTIFICATION_CHANNEL_ID)
            if self.notification_channel:
                logger.info(f"Notification channel: #{self.notification_channel.name}")
            else:
                logger.warning(f"Could not find channel with ID {NOTIFICATION_CHANNEL_ID}")

        # Set presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for rare wheels"
            )
        )

        # Send startup message
        if self.notification_channel:
            embed = discord.Embed(
                title="Wheel Scraper Bot Online",
                description="Ready to search for rare wheels!",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )
            embed.add_field(name="Commands", value="`/search`, `/run`, `/status`, `/schedule`", inline=False)
            embed.set_footer(text="Use /help for more information")
            await self.notification_channel.send(embed=embed)

    async def on_command_error(self, ctx, error):
        """Handle command errors."""
        logger.error(f"Command error: {error}")
        if self.notification_channel:
            embed = discord.Embed(
                title="Command Error",
                description=str(error),
                color=discord.Color.red(),
                timestamp=datetime.now(),
            )
            await self.notification_channel.send(embed=embed)


def main():
    """Main entry point."""
    if not DISCORD_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not set in environment variables!")
        logger.error("Please set it in your .env file")
        sys.exit(1)

    # Create logs directory
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # Run bot
    bot = WheelBot()

    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.error("Invalid Discord token! Please check your DISCORD_BOT_TOKEN")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
