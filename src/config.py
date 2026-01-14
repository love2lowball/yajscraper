"""Configuration and constants for Yahoo Auctions scraper."""

import os
from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# Database
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "listings.db"))

# Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Proxy (optional)
PROXY_URL = os.getenv("PROXY_URL", "")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Yahoo Auctions URLs
SEARCH_BASE_URL = "https://auctions.yahoo.co.jp/search/search"
LISTING_BASE_URL = "https://page.auctions.yahoo.co.jp/jp/auction"

# Categories
CATEGORIES = {
    "tire_wheel_sets": "2084199064",  # タイヤ・ホイールセット
    "wheels_only": "26318",            # ホイール単体
}

# Primary search keywords (Japanese)
PRIMARY_KEYWORDS = [
    "希少 ホイール",       # rare wheels
    "当時もの ホイール",   # period-correct wheels
    "メッキ ホイール",     # chrome wheels
    "絶版 ホイール",       # discontinued wheels
    "3ピース ホイール",    # 3-piece wheels
    "３本スポーク ホイール", # 3-spoke wheels
    "旧車 ホイール",       # classic car wheels
    "深リム ホイール",     # deep dish wheels
    "鍛造 3ピース",        # forged 3-piece
    "バレル研磨 ホイール", # barrel polished wheels
    "carving ホイール",    # carving wheels
    "カービング",          # carving (Japanese)
    "ギャルソン",          # Garson
    "bridgestone ホイール", # Bridgestone wheels
    "BIM ホイール",        # Bridgestone BIM studio
    "リバレル",            # re-barrel
    "トラフィックスター",  # Traffic Star
    "vienna ホイール",     # Vienna wheels
    "ヴィエナ",            # Vienna (Japanese)
    "ABC ホイール",        # ABC Exclusive
]

# Secondary keywords (brand-specific, for later)
SECONDARY_KEYWORDS = [
    "ロンシャン",         # Longchamp
    "ハヤシ レーシング",  # Hayashi Racing
    "RSワタナベ",         # RS Watanabe
    "ワーク エクイップ",  # Work Equip
    "SSR スピードスター", # SSR Speedstar
    "リバーサイド",       # Riverside
    "クレンツェ",         # Kranze
]

# Exclude keywords - skip listings containing these terms
EXCLUDE_KEYWORDS = [
    # Not actual wheels
    "レプリカ",           # replica
    "ミニカー",           # model cars
    "1/18",               # scale model
    "1/43",               # scale model
    "1/64",               # scale model
    "カタログ",           # catalog
    "ステッカー",         # stickers
    "ポスター",           # poster
    "キーホルダー",       # keychain

    # Parts only (not full wheels)
    "ホイールキャップ",   # hubcaps
    "センターキャップ",   # center caps only
    "ナットのみ",         # lug nuts only
    "バルブ",             # valve stems
    "スペーサー",         # spacers only

    # Tires we don't want
    "スタッドレス",       # studless/winter tires
    "タイヤのみ",         # tires only (no wheels)

    # Other noise
    "軽自動車",           # kei car (too small usually)
    "12インチ",           # 12 inch (too small)
    "13インチ",           # 13 inch (usually too small)
]

# Price filters (yen)
MIN_PRICE = 5000        # Skip below this (likely junk or parts)
MAX_PRICE = 2000000     # Skip above this (out of range)

# Require keywords - if set, listing must contain at least one of these
# Leave empty to disable
REQUIRE_KEYWORDS = [
    # Uncomment to only get specific sizes:
    # "14インチ",
    # "15インチ",
    # "16インチ",
    # "17インチ",
]

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

# Request settings
REQUEST_TIMEOUT = 30  # seconds
MIN_DELAY = 2  # seconds between requests
MAX_DELAY = 5  # seconds between requests
MAX_RETRIES = 3
BACKOFF_FACTOR = 2  # exponential backoff multiplier
