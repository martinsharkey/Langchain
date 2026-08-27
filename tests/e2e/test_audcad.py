"""Test AUDCAD onboarding progress bar."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import time
from playwright.sync_api import sync_playwright

def test_audcad():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("http://localhost:5000/symbols")
        time.sleep(2)

        # Start onboarding via API (React onChange is test-hostile)
        result = page.evaluate("""
            async () => {
                const res = await fetch('/api/symbols/AUDCAD-ECN/onboard', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sessions: ['london', 'newyork'],
                        timeframes: ['M15'],
                        start_date: '2026-07-01',
                        end_date: '2026-07-15',
                        top_n: 5
                    })
                });
                return await res.json();
            }
        """)
        print(f"Onboard started: {result.get('status')}")
        print(f"Estimated: {result.get('estimated_seconds')}s")

        # Poll progress
        for i in range(30):
            prog = page.evaluate("""
                async () => {
                    const res = await fetch('/api/onboarding/AUDCAD-ECN/progress');
                    return await res.json();
                }
            """)
            markers = prog.get('progress', [])
            last = markers[-1] if markers else {}
            pct = 0
            for m in reversed(markers):
                if m.get('combinations_completed') and m.get('total_combinations'):
                    pct = round(m['combinations_completed'] / m['total_combinations'] * 100)
                    break
            if last.get('type') == 'complete':
                pct = 100
            print(f"  Poll {i}: type={last.get('type')}, pct={pct}, results={last.get('results_count', 'n/a')}")
            if last.get('type') in ('complete', 'cancelled'):
                break
            time.sleep(2)

        # Check results
        res_data = page.evaluate("""
            async () => {
                const res = await fetch('/api/onboarding/AUDCAD-ECN/results');
                return await res.json();
            }
        """)
        results = res_data.get('results', [])
        print(f"\nFinal results: {len(results)}")
        for r in results[:3]:
            print(f"  {r['session_display']} {r['timeframe']} {r['indicator'][:25]} pf={r['profit_factor']} end=£{r['end_balance']}")

        browser.close()
        print("\n=== AUDCAD test complete ===")

if __name__ == "__main__":
    test_audcad()
