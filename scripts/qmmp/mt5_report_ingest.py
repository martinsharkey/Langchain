"""MT5 Strategy Tester XML optimization ingest (GitHub #71).

Watches `data/qmmp/<SYMBOL>/mt5_optimizer_imports/` for XML reports exported from
MT5's Strategy Tester, parses each pass into a flat DataFrame, moves processed files
to `_ingested/`, and writes a summary JSON that the Optuna floor optimizer can consume.

Folder layout:
  data/qmmp/<SYMBOL>/mt5_optimizer_imports/
    <YYYYMMDD_HHMM>_build<NNN>.xml   # drop MT5 XML exports here
    _ingested/                        # parser moves files here after processing
    summary.json                      # latest merged summary (tracked)
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import pandas as pd

D = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")


def _safe_float(val: str | None, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except ValueError:
        return default


def _parse_xml(path: str) -> list[dict[str, Any]]:
    """Parse a single MT5 Strategy Tester XML report into pass records."""
    tree = ET.parse(path)
    root = tree.getroot()
    passes: list[dict[str, Any]] = []
    # MT5 XML structure varies; support both <Row> and <OptimizationPass> styles
    for row in root.findall(".//Row") + root.findall(".//OptimizationPass") + root.findall(".//Result"):
        record: dict[str, Any] = {"source_file": os.path.basename(path)}
        # Parameters
        for param in row.findall(".//Parameter") + row.findall(".//Input"):
            name = param.get("Name") or param.get("name")
            value = param.get("Value") or param.get("value")
            if name and value is not None:
                record[name] = _safe_float(value, default=value)
        # Results
        result = row.find(".//Result") if row.tag != "Result" else row
        if result is not None:
            for key in ("Profit", "ExpectedPayoff", "Drawdown", "Sharpe", "Trades",
                        "profit", "expected_payoff", "drawdown", "sharpe", "trades"):
                if result.get(key) is not None:
                    record[key.lower()] = _safe_float(result.get(key))
        if len(record) > 1:
            passes.append(record)
    return passes


def _move_to_ingested(path: str, ingested_dir: str) -> str:
    os.makedirs(ingested_dir, exist_ok=True)
    dest = os.path.join(ingested_dir, os.path.basename(path))
    if os.path.exists(dest):
        base, ext = os.path.splitext(os.path.basename(path))
        dest = os.path.join(ingested_dir, f"{base}_{int(datetime.now(timezone.utc).timestamp())}{ext}")
    shutil.move(path, dest)
    return dest


def ingest_symbol(symbol: str) -> dict[str, Any]:
    """Process all pending XML files for a symbol and merge into summary.json."""
    symbol = symbol.upper()
    base_dir = os.path.join(D, symbol, "mt5_optimizer_imports")
    ingested_dir = os.path.join(base_dir, "_ingested")
    os.makedirs(base_dir, exist_ok=True)

    xml_files = sorted(glob.glob(os.path.join(base_dir, "*.xml")))
    all_passes: list[dict[str, Any]] = []
    processed: list[str] = []

    for xml_path in xml_files:
        try:
            passes = _parse_xml(xml_path)
            if passes:
                all_passes.extend(passes)
            dest = _move_to_ingested(xml_path, ingested_dir)
            processed.append(os.path.basename(dest))
        except Exception as e:
            all_passes.append({"source_file": os.path.basename(xml_path), "parse_error": str(e)})

    summary_path = os.path.join(base_dir, "summary.json")
    existing: list[dict[str, Any]] = []
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    merged = existing + all_passes
    summary = {
        "symbol": symbol,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "n_passes": len([r for r in merged if "parse_error" not in r]),
        "n_errors": len([r for r in merged if "parse_error" in r]),
        "processed_files": processed,
        "passes": merged,
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    return summary


def main():
    import sys
    args = sys.argv[1:]
    if not args:
        print("usage: python -m scripts.qmmp.mt5_report_ingest <SYMBOL> [<SYMBOL> ...]")
        sys.exit(1)
    for sym in args:
        summary = ingest_symbol(sym)
        print(f"{sym}: processed {len(summary['processed_files'])} XML files, "
              f"{summary['n_passes']} passes, {summary['n_errors']} errors -> "
              f"data/qmmp/{sym}/mt5_optimizer_imports/summary.json")


if __name__ == "__main__":
    main()
