#!/bin/bash

# IST is UTC+5:30
# User wants: Every 2 hours from 6 AM IST to 2 AM IST
# 6:00 AM IST = 00:30 UTC
# 8:00 AM IST = 02:30 UTC
# ...
# 2:00 AM IST = 20:30 UTC
# Cron schedule: 30 0,2,4,6,8,10,12,14,16,18,20 * * *

CRON_CMD="30 0,2,4,6,8,10,12,14,16,18,20 * * * cd /home/ubuntu/zepto_scraper && /home/ubuntu/zepto_scraper/venv/bin/python3 zepto_tracker_test.py >> /home/ubuntu/zepto_scraper/cron.log 2>&1"

# Check if cron job already exists to avoid duplicates
(crontab -l 2>/dev/null | grep -F "zepto_tracker_test.py") && echo "✅ Cron job already exists." || (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "✅ Cron job set up successfully!"
echo "📅 Schedule: Every 2 hours from 6 AM IST to 2 AM IST (00:30 to 20:30 UTC)"
echo "📋 Current Crontab:"
crontab -l
