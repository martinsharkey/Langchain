"""Test that duplication is removed and results display works."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import time
from playwright.sync_api import sync_playwright

def test_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("http://localhost:5000/symbols")
        time.sleep(2)

        body = page.locator("body").inner_text()

        # Check duplication is removed
        print("=== Duplication check ===")
        add_form_count = page.locator("text=Add Symbol").count()
        print(f"'Add Symbol' form headers: {add_form_count} (should be 0)")
        onboard_wizard_btns = page.locator("text=+ Onboard New Symbol").count()
        print(f"'+ Onboard New Symbol' buttons: {onboard_wizard_btns} (should be 1)")

        # Start onboarding via API
        print("\n=== Starting onboarding ===")
        result = page.evaluate("""
            async () => {
                const res = await fetch('/api/symbols/XAUUSD/onboard', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sessions: ['london'],
                        timeframes: ['M15'],
                        start_date: '2026-07-01',
                        end_date: '2026-07-10',
                        top_n: 3
                    })
                });
                return await res.json();
            }
        """)
        print(f"Started: {result.get('status')}")

        # Wait for completion
        for i in range(30):
            prog = page.evaluate("""
                async () => {
                    const res = await fetch('/api/onboarding/XAUUSD/progress');
                    return await res.json();
                }
            """)
            markers = prog.get("progress", [])
            last = markers[-1] if markers else {}
            if last.get("type") == "complete":
                print(f"  Completed after {i} polls")
                break
            time.sleep(2)

        # Check symbol in list
        print("\n=== Symbol list ===")
        status_data = page.evaluate("""
            async () => {
                const res = await fetch('/api/symbols');
                return await res.json();
            }
        """)
        symbols = status_data.get("symbols", [])
        xauusd = [s for s in symbols if s.get("symbol") == "XAUUSD"]
        print(f"Total symbols in list: {len(symbols)}")
        if xauusd:
            s = xauusd[0]
            print(f"XAUUSD: status={s.get('status')}, results={s.get('results_count')}")
        else:
            print("XAUUSD NOT in list")

        # Now navigate to the manage tab and check results display
        print("\n=== Results display ===")
        # Click on the symbol to expand it
        page.locator("text=XAUUSD").first.click()
        time.sleep(2)

        body2 = page.locator("body").inner_text()
        print(f"Has 'strategy combinations found': {'strategy combinations found' in body2}")
        print(f"Has 'Session': {'Session' in body2}")
        print(f"Has 'Profit Factor': {'PF' in body2}")

        browser.close()
        print("\n=== Test complete ===")

if __name__ == "__main__":
    test_page()
