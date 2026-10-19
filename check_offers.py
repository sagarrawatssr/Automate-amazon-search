import asyncio
from playwright.async_api import async_playwright

SEARCH_URL = "https://www.amazon.in/s?k=milton+1+litre+vacuum+insulated+bottle"
BASE_DOMAIN = "https://www.amazon.in"

async def main():
    async with async_playwright() as p:
        # Launch browser with stealth headers
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-IN"
        )
        page = await context.new_page()

        print(f"Navigating to search page: {SEARCH_URL}")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Collect product links from search results (ignoring ads/sponsored links)
        links = await page.eval_on_selector_all(
            "a.a-link-normal.s-no-outline",
            "elements => elements.map(e => e.getAttribute('href'))"
        )

        product_urls = []
        for href in links:
            if href and "/dp/" in href:
                full_url = BASE_DOMAIN + href.split("?")[0]
                if full_url not in product_urls:
                    product_urls.append(full_url)

        print(f"Discovered {len(product_urls)} candidate product links. Checking SBI offers...\n")

        eligible_products = []

        # Inspect up to first 12 products
        for idx, url in enumerate(product_urls[:12], 1):
            try:
                prod_page = await context.new_page()
                await prod_page.goto(url, wait_until="domcontentloaded", timeout=25000)
                await prod_page.wait_for_timeout(2000)

                # Fetch page HTML and visible offer text
                content = await prod_page.content()
                title_elem = await prod_page.query_selector("#productTitle")
                title = (await title_elem.inner_text()).strip() if title_elem else "Unknown Product"

                # Check if SBI discount exists in the offers container or raw HTML
                is_sbi_eligible = "SBI" in content and ("Bank Offer" in content or "Instant Discount" in content)

                if is_sbi_eligible:
                    print(f"[{idx}] MATCH FOUND!")
                    print(f"Title: {title}")
                    print(f"URL: {url}\n")
                    eligible_products.append({"title": title, "url": url})
                else:
                    print(f"[{idx}] Excluded: No active SBI bank offer on {url}")

                await prod_page.close()
            except Exception as e:
                print(f"[{idx}] Error reading {url}: {e}")

        await browser.close()

        # Write matching URLs to file for workflow artifact
        with open("sbi_eligible_bottles.txt", "w", encoding="utf-8") as f:
            for item in eligible_products:
                f.write(f"{item['title']}\n{item['url']}\n\n")

if __name__ == "__main__":
    asyncio.run(main())
