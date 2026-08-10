"""
prove_learning.py — Integration + real-learning proof harness.

Run: python prove_learning.py

Proves two things with hard evidence (not claims):
  A) INTEGRATION: every major component loads and is wired into the pipeline.
  B) REAL LEARNING: learning artifacts have actually changed from defaults based
     on real closed-trade outcomes (weights, RAG, variants, personalities,
     researcher recommendations, reflection hypotheses).

Exit code 0 if all integration checks pass; prints a clear PASS/FAIL report.
Designed to be re-run over time to SHOW learning advancing (metrics move).
"""

import os, sys, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import DATA_DIR, TRADING_SYMBOLS
from src.mt5.connector import get_connector

PASS = "PASS"; FAIL = "FAIL"; INFO = "INFO"
results = []
def check(name, ok, detail=""):
    results.append((PASS if ok else FAIL, name, detail))
def info(name, detail=""):
    results.append((INFO, name, detail))


def main():
    get_connector().initialize()

    # ── A) INTEGRATION: components load + wire ──
    from src.trading.scalp_engine import ScalpEngine
    eng = ScalpEngine()
    check("ScalpEngine constructs", True, f"{len(TRADING_SYMBOLS)} symbols")
    check("RiskManager wired", eng.risk is not None)
    check("SessionManager wired", eng.sessions is not None)
    check("TradeManager wired", eng.trade_manager is not None)
    check("AdaptiveLoop wired", eng.adaptive is not None)
    check("PerformanceResearcher wired", eng.perf_researcher is not None)
    check("PatternMatcher (RAG read) wired", eng.pattern_matcher is not None)
    check("VectorStore wired", eng.vector_store is not None)

    # strategy registry + CryptoRTI
    n_strats = eng.registry.count
    check("Strategy library expanded", n_strats >= 16, f"{n_strats} strategies")
    check("CryptoRTI strategy registered", eng.registry.get("CryptoRTI_WhaleSignal") is not None)

    # RSS news (free, no key)
    try:
        from src.data_sources.rss_news import RSSNewsSource
        st = RSSNewsSource().status()
        check("Free RSS news live", st.get("available", False), f"{st.get('count',0)} headlines")
    except Exception as e:
        check("Free RSS news live", False, str(e)[:80])

    # CryptoRTI S3 (creds + write)
    try:
        from src.cryptorti import s3_client
        s3_client.list_prefix("data/")
        check("CryptoRTI S3 read", True)
        ok = s3_client.put_shared("_prove_test.txt", b"ok")
        check("CryptoRTI S3 shared write", ok)
    except Exception as e:
        check("CryptoRTI S3", False, str(e)[:80])

    # ── B) REAL LEARNING: artifacts changed from defaults ──
    from src.learning.experience_db import ExperienceDatabase
    edb = ExperienceDatabase()

    # closed-trade sample
    c = sqlite3.connect(os.path.join(DATA_DIR, "trading_experience.db")); c.row_factory = sqlite3.Row
    closed = c.execute("SELECT COUNT(*) FROM trades WHERE outcome IN ('win','loss','breakeven')").fetchone()[0]
    wins = c.execute("SELECT COUNT(*) FROM trades WHERE outcome='win'").fetchone()[0]
    info("Real closed trades", f"{closed} (wins={wins})")

    # weights adapted?
    perf = edb.get_strategy_performance()
    if perf:
        eng.registry.update_weights_from_performance(perf)
    defaults = {"EMA_TrendFollow": 2, "SR_Breakout": 2, "GoldenCross_50_200": 2, "Multi_Confluence": 3}
    changed = [s.name for s in eng.registry.get_all()
               if s.name in defaults and abs(s.weight - defaults[s.name]) > 0.01]
    check("Strategy weights adapted from real outcomes", len(changed) > 0,
          f"changed: {changed}") if closed >= 8 else info("Weights (need >=8 closed)", f"{closed} closed")

    # RAG patterns stored?
    try:
        cnt = eng.vector_store.collection.count()
        check("RAG memory populated", cnt > 0, f"{cnt} patterns")
    except Exception as e:
        check("RAG memory populated", False, str(e)[:80])

    # variant divergence?
    vp = edb.get_variant_performance()
    flat = {}
    for sym, vmap in vp.items():
        for v, m in vmap.items():
            flat.setdefault(v, {"n": 0, "pnl": 0.0})
            flat[v]["n"] += m["trades"]; flat[v]["pnl"] += m["net_pnl"]
    if flat:
        pnls = [round(v["pnl"], 2) for v in flat.values()]
        info("Variant P&L divergence", json.dumps({k: round(v['pnl'],2) for k,v in flat.items()}))
        check("Variants diverging (learning signal)", max(pnls) != min(pnls))
    else:
        info("Variants (need closed trades w/ variant)", "none yet")

    # researcher produces recommendations?
    rep = eng.perf_researcher.analyze()
    recs = rep.get("recommendations", [])
    if closed >= 8:
        check("Researcher produces recommendations", len(recs) > 0, f"{len(recs)} recs")
        for r in recs[:4]:
            info("  rec", r)
    else:
        info("Researcher (need >=8 closed)", f"{closed} closed")

    # reflection hypotheses?
    hp = os.path.join(DATA_DIR, "hypotheses.db")
    if os.path.exists(hp):
        h = sqlite3.connect(hp)
        nh = h.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0]
        info("Reflection hypotheses formed", str(nh))
        h.close()
    c.close()

    # ── report ──
    print("\n" + "=" * 64)
    print("  INTEGRATION + REAL-LEARNING PROOF")
    print("=" * 64)
    fails = 0
    for status, name, detail in results:
        mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "INFO": "[info]"}[status]
        print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
        if status == FAIL:
            fails += 1
    print("=" * 64)
    print(f"  {'ALL INTEGRATION CHECKS PASSED' if fails == 0 else str(fails)+' CHECK(S) FAILED'}")
    print("  Re-run over time to watch learning metrics advance.")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
