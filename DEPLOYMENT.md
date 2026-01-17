# Deployment Guide - Oracle Cloud Free Tier

This guide walks you through deploying the Wheel Scraper Discord Bot on Oracle Cloud's Always Free tier.

## Why Oracle Cloud Free Tier?

- **Truly free forever** (not a trial)
- ARM VM: 4 OCPUs, 24GB RAM (or AMD: 1 OCPU, 1GB RAM)
- 200GB block storage
- 10TB/month outbound data
- Multiple regions including Tokyo (good for Japan scraping)

## Prerequisites

1. Oracle Cloud account (free to create)
2. Discord account
3. Basic command line knowledge

---

## Part 1: Create Discord Bot

### Step 1: Create Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"**
3. Name it "Wheel Scraper" (or your choice)
4. Click **"Create"**

### Step 2: Create Bot

1. Go to **"Bot"** section in left sidebar
2. Click **"Add Bot"**
3. Under **"Privileged Gateway Intents"**, enable:
   - ✅ Message Content Intent
4. Click **"Reset Token"** and copy the token (save it securely!)

### Step 3: Invite Bot to Server

1. Go to **"OAuth2"** → **"URL Generator"**
2. Select scopes:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Select bot permissions:
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Attach Files
   - ✅ Read Message History
   - ✅ Use Slash Commands
4. Copy the generated URL and open it in browser
5. Select your server and authorize

### Step 4: Get Channel ID

1. In Discord, go to Settings → Advanced → Enable **Developer Mode**
2. Right-click the channel for notifications → **Copy ID**

### Step 5: Get Your User ID (for admin commands)

1. Right-click your username → **Copy ID**

---

## Part 2: Create Oracle Cloud VM

### Step 1: Sign Up

1. Go to [Oracle Cloud](https://www.oracle.com/cloud/free/)
2. Click **"Start for free"**
3. Complete registration (requires credit card for verification, but won't be charged)

### Step 2: Create VM Instance

1. Go to **Compute** → **Instances** → **Create Instance**
2. Configure:
   - **Name**: `wheelbot`
   - **Image**: Ubuntu 22.04 (or latest)
   - **Shape**: Click "Change Shape"
     - For ARM (recommended): Ampere A1, 1 OCPU, 6GB RAM
     - For AMD: VM.Standard.E2.1.Micro (1 OCPU, 1GB RAM)
   - **Networking**: Create new VCN or use existing
   - **SSH Key**: Upload your public key or generate new
3. Click **"Create"**

### Step 3: Configure Firewall (optional, for monitoring)

By default, only SSH (port 22) is open. The bot doesn't need additional ports.

### Step 4: Note Your Public IP

After instance is running, note the **Public IP Address**.

---

## Part 3: Deploy the Bot

### Step 1: Connect to VM

```bash
ssh ubuntu@YOUR_PUBLIC_IP
```

### Step 2: Run Setup Script

```bash
# Download and run setup script
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/yajscraper/main/deploy/setup.sh
bash setup.sh
```

Or manually:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv git

# Clone repository
cd /home/ubuntu
git clone https://github.com/YOUR_USERNAME/yajscraper.git
cd yajscraper

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt

# Create directories
mkdir -p logs data
```

### Step 3: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit with your values
nano .env
```

Add your values:
```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id
ADMIN_USER_IDS=your_user_id
```

### Step 4: Test the Bot

```bash
source venv/bin/activate
python bot.py
```

You should see:
```
Bot connected as Wheel Scraper#1234
Connected to 1 guild(s)
```

Press `Ctrl+C` to stop.

### Step 5: Setup as Service

```bash
# Copy service file
sudo cp deploy/wheelbot.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable wheelbot

# Start the service
sudo systemctl start wheelbot

# Check status
sudo systemctl status wheelbot
```

---

## Part 4: Bot Commands

Once running, use these slash commands in Discord:

### Search Commands
| Command | Description |
|---------|-------------|
| `/search <keyword>` | Quick search with one keyword |
| `/run <platform>` | Run full scraper (japan/us/all) |
| `/stop` | Stop current scraping |

### Status Commands
| Command | Description |
|---------|-------------|
| `/status` | Check scraper status |
| `/stats` | View database statistics |
| `/help` | Show all commands |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/schedule` | View/modify auto-scrape schedule |
| `/config` | View current configuration |
| `/cleanup <days>` | Delete old listings |

---

## Part 5: Maintenance

### View Logs

```bash
# Live logs
tail -f /home/ubuntu/yajscraper/logs/bot.log

# Or via journalctl
sudo journalctl -u wheelbot -f
```

### Restart Bot

```bash
sudo systemctl restart wheelbot
```

### Update Bot

```bash
cd /home/ubuntu/yajscraper
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart wheelbot
```

### Backup Database

```bash
cp /home/ubuntu/yajscraper/data/listings.db ~/listings_backup_$(date +%Y%m%d).db
```

---

## Troubleshooting

### Bot won't start

1. Check logs: `sudo journalctl -u wheelbot -n 50`
2. Verify .env file has correct values
3. Test manually: `python bot.py`

### Bot is online but commands don't work

1. Make sure bot has "applications.commands" scope
2. Commands may take up to 1 hour to sync globally
3. Try kicking and re-inviting the bot

### Scraping errors

1. Check if sites are accessible from Oracle's region
2. Japanese sites work best from Tokyo region
3. Consider using a proxy for US Craigslist if needed

### Rate limiting

The bot has built-in delays, but if you get rate limited:
1. Reduce scheduled frequency via `/schedule set 12`
2. Use fewer keywords

---

## Security Notes

1. Never share your bot token
2. Keep your Oracle Cloud SSH key secure
3. Regularly update system packages: `sudo apt update && sudo apt upgrade`
4. The bot token in .env should have restricted file permissions:
   ```bash
   chmod 600 .env
   ```

---

## Cost

**Oracle Cloud Always Free Tier** - $0/month
- 2 AMD VMs or 4 ARM OCPUs
- 200GB storage
- 10TB/month bandwidth

This bot uses minimal resources and fits easily within the free tier.
