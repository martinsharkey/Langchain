"""
Parse MT5 optimiser SpreadsheetML XML reports (backtest + forward) into per-pass rows,
join backtest<->forward on the Pass number, and rank by ROBUST combined criteria so we can
shortlist configs to re-test on the new Dukascopy data.

MT5 optimiser XML = SpreadsheetML: a header <Row> of column names (Pass, Result, Profit,
Expected Payoff, Profit Factor, Recovery Factor, Sharpe Ratio, Custom, Equity DD %, Trades,
then every Inp*/#define parameter as its own column), then one <Row> per pass.

Forward-test reports mirror the same Pass numbers, so we join on Pass.

Usage:
  python -m tools.parse_optimizer_report BT.xml [FT.xml] [--top N] [--min-trades M] [--min-pf P]
Outputs a ranked shortlist (JSON) of passes with strong BT and (if provided) FT metrics.
"""
from __future__ import annotations

import sys
import json
import argparse
from xml.etree.ElementTree import iterparse

SS = "{urn:schemas-microsoft-com:office:spreadsheet}"


def _rows(path):
    """Yield each spreadsheet Row as a list of cell string values (streaming)."""
    # iterparse over Cell/Data; group by Row. MT5 cells are dense (no ss:Index gaps in these
    # reports), so positional mapping to the header is safe.
    cur = []
    depth_row = False
    for event, elem in iterparse(path, events=("start", "end")):
        tag = elem.tag
        if event == "start" and tag == SS + "Row":
            cur = []
            depth_row = True
        elif event == "end" and tag == SS + "Cell" and depth_row:
            data = elem.find(SS + "Data")
            cur.append(data.text if data is not None else "")
        elif event == "end" and tag == SS + "Row":
            yield cur
            depth_row = False
            elem.clear()


def parse_report(path):
    """Return (header, list[dict]) of passes keyed by column name."""
    it = _rows(path)
    header = None
    passes = []
    for row in it:
        if header is None:
            # first non-empty row is the header
            if row and any(c for c in row):
                header = row
            continue
        if not row or not any(c for c in row):
            continue
        rec = {}
        for i, col in enumerate(header):
            rec[col] = row[i] if i < len(row) else ""
        # only keep rows that have a numeric Pass
        try:
            rec["_pass"] = int(rec.get("Pass", ""))
        except (ValueError, TypeError):
            continue
        passes.append(rec)
    return header, passes


def _f(rec, key, default=0.0):
    try:
        return float(str(rec.get(key, "")).replace(",", ""))
    except (ValueError, TypeError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bt")
    ap.add_argument("ft", nargs="?")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--min-trades", type=int, default=30)
    ap.add_argument("--min-pf", type=float, default=1.2)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    hdr_bt, bt = parse_report(args.bt)
    print(f"BT: {len(bt)} passes, {len(hdr_bt)} columns")
    ft_by_pass = {}
    if args.ft:
        _, ft = parse_report(args.ft)
        ft_by_pass = {r["_pass"]: r for r in ft}
        print(f"FT: {len(ft)} passes")

    # Robust ranking: require BT PF>=min_pf, trades>=min_trades, profit>0; if FT present,
    # require FT PF>=1.0 and profit>0 (survives out-of-sample), and score by the WORSE of
    # BT/FT PF (min) minus an overfit penalty for large BT->FT degradation.
    cands = []
    for r in bt:
        bt_pf = _f(r, "Profit Factor")
        bt_tr = _f(r, "Trades")
        bt_profit = _f(r, "Profit")
        bt_dd = _f(r, "Equity DD %")
        if bt_pf < args.min_pf or bt_tr < args.min_trades or bt_profit <= 0:
            continue
        ft = ft_by_pass.get(r["_pass"])
        if args.ft:
            if not ft:
                continue
            ft_pf = _f(ft, "Profit Factor")
            ft_profit = _f(ft, "Profit")
            ft_tr = _f(ft, "Trades")
            if ft_pf < 1.0 or ft_profit <= 0 or ft_tr < 5:
                continue
            robust = min(bt_pf, ft_pf)
            overfit_gap = max(0.0, bt_pf - ft_pf)
            score = robust - 0.3 * overfit_gap
        else:
            ft_pf = ft_profit = ft_tr = None
            score = bt_pf - 0.01 * bt_dd  # backtest-only: PF penalised by drawdown
        cands.append({
            "pass": r["_pass"], "score": round(score, 3),
            "bt_pf": round(bt_pf, 2), "bt_trades": int(bt_tr), "bt_profit": round(bt_profit, 1),
            "bt_dd": round(bt_dd, 1),
            "ft_pf": round(ft_pf, 2) if ft_pf is not None else None,
            "ft_trades": int(ft_tr) if ft_tr is not None else None,
            "ft_profit": round(ft_profit, 1) if ft_profit is not None else None,
            "params": {k: r[k] for k in hdr_bt if k.startswith("Inp") or k.isupper() or "_" in k},
        })

    cands.sort(key=lambda c: c["score"], reverse=True)
    top = cands[:args.top]
    print(f"\n{len(cands)} passes survive filters; top {len(top)}:")
    for c in top:
        ft_str = (f" | FT PF {c['ft_pf']} ({c['ft_trades']}tr £{c['ft_profit']})"
                  if c["ft_pf"] is not None else "")
        print(f"  pass {c['pass']:>6} score {c['score']:>5} | BT PF {c['bt_pf']} "
              f"({c['bt_trades']}tr £{c['bt_profit']} DD{c['bt_dd']}%){ft_str}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(top, f, indent=2)
        print(f"\nwrote {len(top)} candidates -> {args.out}")


if __name__ == "__main__":
    main()
