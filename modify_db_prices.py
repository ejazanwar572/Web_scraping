import sqlite3
from pathlib import Path

db_path = Path("data/zepto_prices_test.db")

def increase_prices():
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get 5 random products
    cursor.execute("SELECT product_hash, name, price FROM products LIMIT 5")
    products = cursor.fetchall()

    if not products:
        print("❌ No products found in database.")
        return

    print("Updating prices for the following products (doubling them):")
    for p_hash, name, price in products:
        new_price = price * 2
        cursor.execute("UPDATE products SET price = ? WHERE product_hash = ?", (new_price, p_hash))
        print(f"  - {name}: ₹{price} -> ₹{new_price}")

    conn.commit()
    conn.close()
    print("\n✅ Prices updated successfully. Run the scraper now to trigger alerts.")

if __name__ == "__main__":
    increase_prices()
