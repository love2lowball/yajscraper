#!/bin/bash
# Oracle Cloud VM Setup Script for Wheel Scraper Bot
# Run as: bash setup.sh

set -e

echo "=========================================="
echo "Wheel Scraper Bot - Oracle Cloud Setup"
echo "=========================================="

# Update system
echo "[1/7] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
echo "[2/7] Installing Python and dependencies..."
sudo apt install -y python3 python3-pip python3-venv git

# Clone repository (if not already cloned)
if [ ! -d "/home/ubuntu/yajscraper" ]; then
    echo "[3/7] Cloning repository..."
    cd /home/ubuntu
    git clone https://github.com/YOUR_USERNAME/yajscraper.git
else
    echo "[3/7] Repository already exists, pulling latest..."
    cd /home/ubuntu/yajscraper
    git pull
fi

cd /home/ubuntu/yajscraper

# Create virtual environment
echo "[4/7] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python packages
echo "[5/7] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
echo "[6/7] Creating directories..."
mkdir -p logs data

# Setup systemd service
echo "[7/7] Setting up systemd service..."
sudo cp deploy/wheelbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wheelbot

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Create .env file with your configuration:"
echo "   cp .env.example .env"
echo "   nano .env"
echo ""
echo "2. Add your Discord bot token and channel ID to .env"
echo ""
echo "3. Start the bot:"
echo "   sudo systemctl start wheelbot"
echo ""
echo "4. Check status:"
echo "   sudo systemctl status wheelbot"
echo ""
echo "5. View logs:"
echo "   tail -f logs/bot.log"
echo ""
