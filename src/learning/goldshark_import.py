"""
GoldShark telemetry -> real Langchain pattern store (`trades` in
experience_db) importer.

Unlike an isolated pattern_store.db, this writes historic GoldShark /
EMA_OSMA_ATR_TM CSV telemetry INTO the live `trades` table via
ExperienceDatabase.record_trade + update_trade_outcome, so the SAME model
(ONNX trainer, vector store, researcher) that learns from live trades also
sees the historic telemetry.

Provenance (Bug 4): every imported row is tagged `data_source`. Historic
GoldShark logs are real-tick simulations by default (SIMULATED_REAL_TICKS);
pass data_source="SIMULATED_OHLC" for interpolated-OHLC exports so training
EXCLUDES them.

Anti-look-ahead (Bug 1): only ENTRY-time indicators become model features
(the indicators_snapshot). Hindsight columns (peak_*/exit_* MACD/Bulls/Bears)
are NEVER written as entry features — they are only used to derive MFE/MAE
labels.
"""
from __future__ import annotations

import os
import csv
import json
from datetime import datetime
from typing import Optional

from src.learning.experience_db import ExperienceDatabase
from src.utils.logger import get_logger

logger = get_logger("goldshark_import")

# CSV header -> canonical field. Covers both the MT5 struct serializer and the
# historical lifecycle log headers.
_HEADER_MAP = {
    # entry / metadata
    "timeIn": "entry_time", "EntryTime": "entry_time",
    "priceIn": "entry_price", "EntryPrice": "entry_price",
    "LotSize": "lot_size", "Symbol": "symbol", "Direction": "direction",
    # entry indicators (the ONLY things allowed to be features)
    "eMACD": "macd_line", "EntryMACD": "macd_line",
    "eOsMA": "osma", "EntryOsMA": "osma",
    "eBulls": "bulls_power", "EntryBulls": "bulls_power",
    "eBears": "bears_power", "EntryBears": "bears_power",
    "emaSlope": "ema_slope", "EMASlope": "ema_slope",
    "priceStretch": "price_stretch", "PriceStretch": "price_stretch",
    "atr": "atr", "ATR_14": "atr", "rsi": "rsi", "RSI_14": "rsi",
    # dedup key
    "TradeID": "trade_ref", "TradeRef": "trade_ref",
    # PEAK-state indicators (reversal-signature: indicators AT the MFE peak)
    "PeakOsMA": "peak_osma", "PeakBulls": "peak_bulls", "PeakBears": "peak_bears",
    "PeakMACD": "peak_macd", "PeakTime": "peak_time", "PeakPrice": "peak_price",
    # EXIT-state indicators (indicators at the exit bar)
    "ExitOsMA": "exit_osma", "ExitBulls": "exit_bulls", "ExitBears": "exit_bears",
    "ExitMACD": "exit_macd",
    # resolution
    "timeOut": "exit_time", "ExitTime": "exit_time",
    "priceOut": "exit_price", "ExitPrice": "exit_price",
    "mfePts": "mfe_points", "MaxProfitPts": "mfe_points",
    "maePts": "mae_points", "MaxLossPts": "mae_points",
    "exitPts": "exit_points", "ExitPts": "exit_points", "BaseExitPts": "exit_points",
    "exitReason": "exit_reason", "ExitReason": "exit_reason",
    "profit": "profit_loss", "Profit": "profit_loss", "PnL": "profit_loss",
}

# entry-time indicator fields that are SAFE to use as model features
_ENTRY_FEATURE_FIELDS = ("macd_line", "osma", "bulls_power", "bears_power",
                         "ema_slope", "price_stretch", "atr", "rsi")

# hindsight fields that must NEVER be treated as entry features
_LOOKAHEAD_FIELDS = ("peak_macd", "peak_bulls", "peak_bears",
                     "exit_macd", "exit_bulls", "exit_bears")


def _to_float(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _norm_action(direction: str) -> Optional[str]:
    """GoldShark LONG/SHORT (or 0/1/-1, or LIVE_LONG/SIM_SHORT etc.) -> buy/sell."""
    d = str(direction).strip().upper()
    # strip execution-context prefixes used in the unified trade log (LIVE_/SIM_/etc.)
    for pre in ("LIVE_", "SIM_", "DEMO_", "REAL_", "PAPER_", "BACKTEST_"):
        if d.startswith(pre):
            d = d[len(pre):]
    if "LONG" in d or d in ("BUY", "1"):
        return "buy"
    if "SHORT" in d or d in ("SELL", "-1"):
        return "sell"
    return None


class GoldSharkImporter:
    def __init__(self, experience_db: Optional[ExperienceDatabase] = None):
        self.db = experience_db or ExperienceDatabase()

    def _map_row(self, raw: dict) -> dict:
        out = {}
        for k, v in raw.items():
            key = _HEADER_MAP.get(k, k)
            out[key] = v
        return out

    def ingest_csv(self, path: str, data_source: str = "SIMULATED_REAL_TICKS",
                   default_symbol: str = "XAUUSD", seen_refs: Optional[set] = None,
                   max_abs_mfe: float = 2_000_000.0) -> dict:
        """Import one GoldShark telemetry CSV into the live `trades` table.

        Captures entry indicators (features) AND the peak/exit indicator snapshots
        (reversal signature) when present. Dedupes by TradeID/TradeRef across files
        via `seen_refs`. Derives win/loss from exit_points/MFE when there is no
        explicit profit column.

        Returns {inserted, skipped, resolved, dupes}.
        """
        if data_source == "SIMULATED_OHLC":
            logger.warning("Importing SIMULATED_OHLC rows — these are TAGGED and will be "
                           "excluded from model training (Bug 4).")
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        seen = seen_refs if seen_refs is not None else set()

        inserted = skipped = resolved = dupes = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                row = self._map_row(raw)
                action = _norm_action(row.get("direction", ""))
                entry_price = _to_float(row.get("entry_price"))
                if action is None or entry_price is None:
                    skipped += 1
                    continue

                # cross-file dedup by trade ref (falls back to symbol+entry_time)
                ref = (row.get("trade_ref") or "").strip() or \
                    f"{row.get('symbol') or default_symbol}_{row.get('entry_time') or ''}_{action}_{entry_price}"
                if ref in seen:
                    dupes += 1
                    continue
                seen.add(ref)

                # entry-time indicators ONLY (no look-ahead)
                indicators = {}
                for fld in _ENTRY_FEATURE_FIELDS:
                    fv = _to_float(row.get(fld))
                    if fv is not None:
                        indicators[fld] = fv
                indicators["close"] = entry_price
                for bad in _LOOKAHEAD_FIELDS:
                    indicators.pop(bad, None)

                signal = {
                    "symbol": row.get("symbol") or default_symbol,
                    "action": action,
                    "price": entry_price,
                    "stop_loss": 0, "take_profit": 0,
                    "position_size": _to_float(row.get("lot_size")) or 0,
                    "confidence": 0.0,
                    "strategy_used": "OsMA_Confluence",
                }

                # resolution labels
                mfe = _to_float(row.get("mfe_points"))
                mae = _to_float(row.get("mae_points"))
                exit_pts = _to_float(row.get("exit_points"))
                exit_price = _to_float(row.get("exit_price"))
                exit_reason = row.get("exit_reason") or "goldshark_import"

                # per-row sanity guard: reject garbage/overflow MFE|MAE|exit values
                if any(v is not None and abs(v) > max_abs_mfe for v in (mfe, mae, exit_pts)):
                    skipped += 1
                    continue

                # derive outcome: explicit profit if present, else the sign of the
                # realised exit points (GoldShark BaseExitPts is signed in the trade's
                # favour). Unresolved only if we truly have nothing.
                profit = _to_float(row.get("profit_loss"))
                if profit is None and exit_pts is not None:
                    profit = exit_pts   # points as a proxy P&L sign/magnitude
                if profit is None and exit_price is not None:
                    profit = (exit_price - entry_price) * (1 if action == "buy" else -1)

                # peak / exit indicator snapshots (reversal signature)
                peak_ind = {k: _to_float(row.get(f"peak_{k2}"))
                            for k, k2 in (("osma", "osma"), ("bulls_power", "bulls"),
                                          ("bears_power", "bears"), ("macd_line", "macd"))
                            if _to_float(row.get(f"peak_{k2}")) is not None}
                exit_ind = {k: _to_float(row.get(f"exit_{k2}"))
                            for k, k2 in (("osma", "osma"), ("bulls_power", "bulls"),
                                          ("bears_power", "bears"), ("macd_line", "macd"))
                            if _to_float(row.get(f"exit_{k2}")) is not None}

                if profit is None:
                    self.db.record_trade(signal=signal, indicators=indicators,
                                         outcome="pending", data_source=data_source)
                    inserted += 1
                    continue

                outcome = "win" if profit > 0 else "loss" if profit < 0 else "breakeven"
                tid = self.db.record_trade(signal=signal, indicators=indicators,
                                          outcome="pending", data_source=data_source)
                inserted += 1
                if tid is not None:
                    self.db.update_trade_outcome(
                        trade_id=tid, outcome=outcome, profit_loss=profit,
                        exit_price=exit_price, exit_reason=exit_reason,
                        mfe_points=mfe, mae_points=mae, exit_points=exit_pts,
                    )
                    if peak_ind or exit_ind:
                        self.db.update_trade_signature(tid, peak_indicators=peak_ind or None,
                                                       exit_indicators=exit_ind or None)
                    resolved += 1

        logger.info(f"GoldShark import {os.path.basename(path)} [{data_source}]: "
                    f"inserted={inserted} resolved={resolved} skipped={skipped} dupes={dupes}")
        return {"inserted": inserted, "skipped": skipped, "resolved": resolved, "dupes": dupes}

    def ingest_tree(self, roots, data_source: str = "SIMULATED_REAL_TICKS",
                    name_patterns=("Master_Lifecycle",),
                    exclude=("venv", "site-packages", "node_modules", "BACKUP", "temp_master",
                             "_ML", "Unified_TradeLog", "ATR_TM", "IntraCandle", "Telemetry",
                             "Signal", "Risk", "MIGRATED"),
                    require_cols=("EntryOsMA", "PeakOsMA", "ExitOsMA", "MaxProfitPts", "Direction"),
                    max_rows=2000, max_abs_mfe=2_000_000.0) -> dict:
        """Scan directory trees for TRUE per-trade GoldShark lifecycle CSVs and ingest
        them into the trades DB, deduping by TradeID across files.

        STRICT (data hygiene, after a polluted first pass): only files whose header has
        the full per-trade lifecycle schema (`require_cols`) are accepted; per-BAR ML
        feature dumps (`*_ML`), unified tick logs (`Unified_TradeLog`), telemetry, and
        implausibly large/garbage files (>`max_rows`, or |MFE|>`max_abs_mfe`) are
        rejected. This keeps the reversal-signature seed clean.
        """
        import csv as _csv, glob
        if isinstance(roots, str):
            roots = [roots]
        candidates = []
        for r in roots:
            for p in glob.glob(os.path.join(r, "**", "*.csv"), recursive=True):
                b = os.path.basename(p)
                if any(k in b for k in name_patterns) and not any(x in p for x in exclude):
                    candidates.append(p)
        # header + size validation
        files = []
        rejected = []
        for p in sorted(set(candidates)):
            try:
                with open(p, encoding="utf-8-sig") as f:
                    hdr = f.readline().strip().split(",")
                    n_rows = sum(1 for _ in f)
            except Exception:
                rejected.append((os.path.basename(p), "unreadable")); continue
            if not all(c in hdr for c in require_cols):
                rejected.append((os.path.basename(p), "schema")); continue
            if n_rows > max_rows or n_rows == 0:
                rejected.append((os.path.basename(p), f"rows={n_rows}")); continue
            files.append(p)

        seen = set()
        agg = {"files": 0, "inserted": 0, "skipped": 0, "resolved": 0, "dupes": 0,
               "rejected_files": len(rejected)}
        for p in files:
            b = os.path.basename(p)
            default_symbol = "BTCUSD" if b.upper().startswith("BTC") else \
                "GER40" if "GER" in b.upper() else "XAUUSD"
            try:
                r = self.ingest_csv(p, data_source=data_source,
                                    default_symbol=default_symbol, seen_refs=seen,
                                    max_abs_mfe=max_abs_mfe)
                agg["files"] += 1
                for k in ("inserted", "skipped", "resolved", "dupes"):
                    agg[k] += r[k]
            except Exception as e:
                logger.warning(f"ingest skip {b}: {e}")
        logger.info(f"GoldShark tree ingest: {agg} | rejected {len(rejected)} files")
        for name, why in rejected[:20]:
            logger.debug(f"  rejected {name}: {why}")
        return agg


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Import GoldShark telemetry CSV into the trades DB")
    ap.add_argument("csv_path")
    ap.add_argument("--data-source", default="SIMULATED_REAL_TICKS",
                    choices=["SIMULATED_REAL_TICKS", "SIMULATED_OHLC", "LIVE_MICRO"])
    ap.add_argument("--symbol", default="XAUUSD")
    a = ap.parse_args()
    r = GoldSharkImporter().ingest_csv(a.csv_path, data_source=a.data_source, default_symbol=a.symbol)
    print(r)
