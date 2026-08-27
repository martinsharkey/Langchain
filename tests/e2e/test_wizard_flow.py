"""Playwright test for the Onboarding Wizard - rendering + API flow."""
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

        # Verify the Symbol Onboarding page loads
        body = page.locator("body").inner_text()
        print("Page loaded:", "Symbol Onboarding" in body)
        print("Has 'Manage Symbols':", "Manage Symbols" in body)

        # Click "Onboard New Symbol"
        page.locator("text=+ Onboard New Symbol").first.click()
        time.sleep(1)

        # Verify wizard step 1 renders
        body1 = page.locator("body").inner_text()
        print("\n=== Step 1 (Symbol) renders ===")
        print("Has 'Select a symbol':", "Select a symbol" in body1)
        print("Has dropdown:", page.locator("select").count() > 0)
        print("Has 'Refresh' button:", "Refresh" in body1)

        # Verify symbols loaded in dropdown
        opt_count = page.locator("select option").count()
        print(f"Symbol options loaded: {opt_count}")

        # Verify step 2 renders (Sessions) - check stepper
        print("\n=== Step indicators ===")
        for step_name in ["Symbol", "Sessions", "Timeframes", "Period", "Summary"]:
            print(f"  '{step_name}' visible: {step_name in body1}")

        # Verify Next button exists (disabled until selection)
        next_btn = page.locator("button:has-text('Next')")
        print(f"\nNext button exists: {next_btn.count() > 0}")

        # --- Test the API flow directly (since React onChange is test-hostile) ---
        print("\n=== API Flow Test ===")

        # Test onboard API via page.evaluate (calls the React app's API)
        result = page.evaluate("""
            async () => {
                const res = await fetch('/api/symbols/BTCUSD/onboard', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sessions: ['london'],
                        timeframes: ['H1'],
                        start_date: '2026-07-01',
                        end_date: '2026-07-15',
                        top_n: 3
                    })
                });
                return await res.json();
            }
        """)
        print(f"Onboard API response: {result}")

        if result.get('status') == 'ok':
            task_id = result.get('task_id')
            print(f"Task started: {task_id}")
            print(f"Estimated seconds: {result.get('estimated_seconds')}")

            # Poll for progress
            time.sleep(5)
            for i in range(10):
                prog = page.evaluate("""
                    async () => {
                        const res = await fetch('/api/onboarding/BTCUSD/progress');
                        return await res.json();
                    }
                """)
                markers = prog.get('progress', [])
                last = markers[-1] if markers else {}
                print(f"  Poll {i}: type={last.get('type')}, completed={last.get('combinations_completed')}/{last.get('total_combinations')}")
                if last.get('type') in ('complete', 'cancelled', 'error'):
                    break
                time.sleep(3)

            # Check results
            res_data = page.evaluate("""
                async () => {
                    const res = await fetch('/api/onboarding/BTCUSD/results');
                    return await res.json();
                }
            """)
            results = res_data.get('results', [])
            print(f"\nResults count: {len(results)}")
            for r in results[:3]:
                print(f"  {r['session_display']} {r['timeframe']} {r['indicator'][:25]} pf={r['profit_factor']} end=£{r['end_balance']}")

        browser.close()
        print("\n=== Wizard + API test complete ===")

if __name__ == "__main__":
    test_wizard()
