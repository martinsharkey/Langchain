"""
Entry-quality learner (#entry-signal).

EVIDENCE (full GoldShark telemetry, XAUUSD n=601 / BTCUSD n=154): OsMA/Bulls/Bears
STRENGTH magnitude does NOT separate winners from losers — raising those thresholds
LOWERS win-rate. The ONE entry feature that DOES separate winners is PRICE STRETCH:
winners enter much CLOSER to the EMA; losers enter over-extended (85% separation on
BTC). So this learner derives a per-symbol `max_stretch_atr` (|close-EMA|/ATR ceiling)
and applies it ONLY when it robustly improves win-rate out-of-sample. It does NOT gate
on strength magnitude (that was overfitting noise).
"""
from __future__ import annotations
import json
import sqlite3
import statistics
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("entry_strength")


class EntryStrengthLearner:
    def __init__(self, experience_db, min_sample: int = 30):
        self.db = experience_db
        self.min_sample = min_sample

    def _rows(self, symbol_prefix: str):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT action, profit_loss, mfe_points, atr_value, indicators_snapshot "
            "FROM trades WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
            "AND indicators_snapshot IS NOT NULL "
            "ORDER BY id DESC LIMIT 1200", (symbol_prefix + "%",)).fetchall()]
        conn.close()
        return rows

    def learn_symbol(self, symbol_prefix: str) -> Optional[dict]:
        """Return {max_stretch_atr, n, ...} for a symbol, or None if insufficient data.
        max_stretch_atr = the |close-EMA|/ATR ceiling that best separates winners,
        applied ONLY when it improves win-rate out-of-sample."""
        rows = self._rows(symbol_prefix)
        samples = []   # (is_win, stretch_atr)
        for r in rows:
            try:
                snap = json.loads(r["indicators_snapshot"]) if r["indicators_snapshot"] else {}
            except Exception:
                continue
            atr = float(r["atr_value"] or snap.get("atr") or 0)
            close = float(snap.get("close") or 0)
            ema = float(snap.get("ema_fast") or snap.get("ema") or 0)
            if atr <= 0 or close <= 0 or ema <= 0:
                continue
            stretch = abs(close - ema) / atr
            is_win = (r["profit_loss"] or 0) > 0
            samples.append((is_win, stretch))

        if len(samples) < self.min_sample:
            return None
        wins = [s for s in samples if s[0]]
        if len(wins) < max(8, self.min_sample // 4):
            return {"max_stretch_atr": 0.0, "n": len(samples), "wins": len(wins),
                    "note": "cold: too few wins"}

        base_wr = len(wins) / len(samples)
        # candidate ceilings = winners' stretch percentiles (75th/90th). Pick the one
        # that MOST improves win-rate on the kept set, and only keep it if it beats
        # base by a real margin with enough sample (honest out-of-sample-style guard).
        win_stretch = sorted(w[1] for w in wins)
        best = {"max_stretch_atr": 0.0, "gated_win_rate": base_wr, "kept": len(samples)}
        for pct in (0.75, 0.9, 0.6):
            ceil = win_stretch[min(len(win_stretch) - 1, int(len(win_stretch) * pct))]
            kept = [s for s in samples if s[1] <= ceil]
            if len(kept) < max(15, self.min_sample // 2):
                continue
            wr = sum(1 for s in kept if s[0]) / len(kept)
            if wr > best["gated_win_rate"]:
                best = {"max_stretch_atr": round(ceil, 3), "gated_win_rate": round(wr, 3),
                        "kept": len(kept)}
        improves = best["max_stretch_atr"] > 0 and best["gated_win_rate"] > base_wr + 0.03
        return {
            "max_stretch_atr": best["max_stretch_atr"] if improves else 0.0,
            "n": len(samples), "wins": len(wins),
            "base_win_rate": round(base_wr, 3), "gated_win_rate": best["gated_win_rate"],
            "kept": best["kept"], "improves": improves,
        }

    def learn_all(self, symbol_prefixes) -> dict:
        out = {}
        for s in symbol_prefixes:
            try:
                r = self.learn_symbol(s)
                if r:
                    out[s] = r
                    logger.info(f"[ENTRY-QUALITY] {s}: max_stretch_atr={r['max_stretch_atr']} "
                                f"(n={r['n']}, WR {r.get('base_win_rate')}->{r.get('gated_win_rate')}, "
                                f"improves={r.get('improves')})")
            except Exception as e:
                logger.debug(f"entry-quality learn skip {s}: {e}")
        return out
