#!/usr/bin/env python3
"""
Zepto Price Tracker with Price Comparison Feature - Enhanced Version
Tracks price changes between runs and reports significant drops
"""
import asyncio
import sys
import os

from pathlib import Path
from datetime import datetime
import sqlite3
import json
import re
import hashlib
import requests
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Color constants for output
class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def ctext(text: str, color: str) -> str:
    return f"{color}{text}{Color.RESET}"

@dataclass
class Product:
    name: str
    price: float
    mrp: float
    discount: float
    category: str
    url: str
    image: str
    rating: float = 0.0
    extracted_at: datetime = None
    product_id: str = None  # Zepto product ID from URL
    
    def __post_init__(self):
        if self.extracted_at is None:
            self.extracted_at = datetime.now()
    
    def extract_zepto_id(self) -> str:
        """Extract unique product ID from Zepto URL (similar to Amazon's ASIN)"""
        if not self.url:
            return None
        
        import re
        # Try to extract from different URL patterns
        patterns = [
            r'/p/([^/?]+)',  # /p/product-id format
            r'/product/([^/?]+)',  # /product/product-id format
            r'/cn/[^/]+/[^/]+/cid/[^/]+/scid/([^/?]+)',  # /cn/category/subcategory/cid/xxx/scid/product-id
            r'id=([^&]+)',  # ?id=product-id query parameter
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.url)
            if match:
                return match.group(1)
        
        # If no ID found, use hash of URL as fallback
        return hashlib.md5(self.url.encode()).hexdigest()[:16]
    
    def get_hash(self) -> str:
        """Generate unique hash using product ID as primary identifier"""
        # First try to extract product ID from URL (most reliable)
        product_id = self.extract_zepto_id()
        
        if product_id:
            return product_id
        
        # Fallback to name-based hash if no URL/ID
        name_lower = self.name.lower()
        
        # Extract size information
        import re
        size_pattern = r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|pcs|pc|pack|units|unit))'
        size_match = re.search(size_pattern, name_lower)
        size_info = size_match.group(1) if size_match else ""
        
        # Extract key differentiators to distinguish similar products
        feature_patterns = [
            r'(dandruff|anti-dandruff|dandruff-care)',
            r'(hair.fall|hair-fall|hairfall)',
            r'(damage.care|damage-repair)',
            r'(smooth|silk|shine|smoothening)',
            r'(volume|volumizing|thick)',
            r'(color|colored|colour)',
            r'(men|male|gentleman)',
            r'(kids|children|baby)',
            r'(herbal|natural|organic)',
            r'(oily|dry|normal)',
            r'(daily|regular|classic)',
            r'(intensive|strong|extra)',
            r'(clinical|medicated)',
        ]
        
        features = []
        for pattern in feature_patterns:
            match = re.search(pattern, name_lower)
            if match:
                features.append(match.group(1))
        
        # Sort features to maintain consistent order
        feature_info = '|'.join(sorted(features)) if features else ""
        
        # Create unique hash with all differentiators
        content = f"{name_lower}|{self.category.lower()}|{size_info}|{feature_info}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


class ZeptoPriceTrackerWithComparison:
    def __init__(self, location_pin: str = "Arcade Gloria", price_drop_threshold: float = 20.0):
        self.location_pin = location_pin
        self.price_drop_threshold = abs(price_drop_threshold)
        self.base_url = "https://www.zepto.com"
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.db_path = Path("data/zepto_prices_Arcade_Gloria.db")
        self.db_path.parent.mkdir(exist_ok=True)
        self.init_database()
        
    def init_database(self):
        """Initialize database with updated schema for price tracking"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Main products table with unique identifier
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    product_hash TEXT PRIMARY KEY,
                    product_id TEXT,
                    name TEXT NOT NULL,
                    price REAL,
                    mrp REAL,
                    discount REAL,
                    category TEXT,
                    url TEXT,
                    image TEXT,
                    rating REAL,
                    extracted_at TEXT,
                    location TEXT
                )
            ''')
            
            # Migration: Add product_id column if it doesn't exist
            try:
                cursor.execute("ALTER TABLE products ADD COLUMN product_id TEXT")
            except sqlite3.OperationalError:
                pass  # Column likely already exists
            
            # Price history table for tracking all price changes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_hash TEXT,
                    name TEXT,
                    price REAL,
                    category TEXT,
                    extracted_at TEXT,
                    location TEXT
                )
            ''')
            
            conn.commit()
    
    def get_product_by_hash(self, product_hash: str) -> Optional[Dict]:
        """Get existing product by hash"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products WHERE product_hash = ?", (product_hash,))
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
    
    def save_or_update_product(self, product: Product) -> Dict:
        """Save or update product and return price change info"""
        product_hash = product.get_hash()
        existing = self.get_product_by_hash(product_hash)
        
        result = {
            'hash': product_hash,
            'name': product.name,
            'price': product.price,
            'old_price': None,
            'price_diff': 0,
            'pct_change': 0,
            'url': product.url,
            'is_new': existing is None
        }
        
        if existing:
            result['old_price'] = existing['price']
            if existing['price'] and existing['price'] > 0:
                price_diff = product.price - existing['price']
                pct_change = (price_diff / existing['price']) * 100.0
                result['price_diff'] = price_diff
                result['pct_change'] = pct_change
        
        # Upsert product
        product_id = product.extract_zepto_id()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products 
                (product_hash, product_id, name, price, mrp, discount, category, url, image, rating, extracted_at, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_hash) DO UPDATE SET
                    product_id=excluded.product_id,
                    name=excluded.name,
                    price=excluded.price,
                    mrp=excluded.mrp,
                    discount=excluded.discount,
                    category=excluded.category,
                    url=excluded.url,
                    image=excluded.image,
                    rating=excluded.rating,
                    extracted_at=excluded.extracted_at,
                    location=excluded.location
            ''', (
                product_hash, product_id, product.name, product.price, product.mrp, product.discount,
                product.category, product.url, product.image, product.rating,
                product.extracted_at.isoformat(), self.location_pin
            ))
            
            # Add to price history
            cursor.execute('''
                INSERT INTO price_history 
                (product_hash, name, price, category, extracted_at, location)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (product_hash, product.name, product.price, product.category,
                  product.extracted_at.isoformat(), self.location_pin))
            
            conn.commit()
        
        return result
    
    async def scrape_all_categories(self):
        """Scrape all categories with price comparison"""
        # Load categories from external JSON file
        try:
            with open('categories.json', 'r') as f:
                categories = json.load(f)
        except FileNotFoundError:
            print("❌ categories.json not found. Please create the file.")
            return []
        except json.JSONDecodeError:
            print("❌ Error parsing categories.json. Please check the format.")
            return []
        
        # Create necessary directories
        Path("data").mkdir(exist_ok=True)
        Path("exports").mkdir(exist_ok=True)
        
        # Take snapshot before scraping for comparison
        print(ctext("🔍 Analyzing existing products for price changes...", Color.CYAN))
        prev_snapshot = self._get_price_snapshot()
        print(f"Found {len(prev_snapshot)} products in database")
        
        all_products = []
        product_updates = []
        new_products_count = 0
        
        print("\n" + ctext("🛒 Zepto Price Tracker with Comparison - Enhanced", Color.BOLD))
        print("=" * 60)
        print(f"📍 Location: {self.location_pin}")
        print(f"📉 Price Drop Threshold: {self.price_drop_threshold}%")
        print(f"\n📦 Scanning {len(categories)} categories...\n")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            
            for i, category in enumerate(categories, 1):
                print(f"[{i}/{len(categories)}] {category['name']}")
                
                try:
                    page = await context.new_page()
                    
                    # Go to category
                    await page.goto(category['url'], wait_until='domcontentloaded')
                    await asyncio.sleep(5)  # Increased initial wait
                    
                    # Set location if needed
                    await self._set_location(page)
                    
                    # Wait for products to load with scrolling
                    await self._wait_for_products(page)
                    
                    # Get HTML and extract products
                    html = await page.content()
                    products = self._extract_products(html, category['name'])
                    
                    # Remove duplicates
                    unique_products = self._remove_duplicates(products)
                    
                    if unique_products:
                        print(f"    Found {len(unique_products)} unique products")
                        
                        # Save/update products and track changes
                        for product in unique_products:
                            update_info = self.save_or_update_product(product)
                            product_updates.append(update_info)
                            if update_info['is_new']:
                                new_products_count += 1
                        
                        all_products.extend(unique_products)
                        
                        # Show sample
                        for j, prod in enumerate(unique_products[:3], 1):
                            print(f"    {j}. {prod.name[:50]}... - ₹{prod.price}")
                    else:
                        print(f"  ⚠️  No products found")
                    
                    await page.close()
                    await asyncio.sleep(1)  # Reduced rate limiting
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            
            await browser.close()
        
        # Analyze price changes
        major_drops = self._analyze_price_changes(product_updates, prev_snapshot)
        
        # Summary
        print(f"\n" + "=" * 60)
        print(f"✅ Scraping Complete!")
        print(f"📊 Total unique products: {len(all_products)}")
        print(f"🆕 New products: {new_products_count}")
        print(f"🔄 Products updated: {len([u for u in product_updates if not u['is_new']])}")
        print(f"🗄️  Database: {self.db_path}")
        
        # Export to JSON - DISABLED per user request
        # if all_products:
        #     export_data = []
        #     for prod in all_products:
        #         export_data.append({
        #             'name': prod.name,
        #             'price': prod.price,
        #             'category': prod.category,
        #             'image_url': prod.image[:100] + '...' if prod.image and len(prod.image) > 100 else prod.image,
        #             'extracted_at': prod.extracted_at.isoformat()
        #         })
        #     
        #     with open('exports/zepto_products.json', 'w') as f:
        #         json.dump(export_data, f, indent=2)
        #     
        #     print(f"📄 Exported to exports/zepto_products.json")
        
        # Report major price drops
        self._report_price_drops(major_drops)
        
        print("\n" + "=" * 60)
        print("✅ Done! Run again to track price changes.")
        
        return all_products
    
    def _get_price_snapshot(self) -> Dict[str, float]:
        """Get current price snapshot from database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT product_hash, price FROM products")
            return {row[0]: row[1] for row in cursor.fetchall()}
    
    def _analyze_price_changes(self, updates: List[Dict], prev_snapshot: Dict[str, float]) -> List[Dict]:
        """Analyze price changes and identify major drops"""
        major_drops = []
        
        for update in updates:
            if not update['is_new'] and update['old_price'] and update['price']:
                pct_change = update['pct_change']
                if pct_change <= -self.price_drop_threshold:  # Price drop
                    major_drops.append(update)
        
        # Sort by percentage drop
        major_drops.sort(key=lambda x: abs(x['pct_change']), reverse=True)
        return major_drops
    
    def send_slack_alert(self, drops: List[Dict]):
        """Send Slack alert for major price drops"""
        if not drops or not self.slack_webhook_url:
            return

        message_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📉 Major Price Drops Detected (≥ {self.price_drop_threshold}%)",
                    "emoji": True
                }
            },
            {
                "type": "divider"
            }
        ]

        for drop in drops[:10]:  # Limit to top 10 to avoid hitting message size limits
            old_price = drop['old_price']
            new_price = drop['price']
            change = drop['pct_change']
            name = drop['name']
            url = drop.get('url', 'N/A')
            
            # Get additional product info
            product_info = self.get_product_by_hash(drop['hash'])
            category = product_info['category'] if product_info else "Unknown"

            product_section = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{url}|{name}>*\nCategory: {category}\n*₹{old_price:.2f}* → *₹{new_price:.2f}* ({change:+.1f}%)"
                }
            }
            message_blocks.append(product_section)
            message_blocks.append({"type": "divider"})

        if len(drops) > 10:
            message_blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"...and {len(drops) - 10} more products."
                    }
                ]
            })

        payload = {"blocks": message_blocks}
        
        try:
            response = requests.post(self.slack_webhook_url, json=payload)
            if response.status_code == 200:
                print(ctext("✅ Slack alert sent successfully!", Color.GREEN))
            else:
                print(ctext(f"❌ Failed to send Slack alert: {response.status_code} - {response.text}", Color.RED))
        except Exception as e:
            print(ctext(f"❌ Error sending Slack alert: {e}", Color.RED))

    def _report_price_drops(self, drops: List[Dict]):
        """Report major price drops with colorized output"""
        print("\n" + "=" * 60)
        print(ctext(f"📉 MAJOR PRICE DROPS (≥ {self.price_drop_threshold}%)", Color.BOLD + Color.RED))
        print("=" * 60)
        
        if not drops:
            print(ctext("No major price drops detected this run.", Color.YELLOW))
        else:
            for drop in drops:
                old_price = drop['old_price']
                new_price = drop['price']
                change = drop['pct_change']
                
                if change < 0:
                    arrow = "↓"
                    color = Color.RED
                else:
                    arrow = "↑"
                    color = Color.GREEN
                
                # Get additional product info from database
                product_info = self.get_product_by_hash(drop['hash'])
                category = product_info['category'] if product_info else "Unknown"
                
                # Display full product name without truncation
                print(ctext(
                    f"{arrow} {drop['name']} | "
                    f"₹{old_price:.2f} → ₹{new_price:.2f} "
                    f"({change:+.1f}%)",
                    color + Color.BOLD
                ))
                
                # Additional details
                print(ctext(f"    📁 Category: {category}", Color.BLUE))
                if drop.get('url'):
                    print(ctext(f"    🔗 Link: {drop['url']}", Color.CYAN))
                
                # Add separator between products
                print()
        
        # Send Slack alert
        if drops:
            self.send_slack_alert(drops)
    
    async def _set_location(self, page):
        """Set delivery location"""
        try:
            pin_input = page.locator('input[placeholder*="Enter location" i]')
            if await pin_input.count() > 0:
                await pin_input.first.fill(self.location_pin)
                await pin_input.first.press('Enter')
                await asyncio.sleep(3)
        except:
            pass
    
    async def _wait_for_products(self, page):
        """Wait and scroll for products to load - Infinite Scroll Implementation"""
        print("    🔄 Starting infinite scroll...")
        
        # Initial wait
        await asyncio.sleep(3)
        
        prev_count = 0
        stable_rounds = 0
        max_scrolls = 100  # Increased limit for infinite scroll
        price_elements = page.locator('text=/₹[0-9]/')
        
        current_count = await price_elements.count()
        print(f"    📦 Initial products: {current_count}")
        
        for scroll_num in range(max_scrolls):
            # Scroll to bottom
            await page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.9));")
            await asyncio.sleep(1.5)  # Wait for content to load
            
            # Check for new products
            current_count = await price_elements.count()
            
            if current_count > prev_count:
                print(f"    📦 New products loaded: {current_count} (scroll #{scroll_num+1})")
                prev_count = current_count
                stable_rounds = 0
            else:
                stable_rounds += 1
                # print(f"    ⏳ No new products (stable rounds: {stable_rounds})")
            
            # Exit if stable for too long
            if stable_rounds >= 5:
                print(f"    🛑 Product count stable for {stable_rounds} rounds. Stopping.")
                break
        
        # Final count
        final_count = await price_elements.count()
        print(f"    ✨ Total products detected: {final_count}")
    
    def _extract_products(self, html: str, category: str) -> list:
        """Extract products from HTML"""
        # Use default parser instead of lxml to avoid dependency issues
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # Multiple selector patterns for different page layouts
        selector_patterns = [
            ['cslgId', 'cTH4Df'],  # Original selectors
            ['nWj0X', 'u-flex'],   # Additional pattern found
            ['gF6HU'],             # Single class pattern
            ['SJno8'],             
        ]
        
        all_containers = []
        
        # Try different selector patterns
        for selectors in selector_patterns:
            containers = soup.find_all('div', class_=selectors)
            if containers:
                all_containers.extend(containers)
        
        # Also try by data attributes and generic patterns
        generic_containers = soup.find_all(['div', 'article'], 
                                         attrs={'data-test': lambda x: x and 'product' in x.lower()}) or \
                          soup.find_all(['div', 'article'], 
                                       class_=lambda x: x and any(keyword in str(x).lower() 
                                                                 for keyword in ['product', 'item', 'card', 'tile']))
        
        all_containers.extend(generic_containers)
        
        # Remove duplicates
        unique_containers = []
        seen = set()
        for container in all_containers:
            container_id = id(container)
            if container_id not in seen:
                seen.add(container_id)
                unique_containers.append(container)
        
        print(f"    Found {len(unique_containers)} product containers")
        
        # Track extraction stats
        stats = {
            'total_containers': len(unique_containers),
            'no_image': 0,
            'invalid_name': 0,
            'no_price': 0,
            'no_url': 0,
            'extracted': 0
        }
        
        for container in unique_containers:
            try:
                # Get product image and name - multiple ways
                name = None
                
                # Try from image alt text
                img = container.find('img')
                if not img or not img.get('alt'):
                    stats['no_image'] += 1
                    continue
                
                name = img.get('alt').strip()
                
                # Try from title or name elements
                if not name or len(name) < 5:
                    name_elem = container.find(['h1', 'h2', 'h3', 'h4', 'span', 'div'], 
                                             class_=lambda x: x and any(keyword in str(x).lower() 
                                                                     for keyword in ['name', 'title', 'product']))
                    if name_elem:
                        name = name_elem.get_text().strip()
                
                if not name or len(name) < 5 or any(skip in name.lower() for skip in ['new launches', 'view all', 'shop now', 'advert']):
                    stats['invalid_name'] += 1
                    continue
                
                # Skip generic category names that aren't actual products
                if name.strip().lower() in ['top picks', 'top deals', 'shampoos', 'facewash', 'soaps', 'shower gels', 'toothpaste', 'conditioner', 'oils']:
                    stats['invalid_name'] += 1
                    continue
                
                # Extract size/quantity information to ensure uniqueness
                # Look for patterns like "1 L", "500 ml", "1 pc", etc. in the container text
                container_text = container.get_text(" ", strip=True)
                size_pattern = r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|pcs|pc|pack|units|unit)\b)'
                
                # Find all size matches in the container text
                size_matches = re.findall(size_pattern, container_text, re.IGNORECASE)
                
                if size_matches:
                    found_sizes = []
                    for size in size_matches:
                        # Normalize size string for comparison
                        size = ' '.join(size.split())
                        if size.lower() not in name.lower() and size.lower() not in [s.lower() for s in found_sizes]:
                            found_sizes.append(size)
                    
                    if found_sizes:
                        # Append all found sizes to ensure uniqueness
                        suffix = " (" + ", ".join(found_sizes) + ")"
                        name = f"{name}{suffix}"
                
                # Get price - multiple patterns
                price = None
                
                # Try direct text search for rupee symbol
                price_text = container.get_text()
                price_matches = re.findall(r'₹\s*([\d,]+\.?\d*)', price_text)
                if price_matches:
                    try:
                        price = float(price_matches[0].replace(',', ''))
                    except:
                        pass
                
                # Try specific price elements
                if not price:
                    price_selectors = container.find_all(['span', 'div'], 
                                                       class_=lambda x: x and any(keyword in str(x).lower() 
                                                                                  for keyword in ['price', 'cost', 'amount', 'rupee', 'rs']))
                    for elem in price_selectors:
                        text = elem.get_text()
                        match = re.search(r'₹\s*([\d,]+\.?\d*)', text)
                        if match:
                            try:
                                price = float(match.group(1).replace(',', ''))
                                break
                            except:
                                pass
                
                if not price or price <= 0:
                    stats['no_price'] += 1
                    continue
                
                # Get product URL (must be actual product link, not category link)
                link = container.find('a')
                # If no link found inside, check if the container itself is wrapped in a link
                if not link:
                    link = container.find_parent('a')
                
                url = ""
                if link and link.get('href'):
                    href = link['href'].strip()
                    
                    # Debug: Print a few URLs to understand the pattern
                    if len(products) < 3:
                        print(f"    🔍 DEBUG URL: {href}")
                    
                    # Skip category/section links - only keep product-specific links
                    # Category links usually contain '/cid/' or '/scid/' without product-specific paths
                    # Whitelist /pn/ (Product Name) and /pvid/ (Product Variant ID)
                    if any(skip in href for skip in ['/cid/', '/scid/']) and not any(product in href for product in ['/p/', '/product/', '?id=', '/pn/', '/pvid/']):
                        # This is likely a category link, skip it
                        url = ""
                    elif href.startswith('/'):
                        url = self.base_url.rstrip('/') + href
                    else:
                        url = href
                # Get image URL
                image_url = img.get('src', '') if img else ''
                
                # TEMPORARILY DISABLED: Zepto might not have individual product pages
                # Skip products without individual URLs (likely category/section items)
                # if not url:
                #     stats['no_url'] += 1
                #     continue
                
                # Create product
                product = Product(
                    name=name[:100],
                    price=price,
                    mrp=price,
                    discount=0,
                    category=category,
                    url=url,
                    image=image_url,
                    rating=0
                )
                
                products.append(product)
                stats['extracted'] += 1
                
            except Exception as e:
                continue
        
        # Print extraction stats
        print(f"    📊 Extraction stats:")
        print(f"       • No image: {stats['no_image']}")
        print(f"       • Invalid name: {stats['invalid_name']}")
        print(f"       • No price: {stats['no_price']}")
        print(f"       • No individual URL (skipped): {stats['no_url']}")
        print(f"       • Successfully extracted: {stats['extracted']}")
        
        return products
    
    def _remove_duplicates(self, products: list) -> list:
        """Remove duplicate products by name"""
        seen = set()
        unique = []
        
        # print(f"    🔍 Checking for duplicates among {len(products)} extracted items...")
        
        for prod in products:
            # Normalize name by removing extra spaces
            normalized_name = ' '.join(prod.name.split()).lower()
            
            if normalized_name not in seen:
                seen.add(normalized_name)
                unique.append(prod)
            else:
                # Log the duplicate for verification (optional, can be noisy)
                # print(f"      ⚠️  Duplicate found (skipping): {prod.name[:50]}...")
                pass
        
        return unique


async def main():
    """Main function"""
    # Create tracker and run with hardcoded defaults
    tracker = ZeptoPriceTrackerWithComparison()
    
    await tracker.scrape_all_categories()


if __name__ == "__main__":
    asyncio.run(main())
