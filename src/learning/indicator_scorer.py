"""
IndicatorScorer — per-indicator entry-quality scoring.

For every closed trade we captured the full indicator snapshot at entry. This
module aggregates those snapshots by OUTCOME to answer: "which indicator states
tend to precede winning vs losing entries, for this symbol / regime / session?"

The output is an evidence base the ReflectionAgent reasons over and the
StrategySynthesizer uses to swap/combine indicators. It is descriptive
statistics only — no LLM here — so it is cheap and deterministic.

Scores are stored back into the knowledge base so they can be recalled.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Optional

from src.utils.logger import get_logger
from src.strategies.sessions import session_of

logger = get_logger("indicator_scorer")

# Indicator fields we score (must exist in compute_full_indicators output).
SCORED_FIELDS = [
    "rsi", "adx", "stoch_k", "stoch_d", "williams_r", "cci",
    "macd_histogram", "volatility_ratio", "body_ratio", "upper_wick",
    "lower_wick", "price_change_5", "price_change_10", "volume",
]

# Backward-compat mapping for old session names that may exist in stored data.
_OLD_SESSION_MAP = {
    "asia": "Asian",
    "london": "London",
    "london_ny_overlap": "NewYork",
    "new_york": "NewYork",
    "late_ny": "Off",
}


def _session_of(hour_utc: int) -> str:
    """Coarse trading session from a UTC hour (for entry-timing analysis)."""
    return _OLD_SESSION_MAP.get(session_of(hour_utc), session_of(hour_utc))


class IndicatorScorer:
    def __init__(self, experience_db):
        self.experience_db = experience_db

    def _load_closed(self, symbol: Optional[str] = None) -> list[dict]:
        import sqlite3
        conn = sqlite3.connect(self.experience_db.db_path)
        conn.row_factory = sqlite3.Row
        q = ("SELECT id, symbol, action, outcome, profit_loss, timestamp, "
             "market_regime, indicators_snapshot, strategy_combination "
             "FROM trades WHERE outcome IN ('win','loss','breakeven')")
        params: list = []
        if symbol:
            q += " AND symbol = ?"
            params.append(symbol)
        # Restrict learning reads to the live OsMA_Confluence era (cutover +
        # recency + OsMA-only + exclude SIMULATED_OHLC). Without this the scorer
        # reasons over the poisoned pre-cutover ensemble era and retired strategies.
        try:
            lw, lp = self.experience_db.learning_window_clause()
            q += lw
            params.extend(lp)
        except Exception:
            pass
        rows = [dict(r) for r in conn.execute(q, tuple(params)).fetchall()]
        conn.close()
        return rows

    def score(self, symbol: Optional[str] = None, min_sample: int = 6) -> dict:
        """
        Return an evidence dict:
        {
          "sample": n, "wins": w, "losses": l,
          "indicators": { field: {"win_mean":.., "loss_mean":.., "separation":..} },
          "by_session": { session: {"trades":n,"win_rate":..} },
          "by_regime":  { regime:  {"trades":n,"win_rate":..} },
          "worst_sessions": [...], "worst_regimes": [...],
          "indicator_ranking": [ (field, separation), ... ]  # most discriminating first
        }
        `separation` = |mean(win) - mean(loss)| normalized; high = the indicator
        distinguishes winners from losers (useful); ~0 = not informative.
        """
        rows = self._load_closed(symbol)
        if len(rows) < min_sample:
            return {"sample": len(rows), "insufficient": True,
                    "needed": min_sample}

        wins = [r for r in rows if r["outcome"] == "win"]
        losses = [r for r in rows if r["outcome"] == "loss"]

        # collect indicator values by outcome
        win_vals = defaultdict(list)
        loss_vals = defaultdict(list)
        by_session = defaultdict(lambda: {"trades": 0, "wins": 0})
        by_regime = defaultdict(lambda: {"trades": 0, "wins": 0})

        for r in rows:
            try:
                snap = json.loads(r.get("indicators_snapshot") or "{}")
            except Exception:
                snap = {}
            is_win = r["outcome"] == "win"
            for f in SCORED_FIELDS:
                v = snap.get(f)
                if isinstance(v, (int, float)):
                    (win_vals if is_win else loss_vals)[f].append(float(v))

            # session from timestamp
            ts = r.get("timestamp") or ""
            try:
                hour = int(ts[11:13])
                sess = _session_of(hour)
                by_session[sess]["trades"] += 1
                by_session[sess]["wins"] += 1 if is_win else 0
            except Exception:
                pass

            reg = r.get("market_regime") or "unknown"
            by_regime[reg]["trades"] += 1
            by_regime[reg]["wins"] += 1 if is_win else 0

        indicators = {}
        ranking = []
        for f in SCORED_FIELDS:
            wv, lv = win_vals.get(f, []), loss_vals.get(f, [])
            if len(wv) >= 3 and len(lv) >= 3:
                wm, lm = statistics.mean(wv), statistics.mean(lv)
                spread = statistics.pstdev(wv + lv) or 1.0
                separation = abs(wm - lm) / spread
                indicators[f] = {
                    "win_mean": round(wm, 4), "loss_mean": round(lm, 4),
                    "separation": round(separation, 3),
                }
                ranking.append((f, round(separation, 3)))
        ranking.sort(key=lambda x: x[1], reverse=True)

        def _rate(d):
            return {k: {"trades": v["trades"],
                       "win_rate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0.0}
                    for k, v in d.items()}

        sess_rates = _rate(by_session)
        reg_rates = _rate(by_regime)
        worst_sessions = sorted(
            [(k, v["win_rate"]) for k, v in sess_rates.items() if v["trades"] >= 3],
            key=lambda x: x[1])[:3]
        worst_regimes = sorted(
            [(k, v["win_rate"]) for k, v in reg_rates.items() if v["trades"] >= 3],
            key=lambda x: x[1])[:3]

        result = {
            "symbol": symbol or "ALL",
            "sample": len(rows), "wins": len(wins), "losses": len(losses),
            "indicators": indicators,
            "indicator_ranking": ranking,
            "by_session": sess_rates,
            "by_regime": reg_rates,
            "worst_sessions": worst_sessions,
            "worst_regimes": worst_regimes,
        }
        logger.info(f"Indicator scoring [{symbol or 'ALL'}]: {len(rows)} closed, "
                    f"top discriminators: {ranking[:3]}")
        return result
