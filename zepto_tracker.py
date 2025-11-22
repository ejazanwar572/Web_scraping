#!/usr/bin/env python3
"""
Zepto Price Tracker with Price Comparison Feature - Enhanced Version
Tracks price changes between runs and reports significant drops
"""
import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime
import sqlite3
import json
import re
import hashlib
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
    
    def __post_init__(self):
        if self.extracted_at is None:
            self.extracted_at = datetime.now()
    
    def get_hash(self) -> str:
        """Generate unique hash for product based on name and category"""
        content = f"{self.name.lower()}|{self.category.lower()}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


class ZeptoPriceTrackerWithComparison:
    def __init__(self, location_pin: str = "560001", price_drop_threshold: float = 20.0):
        self.location_pin = location_pin
        self.price_drop_threshold = abs(price_drop_threshold)
        self.base_url = "https://www.zepto.com"
        self.db_path = Path("data/zepto_prices.db")
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products 
                (product_hash, name, price, mrp, discount, category, url, image, rating, extracted_at, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_hash) DO UPDATE SET
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
                product_hash, product.name, product.price, product.mrp, product.discount,
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
        # Categories from Zepto - Testing with working categories first
        categories = [
            {
                'name': 'Fruits & Vegetables',
                'url': 'https://www.zepto.com/cn/fruits-vegetables/fruits-vegetables/cid/64374cfe-d06f-4a01-898e-c07c46462c36/scid/e78a8422-5f20-4e4b-9a9f-22a0e53962e3'
            },
            {
                'name': 'Bath n body-Deals',
                'url': 'https://www.zepto.com/cn/bath-body/top-deals/cid/26e64367-19ad-4f80-a763-42599d4215ee/scid/b493b1f8-c617-45e6-8a73-95239637bd5c'
            }
        ]
        
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
            browser = await p.chromium.launch(headless=False)
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
        
        # Export to JSON
        if all_products:
            export_data = []
            for prod in all_products:
                export_data.append({
                    'name': prod.name,
                    'price': prod.price,
                    'category': prod.category,
                    'image_url': prod.image[:100] + '...' if prod.image and len(prod.image) > 100 else prod.image,
                    'extracted_at': prod.extracted_at.isoformat()
                })
            
            with open('exports/zepto_products.json', 'w') as f:
                json.dump(export_data, f, indent=2)
            
            print(f"📄 Exported to exports/zepto_products.json")
        
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
                
                print(ctext(
                    f"{arrow} {drop['name'][:60]}... | "
                    f"₹{old_price:.2f} → ₹{new_price:.2f} "
                    f"({change:+.1f}%)",
                    color + Color.BOLD
                ))
    
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
        """Wait and scroll for products to load - simple bottom scrolling"""
        print("    🔄 Waiting for products to load...")
        
        # Initial wait for first load
        await asyncio.sleep(3)
        
        # Get initial count
        prev_count = 0
        stable_rounds = 0
        price_elements = page.locator('text=/₹[0-9]/')
        current_count = await price_elements.count()
        print(f"    📦 Initial products: {current_count}")
        
        # Scroll to bottom 5 times with waits
        for scroll_num in range(9):
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
                print(f"    ⏳ No new products (stable rounds: {stable_rounds})")
            if stable_rounds >= 3:
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
                
                # Get product URL
                link = container.find('a')
                url = ""
                if link and link.get('href'):
                    url = link['href']
                    if url.startswith('/'):
                        url = self.base_url + url
                
                # Get image URL
                image_url = img.get('src', '') if img else ''
                
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
        print(f"       • Successfully extracted: {stats['extracted']}")
        
        return products
    
    def _remove_duplicates(self, products: list) -> list:
        """Remove duplicate products by name"""
        seen = set()
        unique = []
        
        for prod in products:
            # Normalize name by removing extra spaces
            normalized_name = ' '.join(prod.name.split()).lower()
            
            if normalized_name not in seen:
                seen.add(normalized_name)
                unique.append(prod)
        
        return unique


async def main():
    """Main function with command line arguments"""
    parser = argparse.ArgumentParser(description='Zepto Price Tracker with Price Comparison')
    parser.add_argument('--threshold', type=float, default=20.0,
                        help='Price drop threshold percentage (default: 20.0)')
    parser.add_argument('--location', type=str, default='560001',
                        help='Location PIN code (default: 560001)')
    
    args = parser.parse_args()
    
    # Create directories
    Path("data").mkdir(exist_ok=True)
    Path("exports").mkdir(exist_ok=True)
    
    # Create tracker and run
    tracker = ZeptoPriceTrackerWithComparison(
        location_pin=args.location,
        price_drop_threshold=args.threshold
    )
    
    await tracker.scrape_all_categories()


if __name__ == "__main__":
    asyncio.run(main())