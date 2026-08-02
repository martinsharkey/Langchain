"""
GoldShark log re-analysis (#50 / "did we miss anything").

Context: GoldShark EA logs were partly written to the WRONG executor, and earlier
analysis mis-read them. This re-analyses the consolidated trade logs CORRECTLY:

  * The entry FINGERPRINT (EntryOsMA/Bulls/Bears/EMASlope/M5_*) is on the LIVE record.
  * The OUTCOME (MaxProfitPts/MaxLossPts/BaseExitPts) is on the EXIT record.
  * They MUST be joined by TradeID (reading them off one record => zeros/garbage,
    the bug that hid signal before).

Honest caveats baked in: BaseExitPts is a managed/best-case exit metric (137 EXITs
show WR 100% / worst +1 => NOT raw P&L, do not claim a 100% win edge). The
trustworthy signals are the correct-direction rate and the real peak-vs-adverse
excursion (MaxProfit/MaxLoss), plus whether the entry fingerprint predicts them.

Run: python -m scripts.analyze_goldshark [csv_path]
Local workspace files only (no S3, no MT5).
"""

from __future__ import annotations

import csv
import sys
import statistics

DEFAULT = r"..\MT5_OLD_EA's\Goldshark\consolidated_trade_data\MASTER_CONSOLIDATED_CLEAN.csv"


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def load_joined(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    live = {r["TradeID"]: r for r in rows if r.get("RecordType") == "LIVE"}
    exit_ = {r["TradeID"]: r for r in rows if r.get("RecordType") == "EXIT"}
    joined = []
    for t in set(live) & set(exit_):
        l, e = live[t], exit_[t]
        rec = {"tid": t, "direction": l.get("Direction"),
               "bulls": _num(l.get("EntryBulls")), "bears": _num(l.get("EntryBears")),
               "osma": _num(l.get("EntryOsMA")), "ema_slope": _num(l.get("EMASlope")),
               "m5_osma": _num(l.get("M5_OsMA")), "atr": _num(l.get("ATR_14")),
               "peak": _num(e.get("MaxProfitPts")), "adverse": abs(_num(e.get("MaxLossPts")) or 0),
               "base_exit": _num(e.get("BaseExitPts"))}
        if rec["peak"] is not None and rec["bulls"] is not None:
            joined.append(rec)
    return joined, len(live), len(exit_)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    joined, nl, ne = load_joined(path)
    print(f"LIVE {nl}, EXIT {ne}, joined-with-data {len(joined)}")
    if not joined:
        print("no joined records"); return
    peaks = [j["peak"] for j in joined]; adv = [j["adverse"] for j in joined]
    corr = sum(1 for j in joined if j["peak"] > 0)
    print(f"correct-direction (reached +peak): {corr}/{len(joined)} = {corr/len(joined)*100:.0f}%")
    print(f"median MaxProfit {statistics.median(peaks):.0f}pts | median MaxLoss {statistics.median(adv):.0f}pts "
          f"| peak:adverse {statistics.median(peaks)/max(statistics.median(adv),1e-9):.2f}")
    print("CAVEAT: BaseExitPts is a managed/best-case metric (not raw P&L) — no win-rate/edge claim from it.")

    def med(g, k):
        vals = [x[k] for x in g if x[k] is not None]
        return round(statistics.median(vals), 1) if vals else 0

    print("\n=== does the entry fingerprint predict a bigger favourable peak? ===")
    tests = {
        "Bulls>0 AND Bears>0": lambda r: r["bulls"] > 0 and r["bears"] > 0,
        "EntryBulls>2": lambda r: r["bulls"] > 2,
        "M5_OsMA>0 aligned": lambda r: (r["m5_osma"] or 0) > 0,
        "EMASlope>0": lambda r: (r["ema_slope"] or 0) > 0,
    }
    for label, cond in tests.items():
        g = [r for r in joined if cond(r)]; ng = [r for r in joined if not cond(r)]
        print(f"  {label:22} n={len(g):3} peak {med(g,'peak'):>5} adv {med(g,'adverse'):>4}  |  "
              f"NOT n={len(ng):3} peak {med(ng,'peak'):>5} adv {med(ng,'adverse'):>4}")
    print("\nVERDICT: a filter EARNS its place only if its group shows a materially higher "
          "peak:adverse than NOT. On this XAUUSD sample the differences are small (see #50).")


if __name__ == "__main__":
    main()
