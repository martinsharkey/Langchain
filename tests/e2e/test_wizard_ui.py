"""Playwright test for the Onboarding Wizard."""
import time
from playwright.sync_api import sync_playwright

def test_wizard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate directly to the symbols page
        page.goto("http://localhost:5000/symbols")
        time.sleep(2)
        print(f"Page title: {page.title()}")

        # Get page text
        body_text = page.locator("body").inner_text()
        print(f"Body text (first 800 chars): {body_text[:800]}")

        # Check for wizard elements
        onboard_btn = page.locator("text=Onboard New Symbol")
        print(f"Onboard New Symbol button count: {onboard_btn.count()}")

        # Click the onboard button if present
        if onboard_btn.count() > 0:
            onboard_btn.first.click()
            time.sleep(1)

            # Check for wizard steps
            body_text2 = page.locator("body").inner_text()
            print(f"After click (first 800 chars): {body_text2[:800]}")

            # Check for symbol dropdown
            dropdown = page.locator("select")
            print(f"Dropdown count: {dropdown.count()}")

            if dropdown.count() > 0:
                options = dropdown.locator("option").all_text_contents()
                print(f"Symbol options (first 5): {options[:5]}")

            # Check for Next button
            next_btn = page.locator("button:has-text('Next')")
            print(f"Next button count: {next_btn.count()}")

        browser.close()
        print("Test complete")

if __name__ == "__main__":
    test_wizard()
