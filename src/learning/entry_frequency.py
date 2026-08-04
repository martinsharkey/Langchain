"""
Entry frequency-vs-quality analyzer.

Answers: for each monitored symbol, at each OsMA / dominant-power (Bulls/Bears) /
runway strength level — how many entries would fire PER DAY, what % would go into
profit (entry-direction success), and what peak (MFE) they'd reach. This finds the
strength that maximises entry success WITHOUT choking trading to zero.

Replays the REAL live entry indicator snapshots already stored on each trade
(indicators_snapshot + realised mfe_points), so it reflects exactly what the bot saw.
Uses only clean-MFE data (from when capture was fixed). Read-only.
"""
from __future__ import annotations
import json, sqlite3, statistics
from collections import defaultdict
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("entry_frequency")

# strength levels to sweep (ATR-normalized so symbols compare)
_OSMA_LVLS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
_DOM_LVLS = [0.0, 0.5, 1.0, 1.5, 2.0]
_RUNWAY_LVLS = [0.0, 2.0, 3.0, 4.0]


class EntryFrequencyAnalyzer:
    def __init__(self, experience_db, green_atr: float = 0.3, min_clean_date: str = "2026-08-02"):
        self.db = experience_db
        self.green_atr = green_atr
        self.min_clean_date = min_clean_date   # MFE capture trustworthy on/after this

    def _samples(self, symbol_prefix: str, days: int = 7):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        lw, lp = self.db.learning_window_clause()   # exclude pre-fix era + recency
        rows = [dict(r) for r in conn.execute(
            "SELECT date(timestamp) d, action, mfe_points, atr_value, indicators_snapshot "
            "FROM trades WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
            "AND (data_source IS NULL OR data_source='LIVE_MICRO') "
            "AND date(timestamp) >= ? AND indicators_snapshot IS NOT NULL "
            "AND datetime(timestamp) > datetime('now', ?)" + lw,
            tuple([symbol_prefix + "%", self.min_clean_date, f"-{days} days"] + lp)).fetchall()]
        conn.close()
        out = []
        for r in rows:
            try:
                s = json.loads(r["indicators_snapshot"]) if r["indicators_snapshot"] else {}
            except Exception:
                continue
            atr = float(r["atr_value"] or s.get("atr") or 0)
            mfe = r["mfe_points"]
            if atr <= 0 or mfe is None:
                continue
            osma = float(s.get("osma") or 0)
            recent = s.get("osma_recent") or []
            mags = [abs(float(x)) for x in recent if x is not None]
            runway = (abs(osma) / (sum(mags) / len(mags))) if mags else 0.0
            dom = (float(s.get("bulls_power") or 0) if r["action"] == "buy"
                   else -float(s.get("bears_power") or 0)) / atr
            out.append({"day": r["d"], "mfe": mfe, "atr": atr,
                        "osma": abs(osma) / atr, "dom": dom, "runway": runway,
                        "green": 1 if mfe >= self.green_atr * atr else 0})
        return out

    def analyze(self, symbol_prefix: str, days: int = 7, min_trades_per_day: float = 3.0):
        """Sweep strength levels; return the grid + the recommended non-choking level."""
        S = self._samples(symbol_prefix, days)
        if len(S) < 20:
            return {"symbol": symbol_prefix, "n": len(S), "note": "insufficient clean data"}
        n_days = max(1, len(set(s["day"] for s in S)))
        base_green = sum(s["green"] for s in S) / len(S)

        grid = []
        for o in _OSMA_LVLS:
            for dcut in _DOM_LVLS:
                for rw in _RUNWAY_LVLS:
                    kept = [s for s in S if s["osma"] >= o and s["dom"] >= dcut and s["runway"] >= rw]
                    if not kept:
                        continue
                    per_day = len(kept) / n_days
                    succ = sum(s["green"] for s in kept) / len(kept)
                    med_mfe = statistics.median([s["mfe"] for s in kept])
                    grid.append({"osma_min": o, "dom_min": dcut, "runway_min": rw,
                                 "per_day": round(per_day, 1), "n": len(kept),
                                 "success": round(succ, 3), "med_mfe": round(med_mfe, 0)})

        # RECOMMEND: highest entry-success while keeping >= min_trades_per_day (never
        # choke). Tie-break on more trades/day so we don't over-restrict.
        viable = [g for g in grid if g["per_day"] >= min_trades_per_day]
        rec = None
        if viable:
            best = max(g["success"] for g in viable)
            # among near-best success, take the one with most trades/day (least choke)
            near = [g for g in viable if g["success"] >= best - 0.02]
            rec = max(near, key=lambda g: g["per_day"])
        return {"symbol": symbol_prefix, "n": len(S), "days": n_days,
                "trades_per_day": round(len(S) / n_days, 1), "base_success": round(base_green, 3),
                "recommended": rec, "grid": grid}

    def report(self, symbol_prefixes, days: int = 7, min_trades_per_day: float = 3.0):
        out = {}
        for sym in symbol_prefixes:
            a = self.analyze(sym, days, min_trades_per_day)
            out[sym] = a
            if a.get("note"):
                print(f"\n{sym}: {a['note']} (n={a['n']})"); continue
            print(f"\n===== {sym}: {a['n']} clean entries over {a['days']}d "
                  f"= {a['trades_per_day']}/day, base success {a['base_success']*100:.0f}% =====")
            # show a few informative grid rows: no-gate, and increasing tightness
            shown = sorted(a["grid"], key=lambda g: (g["osma_min"], g["dom_min"], g["runway_min"]))
            for g in shown:
                if (g["osma_min"], g["dom_min"], g["runway_min"]) in [
                        (0.0, 0.0, 0.0), (0.1, 1.0, 0.0), (0.15, 1.0, 0.0),
                        (0.0, 1.0, 3.0), (0.2, 1.5, 0.0), (0.1, 1.0, 3.0)]:
                    print(f"   osma>={g['osma_min']} dom>={g['dom_min']} runway>={g['runway_min']}: "
                          f"{g['per_day']}/day  success={g['success']*100:.0f}%  medMFE={g['med_mfe']:.0f}pts (n={g['n']})")
            r = a["recommended"]
            if r:
                print(f"   >>> RECOMMENDED (no-choke, >= {min_trades_per_day}/day): "
                      f"osma>={r['osma_min']} dom>={r['dom_min']} runway>={r['runway_min']} "
                      f"-> {r['per_day']}/day, success={r['success']*100:.0f}%, medMFE={r['med_mfe']:.0f}pts")
            else:
                print(f"   >>> no level keeps >= {min_trades_per_day}/day — would choke; keep base")
        return out
