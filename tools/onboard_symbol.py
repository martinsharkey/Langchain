"""
Symbol onboarding — the AUTOMATED process to add a new tradable symbol.

Owner directive (2026-08-13): adding a symbol must be a repeatable, automated
pipeline, NOT hand-tuning each time. Every new symbol goes through the SAME steps
that gold and BTCUSD went through:

  1. SEED baseline floors — from the symbol's own winning-trade entry values if we
     have history, else a directional-safe default (sign-only). Directional
     alignment (long: osma/bulls/bears > 0; short: all < 0) is ALWAYS enforced.
  2. VALIDATE + AUTO-ESCALATE over a multi-week window (floor_validator): raise
     floors (longs up / shorts down) until win rate >= target (default 70%). Higher
     indicator strength = higher entry quality (the owner principle).
  3. PROMOTE — if a >= target level is found, persist the discovered floors as the
     symbol's baseline (alignment_floors.propose_rebaseline) + golden baseline, and
     REMOVE it from DISABLED_SYMBOLS so it trades. If no level reaches target, the
     symbol stays DISABLED and a report explains why.
  4. EXIT geometry — wide SL + BE + trail (no TP), scaled to the symbol's point
     magnitude (see floor_validator._EXIT). Documented in SYMBOL_ONBOARDING.md.

Run: python tools/onboard_symbol.py BTCUSD           (validate only, report)
     python tools/onboard_symbol.py BTCUSD --promote  (validate + enable if passes)
"""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("USE_SAFE_EMBEDDER", "1")
os.environ.setdefault("FORCE_LOCAL_VECTOR_STORE", "1")

from src.mt5.connector import get_connector
from src.learning.floor_validator import discover_high_quality_floors
from src.strategies.alignment_floors import propose_rebaseline, baseline

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD-ECN"
PROMOTE = "--promote" in sys.argv
TARGET_WR = float(os.getenv("FLOOR_TARGET_WR", "70"))


def onboard(symbol: str, promote: bool = False, target_wr: float = TARGET_WR) -> dict:
    conn = get_connector(); conn.initialize()
    print(f"=== ONBOARDING {symbol} (target WR>={target_wr}%, promote={promote}) ===")
    print(f"seed baseline: {baseline(symbol)}")
    res = discover_high_quality_floors(symbol, target_wr=target_wr)
    if res.get("error"):
        print(f"  ABORT: {res['error']}")
        conn.shutdown(); return res
    print(f"  validated over {res.get('weeks')} weeks; levels tried: {len(res.get('levels', []))}")
    for lv in res.get("levels", []):
        print(f"    lvl{lv['level']} osmaL={lv['osma_min_long']} bullsL={lv['bulls_min_long']} "
              f"bearsL={lv['bears_min_long']} -> {lv['win_rate']}% WR PF{lv['pf']} {lv['trades_per_week']}/wk (n={lv['n']})")
    if not res.get("found"):
        print(f"  RESULT: no level reached {target_wr}% — symbol should stay DISABLED.")
        conn.shutdown(); return res
    b = res["best"]
    print(f"  RESULT: HIGH-QUALITY floors found -> {b['win_rate']}% WR, PF {b['pf']}, "
          f"{b['trades_per_week']}/wk. Exit: {res['exit']}")
    if promote:
        propose_rebaseline(symbol, "long", {"osma_min": b["osma_min_long"], "bulls_min": b["bulls_min_long"],
                                            "bears_min": b["bears_min_long"]}, source="onboarding")
        propose_rebaseline(symbol, "short", {"osma_max": b["osma_max_short"], "bears_max": b["bears_max_short"],
                                             "bulls_max": b["bulls_max_short"]}, source="onboarding")
        _enable_symbol(symbol)
        print(f"  PROMOTED: floors persisted + {symbol} removed from DISABLED_SYMBOLS. "
              f"Set exit geometry {res['exit']} in config for this symbol before live.")
    else:
        print("  (dry run — pass --promote to persist floors + enable trading)")
    conn.shutdown(); return res


def _enable_symbol(symbol: str):
    """Remove the symbol from DISABLED_SYMBOLS in .env (base symbol form)."""
    base = symbol.replace("-ECN", "").upper()
    env = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env):
        return
    lines = open(env, encoding="utf-8").read().splitlines()
    out = []
    for ln in lines:
        if ln.startswith("DISABLED_SYMBOLS="):
            vals = [v for v in ln.split("=", 1)[1].split(",") if v and v.upper() != base]
            out.append("DISABLED_SYMBOLS=" + ",".join(vals))
        else:
            out.append(ln)
    open(env, "w", encoding="utf-8").write("\n".join(out) + "\n")


if __name__ == "__main__":
    onboard(SYMBOL, PROMOTE)
