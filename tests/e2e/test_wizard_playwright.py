"""Playwright test for the Onboarding Wizard."""
import time
from playwright.sync_api import sync_playwright

def test_wizard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to the dashboard
        page.goto("http://localhost:5000")
        print(f"Page title: {page.title()}")

        # Take screenshot of the main page
        page.screenshot(path="wizard_test_01_main.png")
        print("Screenshot saved: wizard_test_01_main.png")

        # Look for the Symbol Onboarding link/tab
        # Try to navigate to onboarding
        onboarding_link = page.locator("text=Symbol Onboarding")
        if onboarding_link.count() > 0:
            onboarding_link.first.click()
            time.sleep(1)
            page.screenshot(path="wizard_test_02_onboarding.png")
            print("Screenshot saved: wizard_test_02_onboarding.png")

        # Look for "Onboard New Symbol" button
        onboard_btn = page.locator("text=Onboard New Symbol")
        if onboard_btn.count() > 0:
            onboard_btn.first.click()
            time.sleep(1)
            page.screenshot(path="wizard_test_03_wizard.png")
            print("Screenshot saved: wizard_test_03_wizard.png")

            # Check for the wizard steps
            symbol_step = page.locator("text=Symbol").first
            sessions_step = page.locator("text=Sessions").first
            print(f"Symbol step visible: {symbol_step.count() > 0}")
            print(f"Sessions step visible: {sessions_step.count() > 0}")

            # Check for symbol dropdown
            dropdown = page.locator("select")
            print(f"Dropdown count: {dropdown.count()}")

            if dropdown.count() > 0:
                # Get options
                options = dropdown.locator("option").all_text_contents()
                print(f"Symbol options (first 5): {options[:5]}")

        browser.close()
        print("Test complete")

if __name__ == "__main__":
    test_wizard()
