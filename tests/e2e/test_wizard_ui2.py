"""Playwright test for the Onboarding Wizard."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import time
from playwright.sync_api import sync_playwright

def test_wizard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("http://localhost:5000/symbols")
        time.sleep(3)

        body_text = page.locator("body").inner_text()
        print(f"Body text (first 1000 chars): {body_text[:1000]}")

        # Find all buttons
        all_buttons = page.locator("button").all_text_contents()
        print(f"All buttons: {all_buttons}")

        browser.close()

if __name__ == "__main__":
    test_wizard()
