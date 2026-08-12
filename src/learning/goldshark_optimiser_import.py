"""
GoldShark optimiser-XML ingester.

MT5 Strategy-Tester optimisation reports (ReportOptimizer-*.xml) are MS-spreadsheet
XML: one header row of column names, then one row PER parameter-combination pass
with its backtest result (Profit, Profit Factor, Sharpe, Recovery, Equity DD %,
Trades) followed by every Inp* parameter value.

These are thousands of ALREADY-BACKTESTED parameter sets per symbol — the perfect
SEED so the ML authority gate has real `backtest` support immediately instead of
waiting weeks for live trades. We ingest each pass into the append-only
`adjustment_ledger` as a backtest-proof row (source='goldshark_optimiser'), mapping
the EA's Inp* names to our tunable param names where they correspond.

Streaming parse (iterparse) so 14MB+ files don't blow memory. Non-fatal.
"""
import os
import glob
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

logger = logging.getLogger("goldshark_optimiser_import")

_NS = "{urn:schemas-microsoft-com:office:spreadsheet}"

# EA Inp* -> our tunable param name (only the ones that map to our PARAM_SPACE)
_PARAM_MAP = {
    "InpEMAPeriod": "ema_period", "InpBullsPeriod": "power_period",
    "InpBearsPeriod": "power_period", "InpOsMAFast": "osma_fast",
    "InpOsMASlow": "osma_slow", "InpOsMASignal": "osma_signal",
    "InpATRPeriod": "atr_period", "InpMinAtrValue": "atr_min",
    "InpLongBullsMin": "bulls_min_long", "InpLongBearsMin": "bears_min_long",
    "InpLongOsMAMin": "osma_min_long", "InpShortBullsMax": "bulls_max_short",
    "InpShortBearsMax": "bears_max_short", "InpShortOsMAMax": "osma_max_short",
    "InpStopLossPts": "sl_atr_pts", "InpTakeProfitPts": "tp_pts",
}
_METRICS = ("Profit", "Expected Payoff", "Profit Factor", "Recovery Factor",
            "Sharpe Ratio", "Equity DD %", "Trades")


def _rows(path):
    """Yield each Row as a list of cell string values (streaming)."""
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag == f"{_NS}Row":
            cells = []
            for c in elem.findall(f"{_NS}Cell"):
                d = c.find(f"{_NS}Data")
                cells.append(d.text if d is not None else None)
            yield cells
            elem.clear()


def _symbol_from_title(path):
    try:
        for _, elem in ET.iterparse(path, events=("end",)):
            if elem.tag.endswith("Title") and elem.text:
                t = elem.text.upper()
                for s in ("XAUUSD", "BTCUSD", "ETHUSD", "GER40"):
                    if s in t:
                        return s
                return t.split()[0] if t else None
    except Exception:
        pass
    return None


def ingest_optimiser_xml(path, experience_db, min_trades=10, min_pf=1.0):
    """Ingest one optimiser XML into adjustment_ledger. Only passes with a real
    backtest result (>= min_trades) are recorded; each mapped Inp* becomes a
    ledger row with backtest_pf + fwd(None) + n_samples=Trades, adopted=(PF>=min_pf).
    Returns {parsed, recorded}."""
    if not os.path.exists(path):
        return {"error": "not found", "recorded": 0}
    symbol = _symbol_from_title(path) or "XAUUSD"
    header = None
    parsed = recorded = 0
    for cells in _rows(path):
        if header is None:
            if cells and cells[0] == "Pass":
                header = cells
                # STRATEGY GUARD (owner note 2026-08-12): only ingest reports whose
                # parameter schema is GoldShark's (has our mapped Inp* columns). A
                # DIFFERENT EA (e.g. Quantum Bitcoin, BTCUSD/H1) has a different
                # schema and must NOT be merged into our per-symbol learning as if
                # it were the same strategy. Refuse mismatched schemas.
                matched = sum(1 for inp in _PARAM_MAP if inp in header)
                if matched < 3:
                    logger.warning(f"optimiser XML {os.path.basename(path)}: schema "
                                   f"does not match GoldShark ({matched} mapped Inp* "
                                   f"cols) — SKIPPING (foreign EA, not merged)")
                    return {"symbol": symbol, "parsed": 0, "recorded": 0,
                            "skipped": "foreign-strategy-schema"}
            continue
        if not cells or cells[0] is None:
            continue
        row = dict(zip(header, cells))
        try:
            trades = int(float(row.get("Trades") or 0))
            pf = float(row.get("Profit Factor") or 0)
        except (TypeError, ValueError):
            continue
        if trades < min_trades:
            continue
        parsed += 1
        adopted = pf >= min_pf
        for inp, ourname in _PARAM_MAP.items():
            val = row.get(inp)
            if val in (None, ""):
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            experience_db.record_adjustment(
                symbol=symbol, param=ourname, old_value=None, new_value=fval,
                backtest_pf=pf, fwd_pf=None,
                exp_before=None, exp_after=float(row.get("Expected Payoff") or 0),
                n_samples=trades, source="goldshark_optimiser", adopted=adopted)
            recorded += 1
    logger.info(f"optimiser XML {os.path.basename(path)} [{symbol}]: "
                f"passes={parsed} ledger_rows={recorded}")
    return {"symbol": symbol, "parsed": parsed, "recorded": recorded}


def ingest_optimiser_dir(root, experience_db, pattern="ReportOptimizer*.xml"):
    total = {"files": 0, "recorded": 0}
    for p in glob.glob(os.path.join(root, "**", pattern), recursive=True):
        try:
            r = ingest_optimiser_xml(p, experience_db)
            total["files"] += 1
            total["recorded"] += r.get("recorded", 0)
        except Exception as e:
            logger.warning(f"optimiser ingest skip {p}: {e}")
    return total
