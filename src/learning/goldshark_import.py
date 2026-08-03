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
    # resolution
    "timeOut": "exit_time", "ExitTime": "exit_time",
    "priceOut": "exit_price", "ExitPrice": "exit_price",
    "mfePts": "mfe_points", "MaxProfitPts": "mfe_points",
    "maePts": "mae_points", "MaxLossPts": "mae_points",
    "exitPts": "exit_points", "ExitPts": "exit_points",
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
    """GoldShark LONG/SHORT (or 0/1/-1) -> engine buy/sell."""
    d = str(direction).strip().upper()
    if d in ("LONG", "BUY", "1"):
        return "buy"
    if d in ("SHORT", "SELL", "-1"):
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
                   default_symbol: str = "XAUUSD") -> dict:
        """Import one GoldShark telemetry CSV into the live `trades` table.

        Returns {inserted, skipped, resolved}.
        """
        if data_source == "SIMULATED_OHLC":
            logger.warning("Importing SIMULATED_OHLC rows — these are TAGGED and will be "
                           "excluded from model training (Bug 4).")
        if not os.path.exists(path):
            raise FileNotFoundError(path)

        inserted = skipped = resolved = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                row = self._map_row(raw)
                action = _norm_action(row.get("direction", ""))
                entry_price = _to_float(row.get("entry_price"))
                if action is None or entry_price is None:
                    skipped += 1
                    continue

                # entry-time indicators ONLY (no look-ahead)
                indicators = {}
                for fld in _ENTRY_FEATURE_FIELDS:
                    fv = _to_float(row.get(fld))
                    if fv is not None:
                        indicators[fld] = fv
                indicators["close"] = entry_price
                # guard: never let a hindsight field leak in as a feature
                for bad in _LOOKAHEAD_FIELDS:
                    indicators.pop(bad, None)

                signal = {
                    "symbol": row.get("symbol") or default_symbol,
                    "action": action,
                    "price": entry_price,
                    "stop_loss": 0,
                    "take_profit": 0,
                    "position_size": _to_float(row.get("lot_size")) or 0,
                    "confidence": 0.0,
                    "strategy_used": "OsMA_Confluence",
                }

                # resolution -> outcome + labels
                profit = _to_float(row.get("profit_loss"))
                exit_price = _to_float(row.get("exit_price"))
                mfe = _to_float(row.get("mfe_points"))
                mae = _to_float(row.get("mae_points"))
                exit_pts = _to_float(row.get("exit_points"))
                exit_reason = row.get("exit_reason") or "goldshark_import"

                if profit is None:
                    # unresolved -> pending row, features only
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
                    resolved += 1

        logger.info(f"GoldShark import {os.path.basename(path)} [{data_source}]: "
                    f"inserted={inserted} resolved={resolved} skipped={skipped}")
        return {"inserted": inserted, "skipped": skipped, "resolved": resolved}


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
