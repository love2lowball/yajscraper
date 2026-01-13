# YAJScraper - Yahoo Auctions Japan Wheel Scraper

## Project Overview
Automated scraper for Yahoo Auctions Japan targeting rare JDM wheels for WheelyWich import/export business. Runs daily, deduplicates listings, and sends new finds to Discord.

## Tech Stack
- Python 3.10+
- `requests` for HTTP
- `beautifulsoup4` for HTML parsing
- `sqlite3` for deduplication
- Discord webhooks for notifications

## Project Structure
```
yajscraper/
├── src/
│   ├── __init__.py
│   ├── scraper.py      # HTTP requests, search execution
│   ├── parser.py       # HTML parsing, data extraction
│   ├── database.py     # SQLite operations
│   ├── notifier.py     # Discord webhook sender
│   └── config.py       # Keywords, settings, constants
├── data/
│   └── listings.db     # SQLite database
├── logs/
│   └── scraper.log
├── .env                # Secrets (not committed)
├── .env.example        # Template for .env
├── requirements.txt
├── run.py              # CLI entry point
└── CLAUDE.md
```

## Key URLs
- Search: `https://auctions.yahoo.co.jp/search/search?p={keyword}&auccat={category}`
- Listing: `https://page.auctions.yahoo.co.jp/jp/auction/{auction_id}`
- Categories: `2084199064` (tire+wheel sets), `26318` (wheels only)

## Search Keywords (Japanese)
Primary (search individually):
- 希少 ホイール (rare wheels)
- 当時もの ホイール (period-correct wheels)
- メッキ ホイール (chrome wheels)
- 絶版 ホイール (discontinued wheels)
- 3ピース ホイール (3-piece wheels)
- ３本スポーク ホイール (3-spoke wheels)
- 旧車 ホイール (classic car wheels)
- 深リム ホイール (deep dish wheels)
- 鍛造 3ピース (forged 3-piece)
- バレル研磨 ホイール (barrel polished wheels)

## Data Model
Each listing extracts:
- `auction_id` - unique Yahoo ID
- `title` - full listing title
- `current_price` - current bid (yen)
- `buyout_price` - buy-it-now price (optional)
- `bids` - bid count
- `time_remaining` - human readable
- `end_time` - datetime
- `seller_id`, `seller_rating`
- `thumbnail_url`, `listing_url`
- `search_keyword` - which keyword matched

## Request Handling Rules
- Random delay: 2-5 seconds between requests
- Rotate User-Agent strings
- 30 second timeout
- Retry 3x with exponential backoff
- Back off on 429 rate limiting

## Discord Limits
- Max 2000 chars per message
- Max 10 embeds per message
- Split large batches into multiple messages

## Development Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run scraper
python run.py

# Specific keywords only
python run.py --keywords "希少,メッキ"

# Dry run (no Discord)
python run.py --dry-run

# Verbose logging
python run.py --verbose
```

## Environment Variables
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
PROXY_URL=              # Optional
LOG_LEVEL=INFO
DB_PATH=./data/listings.db
```

## Testing Checklist
- [ ] Single keyword search returns results
- [ ] Parser extracts all fields correctly
- [ ] Database insert/dedup works
- [ ] Discord webhook receives messages
