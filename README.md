# Zepto Price Tracker

A Python script to scrape product prices from Zepto.com and track price changes over time.

## Features

- Scrapes products from Zepto categories
- Extracts product details: name, price, image, category
- Saves data to SQLite database with price history
- Exports data to JSON
- Tracks price drops over time
- Email/webhook alerts for price changes

## Setup

1. Install dependencies:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

2. Run the tracker:
```bash
source venv/bin/activate && python zepto_tracker.py
```

## Output

- Database: `data/zepto_prices.db`
- JSON export: `exports/zepto_products.json`

## Project Structure

```
Zepto_scrapper/
├── zepto_tracker.py          # Main scraper
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── alert_config*.json        # Alert configurations (for future use)
├── data/
│   └── zepto_prices.db       # SQLite database with scraped products
└── exports/
    └── zepto_products.json   # Latest product export
```