"""Debug the wizard dropdown."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import time
from playwright.sync_api import sync_playwright

def test_wizard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("http://localhost:5000/symbols")
        time.sleep(2)

        page.locator("text=+ Onboard New Symbol").first.click()
        time.sleep(1)

        dropdown = page.locator("select").first
        options = dropdown.locator("option")
        count = options.count()
        print(f"Options count: {count}")
        for i in range(min(count, 5)):
            val = options.nth(i).get_attribute("value")
            txt = options.nth(i).inner_text()
            print(f"  [{i}] value='{val}' text='{txt[:40]}'")

        # Try selecting by clicking
        dropdown.click()
        time.sleep(0.5)
        # Press down arrow to select second option
        page.keyboard.press("ArrowDown")
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(1)

        # Check if Next is enabled
        next_btn = page.locator("button:has-text('Next')").first
        print(f"Next disabled: {next_btn.get_attribute('disabled')}")

        browser.close()

if __name__ == "__main__":
    test_wizard()
