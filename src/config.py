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

# Yahoo Auctions Categories
CATEGORIES = {
    "tire_wheel_sets": "2084200183",  # タイヤ・ホイールセット
    "wheels_only": "2084005140",       # ホイール
}

# Mercari Japan Categories
MERCARI_CATEGORIES = {
    "wheels_only": 1112,
    "tire_wheel_sets": 1109,
}

# Mercari-specific settings (more conservative delays)
MERCARI_MIN_DELAY = 3.0
MERCARI_MAX_DELAY = 7.0
MERCARI_MAX_PAGES = 5  # Mercari returns more per page, so fewer pages needed

# JMTY Categories
JMTY_CATEGORIES = {
    "tire_wheel": "g-2429",  # タイヤ、ホイール
}

# JMTY-specific settings (most conservative due to bot protection)
JMTY_MIN_DELAY = 5.0
JMTY_MAX_DELAY = 10.0
JMTY_MAX_PAGES = 5
JMTY_REGION = "all"  # "all" for nationwide, or specific prefecture like "tokyo"

# Primary search keywords (Japanese)
# Note: "ホイール" omitted since we search within wheel categories
PRIMARY_KEYWORDS = [
    "希少",                # rare
    "当時もの",            # period-correct
    "メッキ",              # chrome
    "絶版",                # discontinued
    "3ピース",             # 3-piece
    "３本スポーク",        # 3-spoke
    "旧車",                # classic car
    "深リム",              # deep dish
    "鍛造",                # forged
    "バレル研磨",          # barrel polished
    "carving",             # carving
    "カービング",          # carving (Japanese)
    "ギャルソン",          # Garson
    "bridgestone",         # Bridgestone
    "BIM",                 # Bridgestone BIM studio
    "リバレル",            # re-barrel
    "トラフィックスター",  # Traffic Star
    "vienna",              # Vienna
    "ヴィエナ",            # Vienna (Japanese)
    "ABC",                 # ABC Exclusive
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

    # Condition we don't want (new items)
    "新品",               # brand new
    "未使用",             # unused/never used
    "新品未使用",         # brand new unused

    # Other noise
    "軽自動車",           # kei car (too small usually)
    "12インチ",           # 12 inch (too small)
    "13インチ",           # 13 inch (usually too small)
]

# Price filters (yen)
MIN_PRICE = 5000        # Skip below this (likely junk or parts)
MAX_PRICE = 250000      # Skip above this (out of range)

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

# ============================================================
# US Market Settings (Craigslist)
# ============================================================

# Craigslist Categories
CRAIGSLIST_CATEGORIES = {
    "wheels_tires": "wta",   # wheels+tires section
    "auto_parts": "pta",     # auto parts section
}

# Craigslist-specific settings (conservative due to bot protection)
CRAIGSLIST_MIN_DELAY = 5.0
CRAIGSLIST_MAX_DELAY = 10.0
CRAIGSLIST_MAX_PAGES = 2  # Pages per city (120 results per page)

# US Price filters (USD)
US_MIN_PRICE = 150
US_MAX_PRICE = 1200

# US Search keywords (placeholder - user will provide)
US_PRIMARY_KEYWORDS = [
    "billet",  # placeholder
]

# US Exclude keywords - skip listings containing these terms
US_EXCLUDE_KEYWORDS = [
    # Replicas and fakes
    "replica",
    "reps",
    "rep ",
    "fake",
    "knockoff",

    # Not actual wheels
    "hubcaps",
    "hub caps",
    "center caps only",
    "center cap",
    "lug nuts",
    "spacers",

    # Condition we don't want
    "new",
    "brand new",
    "winter tires",
    "snow tires",
    "studded",

    # Too small or irrelevant
    "12 inch",
    "13 inch",
    "golf cart",
    "atv",
    "trailer",
    "lawn mower",
]
