import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        url = "https://omnijobs.io/en/search?jobFunction=data+science+and+analytics&onlyRemote=true&location=IN"
        print(f"Navigating to {url}...")
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print("Page loaded.")
            
            # Wait a bit for dynamic content
            await asyncio.sleep(5)
            
            content = await page.content()
            with open("job_trackers/omnijobs_source.html", "w") as f:
                f.write(content)
            print("Saved HTML to job_trackers/omnijobs_source.html")
            
            # Take a screenshot too
            await page.screenshot(path="job_trackers/omnijobs_screenshot.png")
            print("Saved screenshot to job_trackers/omnijobs_screenshot.png")
            
        except Exception as e:
            print(f"Error: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
