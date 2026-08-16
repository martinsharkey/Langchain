"""
Reversal-signature analyzer (exit research).

Question this answers: our 7-indicator confluence is good for ENTRY — is it also
good for EXIT? For each historical closed trade we reconstruct the real M1 bars
from entry to exit, recompute the indicator series, and compare the indicator
state at three moments:

  ENTRY  -> the bar we entered on
  PEAK   -> the bar of maximum favourable excursion (MFE)
  ROLLOVER -> the first bar AFTER the peak where profit has dropped >= `rollover_frac`
              of the peak (the move rolling over)

If the indicators show a repeatable signature at PEAK/ROLLOVER (e.g. OsMA turning
back toward zero, MACD histogram shrinking, Bulls/Bears flipping, RSI unwinding
from an extreme), that signature can drive a signal-based exit/hold instead of a
blind giveback %. This module ONLY analyses — it does not change live behaviour.

Offline-safe: bar access is injected (or uses MT5 if available), so it is unit
testable without the terminal.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional, Callable

from src.utils.logger import get_logger

logger = get_logger("reversal_signature")

# the confluence indicators we compare across ENTRY/PEAK/ROLLOVER
_FIELDS = ("macd_line", "macd_histogram", "osma", "bulls_power", "bears_power", "rsi", "atr")


@dataclass
class StageSnapshot:
    stage: str                      # entry | peak | rollover
    bar_index: int
    profit_points: float
    values: dict = field(default_factory=dict)


@dataclass
class TradeReversal:
    trade_id: int
    action: str                     # buy | sell
    mfe_points: float
    realised_points: float
    entry: StageSnapshot
    peak: StageSnapshot
    rollover: Optional[StageSnapshot]


class ReversalSignatureAnalyzer:
    def __init__(self, experience_db, bars_fn: Optional[Callable] = None,
                 point_fn: Optional[Callable] = None):
        """
        experience_db: ExperienceDatabase (for closed trades).
        bars_fn(symbol, start_dt, end_dt) -> list[{time,open,high,low,close}] (M1).
          Defaults to MT5 copy_rates_range. Injected in tests.
        point_fn(symbol) -> float point size. Defaults to a metals/FX guess.
        """
        self.db = experience_db
        self._bars_fn = bars_fn or self._mt5_bars
        self._point_fn = point_fn or (lambda s: 0.01 if "XAU" in s.upper() else 0.0001)
        self._srv_offset = None

    # ── bar access (MT5) ──
    def _server_offset(self) -> float:
        if self._srv_offset is not None:
            return self._srv_offset
        try:
            from src.mt5.broker_time import broker_offset_seconds
            self._srv_offset = broker_offset_seconds()
        except Exception:
            self._srv_offset = 0.0
        return self._srv_offset

    def _mt5_bars(self, symbol, start_dt, end_dt):
        try:
            import MetaTrader5 as mt5
            rr = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start_dt, end_dt)
            if rr is None:
                return []
            return [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
                     "low": float(r["low"]), "close": float(r["close"])} for r in rr]
        except Exception as e:
            logger.debug(f"mt5 bars failed {symbol}: {e}")
            return []

    # ── the core: profit points of a bar for a direction ──
    @staticmethod
    def _profit_points(action, entry_price, price, point):
        d = (price - entry_price) if action == "buy" else (entry_price - price)
        return d / point if point else 0.0

    def analyze_trade(self, trade: dict, rollover_frac: float = 0.33) -> Optional[TradeReversal]:
        """Reconstruct one trade and return its ENTRY/PEAK/ROLLOVER indicator states."""
        import datetime as _dt
        from src.strategies.indicators import compute_indicator_series

        symbol = trade["symbol"]
        action = trade["action"]
        entry_price = float(trade["entry_price"] or 0)
        if action not in ("buy", "sell") or entry_price <= 0:
            return None
        point = self._point_fn(symbol)

        # window: entry .. exit (+ small pad), shifted to server time for MT5
        try:
            t0 = _dt.datetime.fromisoformat(trade["timestamp"])
        except Exception:
            return None
        # exit time unknown precisely; use created_at or a max hold pad
        end = t0 + _dt.timedelta(hours=6)
        off = self._server_offset()
        bars = self._bars_fn(symbol, t0 + _dt.timedelta(seconds=off) - _dt.timedelta(minutes=5),
                             end + _dt.timedelta(seconds=off))
        # need warmup for indicators; if the reconstruction is too short, skip
        if not bars or len(bars) < 60:
            return None

        series = compute_indicator_series(bars, None)

        # locate entry bar = first bar at/after entry price time (closest close to entry)
        entry_idx = min(range(len(bars)), key=lambda i: abs(bars[i]["close"] - entry_price))
        # walk forward tracking favourable excursion
        peak_idx = entry_idx
        peak_pts = 0.0
        for i in range(entry_idx, len(bars)):
            fav_price = bars[i]["high"] if action == "buy" else bars[i]["low"]
            pts = self._profit_points(action, entry_price, fav_price, point)
            if pts > peak_pts:
                peak_pts = pts
                peak_idx = i
        if peak_pts <= 0:
            return None

        # rollover: first bar after peak where profit dropped >= rollover_frac of peak
        rollover_idx = None
        for i in range(peak_idx + 1, len(bars)):
            pts = self._profit_points(action, entry_price, bars[i]["close"], point)
            if pts <= peak_pts * (1.0 - rollover_frac):
                rollover_idx = i
                break

        def snap(stage, idx):
            ind = series[idx] if 0 <= idx < len(series) and series[idx] else {}
            pts = self._profit_points(action, entry_price,
                                      bars[idx]["close"], point)
            return StageSnapshot(stage=stage, bar_index=idx, profit_points=round(pts, 1),
                                 values={k: ind.get(k) for k in _FIELDS})

        return TradeReversal(
            trade_id=trade["id"], action=action,
            mfe_points=round(peak_pts, 1),
            realised_points=round(self._profit_points(action, entry_price,
                                  bars[-1]["close"], point), 1),
            entry=snap("entry", entry_idx),
            peak=snap("peak", peak_idx),
            rollover=snap("rollover", rollover_idx) if rollover_idx is not None else None,
        )

    def analyze_symbol(self, symbol_prefix="XAUUSD", limit=60, min_mfe_points=100.0):
        """Analyze recent closed trades with a meaningful peak; aggregate the signature."""
        import sqlite3
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT id, symbol, action, entry_price, timestamp, mfe_points, profit_loss "
            "FROM trades WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
            "AND (data_source IS NULL OR data_source<>'SIMULATED_OHLC') "
            "AND mfe_points >= ? ORDER BY id DESC LIMIT ?",
            (symbol_prefix + "%", min_mfe_points, limit)).fetchall()]
        conn.close()

        reversals = []
        for r in rows:
            tr = self.analyze_trade(r)
            if tr and tr.rollover is not None:
                reversals.append(tr)

        return {"analyzed": len(rows), "with_rollover": len(reversals),
                "signature": self._aggregate(reversals), "reversals": reversals}

    def signature_from_captured(self, symbol_prefix="XAUUSD", limit=200,
                                min_mfe_points: Optional[float] = None) -> dict:
        """Aggregate the reversal signature from LIVE-CAPTURED snapshots
        (peak_indicators / exit_indicators columns) — no bar reconstruction needed.
        This is the loop-facing method: it works on data the engine already stored.

        SCALE-AWARE / PER-SYMBOL: gold's OsMA/MACD live on a totally different numeric
        scale than BTCUSD's, so we NEVER compare raw indicator units across symbols.
        Everything here is measured within THIS symbol and expressed scale-free:
          * momentum magnitudes (osma, macd_line, macd_histogram, bulls/bears) are
            normalized by the trade's own ATR at peak -> `_atr` variants;
          * the reversal 'tell' is a RATIO (exit magnitude / peak magnitude), so it is
            unit-free and directly comparable across symbols and learnable per symbol;
          * `min_mfe_points` auto-scales to the symbol's median MFE when not given.

        Returns, per indicator: how reliably it shrinks toward neutral at exit
        (`shrank_toward_neutral_pct`), the symbol's OWN median retained fraction
        (`median_retained_frac` = |exit|/|peak|), and the ATR-normalized peak
        magnitude the symbol typically reaches (`median_peak_over_atr`). Empty until
        enough live trades close.
        """
        import sqlite3, json
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT id, action, mfe_points, exit_points, atr_value, indicators_snapshot, "
            "peak_indicators, exit_indicators FROM trades "
            "WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
            "AND (data_source IS NULL OR data_source<>'SIMULATED_OHLC') "
            "AND peak_indicators IS NOT NULL "
            "ORDER BY id DESC LIMIT ?",
            (symbol_prefix + "%", limit)).fetchall()]
        conn.close()

        # auto-scale the MFE filter to THIS symbol (median of what it actually reaches)
        mfes = [r["mfe_points"] for r in rows if (r["mfe_points"] or 0) > 0]
        if min_mfe_points is None:
            min_mfe_points = (statistics.median(mfes) * 0.5) if mfes else 0.0

        # momentum fields we normalize by ATR; RSI is already 0-100 (scale-free-ish)
        _MOM = ("osma", "macd_line", "macd_histogram", "bulls_power", "bears_power")

        retained_frac = {f: [] for f in _FIELDS}     # |exit|/|peak| — the scale-free tell
        peak_over_atr = {f: [] for f in _MOM}         # peak magnitude / ATR — per-symbol scale
        rollover_tell = {f: 0 for f in _FIELDS}
        n = 0
        for r in rows:
            if (r["mfe_points"] or 0) < min_mfe_points:
                continue
            try:
                peak = json.loads(r["peak_indicators"]) if r["peak_indicators"] else {}
                ex = json.loads(r["exit_indicators"]) if r["exit_indicators"] else {}
            except Exception:
                continue
            if not peak:
                continue
            n += 1
            atr = float(r["atr_value"] or 0) or (peak.get("atr") or 0) or 0
            for f in _FIELDS:
                pv, xv = peak.get(f), ex.get(f)
                if pv is not None and xv is not None:
                    pk, lv = abs(float(pv)), abs(float(xv))
                    if pk > 1e-9:
                        retained_frac[f].append(lv / pk)     # scale-free
                        if lv < pk:
                            rollover_tell[f] += 1
                if f in _MOM and pv is not None and atr > 0:
                    peak_over_atr[f].append(abs(float(pv)) / atr)

        def med(xs):
            return round(statistics.median(xs), 4) if xs else None

        sig = {}
        for f in _FIELDS:
            k = len(retained_frac[f])
            sig[f] = {
                # the symbol's OWN average reversal depth (scale-free)
                "median_retained_frac": med(retained_frac[f]),
                "shrank_toward_neutral_pct": round(rollover_tell[f] / k * 100, 0) if k else None,
                # per-symbol scale of the momentum peak (how big is 'big' for this symbol)
                "median_peak_over_atr": med(peak_over_atr.get(f, [])) if f in _MOM else None,
                "n": k,
            }
        caps = [ (r["exit_points"] / r["mfe_points"])
                 for r in rows if (r["mfe_points"] or 0) > 5 and r["exit_points"] is not None ]
        sig["_meta"] = {
            "symbol": symbol_prefix,
            "n_trades": n,
            "min_mfe_points_used": round(min_mfe_points, 1),
            "median_mfe_points": round(statistics.median(mfes), 1) if mfes else None,
            "median_capture_ratio": round(statistics.median(caps), 3) if caps else None,
            "left_on_table_pct": round((1 - statistics.median(caps)) * 100, 0) if caps else None,
        }
        return sig

    def _aggregate(self, reversals) -> dict:
        """Median indicator DELTAS entry->peak and peak->rollover, so a signature
        (e.g. 'OsMA falls X toward zero and MACD histogram halves as it rolls over')
        becomes visible and testable."""
        if not reversals:
            return {}
        out = {}
        for f in _FIELDS:
            ep = [ (tr.peak.values[f] - tr.entry.values[f])
                   for tr in reversals
                   if tr.entry.values.get(f) is not None and tr.peak.values.get(f) is not None ]
            pr = [ (tr.rollover.values[f] - tr.peak.values[f])
                   for tr in reversals
                   if tr.peak.values.get(f) is not None and tr.rollover.values.get(f) is not None ]
            out[f] = {
                "entry_to_peak_median": round(statistics.median(ep), 4) if ep else None,
                "peak_to_rollover_median": round(statistics.median(pr), 4) if pr else None,
                "n": len(pr),
            }
        # capture stats
        caps = [ (1.0 - (tr.mfe_points - tr.realised_points) / tr.mfe_points)
                 for tr in reversals if tr.mfe_points > 0 ]
        out["_capture"] = {
            "median_capture_ratio": round(statistics.median(caps), 3) if caps else None,
            "median_mfe": round(statistics.median([tr.mfe_points for tr in reversals]), 1),
        }
        return out
