"""Test onboarding with VectorBT activity + symbol list."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import time
from playwright.sync_api import sync_playwright

def test_wizard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("http://localhost:5000")
        time.sleep(1)

        # Start onboarding for a fresh symbol
        result = page.evaluate("""
            async () => {
                const res = await fetch('/api/symbols/AUDCAD-ECN/onboard', {
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
        print(f"Onboard started: {result.get('status')}")

        # Poll progress + activity
        for i in range(20):
            data = page.evaluate("""
                async () => {
                    const [prog, act] = await Promise.all([
                        fetch('/api/onboarding/AUDCAD-ECN/progress').then(r => r.json()),
                        fetch('/api/onboarding/AUDCAD-ECN/activity').then(r => r.json()),
                    ]);
                    return { prog, act };
                }
            """)
            markers = data.get("prog", {}).get("progress", [])
            last = markers[-1] if markers else {}
            latest_act = data.get("act", {}).get("latest", {}) or {}
            pct = 0
            for m in reversed(markers):
                if m.get("combinations_completed") and m.get("total_combinations"):
                    pct = round(m["combinations_completed"] / m["total_combinations"] * 100)
                    break
            if last.get("type") == "complete":
                pct = 100
            act_str = f", testing: {latest_act.get('name', '?')} ({latest_act.get('index', '?')}/{latest_act.get('total', '?')})" if latest_act.get("name") else ""
            print(f"  Poll {i}: type={last.get('type')}, pct={pct}{act_str}")
            if last.get("type") in ("complete", "cancelled"):
                break
            time.sleep(2)

        # Check symbol appears in status list
        status_data = page.evaluate("""
            async () => {
                const res = await fetch('/api/symbols');
                return await res.json();
            }
        """)
        symbols = status_data.get("symbols", [])
        audcad = [s for s in symbols if s.get("symbol") == "AUDCAD-ECN"]
        print(f"\nSymbol list count: {len(symbols)}")
        if audcad:
            s = audcad[0]
            print(f"AUDCAD-ECN in list: status={s.get('status')}, results={s.get('results_count')}")
        else:
            print("AUDCAD-ECN NOT found in symbol list")

        browser.close()
        print("\n=== Test complete ===")

if __name__ == "__main__":
    test_wizard()
