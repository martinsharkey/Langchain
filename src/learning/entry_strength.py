"""
Entry-strength learner (#entry-signal).

The bot must LEARN which indicator STRENGTHS give reliable entries — e.g. does a
Bulls value of 2.4 vs 3.1, or an OsMA of 0.5 vs 0.9, better predict a winner — per
symbol, and scale-free (gold's values are ~1, BTC's ~an order of magnitude higher).

It samples closed trades' ENTRY snapshots (entry OsMA / Bulls / Bears, all
normalized by the trade's ATR so symbols are comparable), splits winners vs losers,
and finds the strength level that maximises entry reliability. It outputs, per
symbol, ATR-normalized minimums the confluence gate uses:

  osma_strength_min   (|OsMA| / ATR)
  power_strength_min  (dominant power / ATR: Bulls for longs, Bears for shorts)

Seeded from the GoldShark real-tick trades (data_source=SIMULATED_REAL_TICKS) and
refined continuously from live wins. Read-only over the DB; deterministic.
"""
from __future__ import annotations
import json
import sqlite3
import statistics
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("entry_strength")


class EntryStrengthLearner:
    def __init__(self, experience_db, min_sample: int = 15):
        self.db = experience_db
        self.min_sample = min_sample

    def _rows(self, symbol_prefix: str):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT action, profit_loss, mfe_points, atr_value, indicators_snapshot "
            "FROM trades WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
            "AND indicators_snapshot IS NOT NULL "
            "ORDER BY id DESC LIMIT 800", (symbol_prefix + "%",)).fetchall()]
        conn.close()
        return rows

    def learn_symbol(self, symbol_prefix: str) -> Optional[dict]:
        """Return {osma_strength_min, power_strength_min, n, ...} for a symbol, or
        None if there isn't enough data yet. Values are ATR-normalized (scale-free)."""
        rows = self._rows(symbol_prefix)
        samples = []   # (is_win, |osma|/atr, dominant_power/atr)
        for r in rows:
            try:
                snap = json.loads(r["indicators_snapshot"]) if r["indicators_snapshot"] else {}
            except Exception:
                continue
            atr = float(r["atr_value"] or snap.get("atr") or 0)
            if atr <= 0:
                continue
            osma = abs(float(snap.get("osma") or 0)) / atr
            action = r["action"]
            # dominant-side power: Bulls for a long, Bears(magnitude) for a short
            if action == "buy":
                power = float(snap.get("bulls_power") or 0) / atr
            else:
                power = -float(snap.get("bears_power") or 0) / atr   # bears are negative on shorts
            # "reliable win" = the trade closed positive. (MFE in points is not
            # comparable to ATR in price, so use realised P&L as the honest label.)
            is_win = (r["profit_loss"] or 0) > 0
            samples.append((is_win, osma, power))

        if len(samples) < self.min_sample:
            return None
        wins = [s for s in samples if s[0]]
        if len(wins) < max(5, self.min_sample // 3):
            # not enough winners to learn a reliable level yet — stay permissive
            return {"osma_strength_min": 0.0, "power_strength_min": 0.0,
                    "n": len(samples), "wins": len(wins), "note": "cold: too few wins"}

        # Learn the level that best separates winners: use the winners' own
        # distribution. The 25th percentile of WINNERS' strength is a robust floor —
        # most winners clear it, while it still rejects the weakest (losing) entries.
        def p25(vals):
            v = sorted(vals)
            return v[max(0, int(len(v) * 0.25))] if v else 0.0

        osma_floor = p25([w[1] for w in wins])
        power_floor = p25([w[2] for w in wins if w[2] > 0])

        # validate the floor actually improves win-rate vs no floor (honesty guard)
        base_wr = len(wins) / len(samples)
        kept = [s for s in samples if s[1] >= osma_floor and s[2] >= power_floor]
        kept_wr = (sum(1 for s in kept if s[0]) / len(kept)) if kept else 0.0
        improves = kept_wr > base_wr and len(kept) >= max(5, self.min_sample // 3)

        return {
            "osma_strength_min": round(osma_floor, 4) if improves else 0.0,
            "power_strength_min": round(power_floor, 4) if improves else 0.0,
            "n": len(samples), "wins": len(wins),
            "base_win_rate": round(base_wr, 3), "gated_win_rate": round(kept_wr, 3),
            "kept": len(kept), "improves": improves,
        }

    def learn_all(self, symbol_prefixes) -> dict:
        out = {}
        for s in symbol_prefixes:
            try:
                r = self.learn_symbol(s)
                if r:
                    out[s] = r
                    logger.info(f"[ENTRY-STRENGTH] {s}: osma_min={r['osma_strength_min']} "
                                f"power_min={r['power_strength_min']} (n={r['n']}, "
                                f"WR {r.get('base_win_rate')}->{r.get('gated_win_rate')}, "
                                f"improves={r.get('improves')})")
            except Exception as e:
                logger.debug(f"entry-strength learn skip {s}: {e}")
        return out
