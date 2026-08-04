"""
Entry-quality learner (#entry-signal) — mines the per-symbol ENTRY-QUALITY recipe
that maximises ENTRY-DIRECTION success (the ~95% edge the GoldShark / EMA_OSMA_ATR
EAs achieved: the trade went into meaningful profit, i.e. direction was right).

EVIDENCE (full EA telemetry): OsMA/Bulls/Bears STRENGTH magnitude does NOT separate
winners. What DOES lift entry-direction success is a COMBINATION of freshness +
not-over-extended + runway:
  accel_min      OsMA acceleration |osma-osma_prev|/ATR (fresh momentum)
  max_stretch_atr  |close-EMA|/ATR ceiling (not over-extended)
  dom_min        dominant power (Bulls long / Bears short)/ATR
  runway_min     |OsMA| / recent-avg|OsMA| (FinalMultiplier proxy)

The learner greedily selects the gate set that raises entry-success on THIS symbol's
own closed trades, applied ONLY when it beats the base rate on a meaningful sample.
Scale-free (all ATR-normalized) so gold and BTC self-calibrate.
"""
from __future__ import annotations
import json
import sqlite3
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("entry_quality")

# candidate gates: (cfg_key, field, op, value)
_CANDIDATES = [
    ("accel_min", "accel", ">=", 0.02), ("accel_min", "accel", ">=", 0.05), ("accel_min", "accel", ">=", 0.10),
    ("dom_min", "dom", ">=", 0.5), ("dom_min", "dom", ">=", 1.0), ("dom_min", "dom", ">=", 1.5),
    ("max_stretch_atr", "stretch", "<=", 2.0), ("max_stretch_atr", "stretch", "<=", 1.0), ("max_stretch_atr", "stretch", "<=", 0.7),
    ("runway_min", "runway", ">=", 2.0), ("runway_min", "runway", ">=", 3.0),
]


class EntryStrengthLearner:  # name kept for wiring compatibility
    def __init__(self, experience_db, min_sample: int = 40, green_atr: float = 0.3,
                 min_keep_frac: float = 0.15, max_gates: int = 3):
        self.db = experience_db
        self.min_sample = min_sample
        self.green_atr = green_atr
        self.min_keep_frac = min_keep_frac
        self.max_gates = max_gates

    def _samples(self, symbol_prefix: str):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT action, mfe_points, atr_value, indicators_snapshot FROM trades "
            "WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
            "AND indicators_snapshot IS NOT NULL ORDER BY id DESC LIMIT 1500",
            (symbol_prefix + "%",)).fetchall()]
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
            close = float(s.get("close") or 0); ema = float(s.get("ema_fast") or s.get("ema") or 0)
            osma = float(s.get("osma") or 0); osma_prev = float(s.get("osma_prev") or 0)
            recent = s.get("osma_recent") or []
            mags = [abs(float(x)) for x in recent if x is not None]
            runway = (abs(osma) / (sum(mags) / len(mags))) if mags else float("nan")
            dom = (float(s.get("bulls_power") or 0) if r["action"] == "buy"
                   else -float(s.get("bears_power") or 0)) / atr
            out.append({
                "green": 1 if mfe >= self.green_atr * atr else 0,
                "accel": abs(osma - osma_prev) / atr,
                "stretch": abs(close - ema) / atr if (close > 0 and ema > 0) else float("nan"),
                "dom": dom, "runway": runway,
            })
        return out

    @staticmethod
    def _passes(rec, gate):
        _, field, op, val = gate
        x = rec.get(field)
        if x is None or x != x:   # nan/missing -> permissive
            return True
        return x >= val if op == ">=" else x <= val

    def _rate(self, samples, gates):
        kept = [s for s in samples if all(self._passes(s, g) for g in gates)]
        if not kept:
            return 0.0, 0
        return sum(s["green"] for s in kept) / len(kept), len(kept)

    def learn_symbol(self, symbol_prefix: str) -> Optional[dict]:
        S = self._samples(symbol_prefix)
        if len(S) < self.min_sample:
            return None
        base, n = self._rate(S, [])
        min_keep = max(20, int(n * self.min_keep_frac))
        chosen, cur = [], base
        while len(chosen) < self.max_gates:
            best = None
            for g in _CANDIDATES:
                # don't stack two gates on the same key
                if any(c[0] == g[0] for c in chosen):
                    continue
                sr, kept = self._rate(S, chosen + [g])
                if kept >= min_keep and sr > cur + 0.005 and (best is None or sr > best[1]):
                    best = (g, sr, kept)
            if not best:
                break
            chosen.append(best[0]); cur = best[1]
        kept = self._rate(S, chosen)[1]
        improves = bool(chosen) and cur > base + 0.02
        recipe = {}
        if improves:
            for key, _f, _op, val in chosen:
                recipe[key] = val
        return {"recipe": recipe, "n": n, "base_success": round(base, 3),
                "gated_success": round(cur, 3), "kept": kept, "improves": improves,
                "gates": [f"{g[1]}{g[2]}{g[3]}" for g in chosen]}

    def learn_all(self, symbol_prefixes) -> dict:
        out = {}
        for s in symbol_prefixes:
            try:
                r = self.learn_symbol(s)
                if r:
                    out[s] = r
                    logger.info(f"[ENTRY-QUALITY] {s}: {r['gates'] or '(base best)'} -> "
                                f"entry-success {r['base_success']*100:.0f}%->{r['gated_success']*100:.0f}% "
                                f"(kept {r['kept']}/{r['n']}, improves={r['improves']})")
            except Exception as e:
                logger.debug(f"entry-quality learn skip {s}: {e}")
        return out
