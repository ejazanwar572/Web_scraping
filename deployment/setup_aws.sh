#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting Server Setup for Zepto Scraper..."

# 1. Update System
echo "📦 Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Python and Pip
echo "🐍 Installing Python and dependencies..."
sudo apt-get install -y python3-pip python3-venv unzip

# 3. Create Project Directory (if running from a fresh upload)
# Assuming files are already here or cloned.

# 4. Set up Virtual Environment
echo "🛠️ Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# 5. Install Python Requirements
echo "📥 Installing Python libraries..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "⚠️ requirements.txt not found! Installing manually..."
    pip install playwright requests beautifulsoup4 pandas sqlalchemy lxml plotly flask schedule
fi

# 6. Install Playwright Browsers and System Dependencies
echo "🎭 Installing Playwright browsers and dependencies..."
playwright install chromium
sudo playwright install-deps chromium

# 7. Create Data Directory
mkdir -p data exports

echo "✅ Setup Complete!"
echo "To run the scraper:"
echo "  source venv/bin/activate"
echo "  python3 zepto_tracker_test.py"
