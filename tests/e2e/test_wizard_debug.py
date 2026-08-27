"""Playwright test for the Onboarding Wizard - debug version."""
import time
from playwright.sync_api import sync_playwright

def test_wizard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("http://localhost:5000")
        print(f"Page title: {page.title()}")

        # Get all links and buttons
        links = page.locator("a").all_text_contents()
        buttons = page.locator("button").all_text_contents()
        print(f"Links: {links[:10]}")
        print(f"Buttons: {buttons[:10]}")

        # Get page text content
        body_text = page.locator("body").inner_text()
        print(f"Body text (first 500 chars): {body_text[:500]}")

        browser.close()

if __name__ == "__main__":
    test_wizard()
