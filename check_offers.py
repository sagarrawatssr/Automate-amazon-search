import asyncio
from playwright.async_api import async_playwright

SEARCH_URL = "https://www.amazon.in/s?k=milton+1+litre+vacuum+insulated+bottle&ref=nb_sb_noss"
BASE_DOMAIN = "https://www.amazon.in"

async def check_captcha(page):
    content = await page.content()
    if "api-services-support@amazon.com" in content or "Type the characters you see in this image" in content:
        return True
    return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            }
        )

        page = await context.new_page()

        # Evade navigator.webdriver detection
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        print(f"Navigating to search query...")
        response = await page.goto(SEARCH_URL, wait_until="networkidle", timeout=45000)

        if await check_captcha(page):
            print("❌ Amazon served a CAPTCHA on the search page (Datacenter IP flagged).")
            await browser.close()
            return

        # Extract product ASIN links
        await page.wait_for_timeout(2000)
        product_elements = await page.query_selector_all("div[data-asin]")
        
        product_urls = []
        for el in product_elements:
            asin = await el.get_attribute("data-asin")
            if asin and len(asin) == 10:
                url = f"https://www.amazon.in/dp/{asin}"
                if url not in product_urls:
                    product_urls.append(url)

        print(f"Discovered {len(product_urls)} candidate Milton bottles. Inspecting for SBI offer...\n")

        if not product_urls:
            print("⚠️ 0 links found on search page. Inspecting search page layout...")
            title = await page.title()
            print(f"Page title was: {title}")

        eligible_products = []

        # Check the first 10 products
        for idx, url in enumerate(product_urls[:10], 1):
            try:
                prod_page = await context.new_page()
                await prod_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Check for product-page CAPTCHA
                if await check_captcha(prod_page):
                    print(f"[{idx}] Blocked by CAPTCHA on {url}")
                    await prod_page.close()
                    continue

                # Scroll down smoothly to trigger lazy-loaded bank offer drawer
                await prod_page.evaluate("window.scrollBy(0, 600)")
                await prod_page.wait_for_timeout(2500)

                # Fetch page content and title
                content = await prod_page.content()
                title_elem = await prod_page.query_selector("#productTitle")
                title = (await title_elem.inner_text()).strip() if title_elem else "Milton Bottle"

                # Check for SBI promo conditions in text
                has_sbi = "SBI" in content and any(kw in content for kw in ["Bank Offer", "Instant Discount", "10%"])

                if has_sbi:
                    print(f"[{idx}] ✅ MATCH FOUND!")
                    print(f"Name: {title}")
                    print(f"Link: {url}\n")
                    eligible_products.append({"title": title, "url": url})
                else:
                    print(f"[{idx}] ❌ No SBI offer on {url}")

                await prod_page.close()
                await asyncio.sleep(1)  # Throttling to prevent IP ban
            except Exception as e:
                print(f"[{idx}] Error parsing {url}: {e}")

        await browser.close()

        # Output results to file
        with open("sbi_eligible_bottles.txt", "w", encoding="utf-8") as f:
            if eligible_products:
                for item in eligible_products:
                    f.write(f"Product: {item['title']}\nURL: {item['url']}\n\n")
            else:
                f.write("No matching items found or datacenter IP was blocked by Amazon.")

        print(f"\nCompleted! Found {len(eligible_products)} eligible bottle links.")

if __name__ == "__main__":
    asyncio.run(main())
