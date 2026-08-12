"""
EA telemetry miner + incremental entry-gate test harness.

GOAL: GoldShark / EMA_OSMA_ATR EAs achieved ~95% ENTRY-DIRECTION success (the trade
went into meaningful profit), even though final P&L was ruined by exits. This harness:

  1. MINES every EA telemetry CSV across all locations into one unified dataset.
  2. Defines candidate ENTRY GATES from the fields the EAs logged (FinalMultiplier,
     momentum freshness = trend/OsMA age, OsMA/Bulls/Bears/EMA-slope/stretch, all
     ATR-normalized so symbols are comparable).
  3. Measures each gate's ENTRY-SUCCESS rate + retained sample, then GREEDILY combines
     gates (keeping only those that raise success without over-shrinking the sample)
     to find the highest-entry-success recipe per symbol.

Entry success = the trade reached >= `green_atr` * ATR of favourable excursion (MFE),
i.e. the ENTRY DIRECTION was right with real room — the thing the EAs got ~95% on.

Read-only analysis. Prints a report + returns the learned per-symbol gate recipe.
Run: python -m tools.mine_ea_telemetry   (or python langchain/tools/mine_ea_telemetry.py)
"""
from __future__ import annotations
import csv, glob, os, statistics
from collections import defaultdict

ROOTS = [
    r"C:\Users\MartinSharkey\AppData\Roaming\MetaQuotes\Terminal",
    r"C:\Users\MartinSharkey\Documents\machine learning",
    # Google Drive "Other computers" backup (real GoldShark telemetry CSVs).
    r"G:\Other computers\My laptop\Downloads",
    r"G:\Other computers\My laptop\Documents",
    r"G:\Other computers\My Mac\Downloads",
]
# Env override (portable across devices): GOLDSHARK_DATA_ROOTS="path1;path2"
_extra = os.getenv("GOLDSHARK_DATA_ROOTS", "")
if _extra:
    ROOTS = [p.strip() for p in _extra.split(";") if p.strip()] + ROOTS
EXCLUDE = ("venv", "site-packages", "node_modules")


def _f(row, k):
    try:
        v = row.get(k, "")
        return float(v) if v not in (None, "") else float("nan")
    except (ValueError, TypeError):
        return float("nan")


def _isnan(x):
    return x != x


def mine_rows():
    """Unify every PER-TRADE lifecycle telemetry CSV into normalized records.

    STRICT: only true per-trade lifecycle logs (one row per trade, with entry+peak+
    outcome). Excludes per-BAR telemetry dumps (IntraCandle/Signal/tick), unified tick
    logs, and oversized files — those pollute the sample with non-trade rows (they made
    XAUUSD base success collapse to 4%)."""
    NAME_OK = ("Master_Lifecycle", "ATR_TM_Lifecycle")   # per-trade lifecycle families
    NAME_BAD = ("IntraCandle", "Telemetry", "Signal", "Risk", "Unified", "BACKUP",
                "MIGRATED", "temp", "_ML")
    REQUIRE = ("Direction", "EntryOsMA", "MaxProfitPts", "PeakOsMA")  # true lifecycle schema
    files = []
    for r in ROOTS:
        for p in glob.glob(os.path.join(r, "**", "*.csv"), recursive=True):
            b = os.path.basename(p)
            if any(x in p for x in EXCLUDE):
                continue
            if not any(k in b for k in NAME_OK) or any(x in b for x in NAME_BAD):
                continue
            files.append(p)
    recs = []
    seen = set()
    for p in sorted(set(files)):
        try:
            with open(p, encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        except Exception:
            continue
        if not rows or len(rows) > 2000:   # per-trade files are small; big = not per-trade
            continue
        hdr = rows[0].keys()
        if not all(k in hdr for k in REQUIRE):
            continue
        for r in rows:
            sym_raw = (r.get("Symbol") or "").upper()
            sym = "BTCUSD" if sym_raw.startswith("BTC") else \
                  "XAUUSD" if sym_raw.startswith("XAU") else \
                  "GER40" if "GER" in sym_raw else (sym_raw[:6] or "XAUUSD")
            atr = _f(r, "ATR_14")
            if _isnan(atr) and "atr" in r:
                atr = _f(r, "atr")
            mfe = _f(r, "MaxProfitPts")
            if _isnan(mfe):
                mfe = _f(r, "mfePts")
            if _isnan(atr) or atr <= 0 or _isnan(mfe):
                continue
            # cross-file dedup
            ref = (r.get("TradeID") or "") + "|" + (r.get("EntryTime") or "") + "|" + str(_f(r, "EntryPrice"))
            if ref in seen:
                continue
            seen.add(ref)
            direction = (r.get("Direction") or "").upper()
            dom = (_f(r, "EntryBulls") if direction == "LONG" else -_f(r, "EntryBears"))
            recs.append({
                "sym": sym, "dir": direction, "atr": atr, "mfe": mfe,
                "osma": abs(_f(r, "EntryOsMA")) / atr,
                "dom": (dom / atr) if not _isnan(dom) else float("nan"),
                "accel": abs(_f(r, "OsMA_Accel")) / atr if "OsMA_Accel" in r else float("nan"),
                "emaslope": abs(_f(r, "EMASlope")) / atr if "EMASlope" in r else float("nan"),
                "stretch": abs(_f(r, "PriceStretch")) / atr if "PriceStretch" in r else float("nan"),
                "mult": _f(r, "FinalMultiplier"),
                "anti": _f(r, "Anticipation_55s"),
                "trend_age": _f(r, "DirTrendAge"),
                "osma_age": _f(r, "DirOsmaSignAge"),
            })
    return recs


# candidate gates: (name, field, op, value). op '>=' or '<=' (for age/stretch ceilings)
def _candidate_gates():
    g = []
    for v in (0.05, 0.10, 0.15, 0.20, 0.30):
        g.append((f"osma>={v}", "osma", ">=", v))
    for v in (0.5, 1.0, 1.5):
        g.append((f"dom>={v}", "dom", ">=", v))
    for v in (0.02, 0.05, 0.10):
        g.append((f"accel>={v}", "accel", ">=", v))
    for v in (2.0, 2.5, 3.0, 3.5):
        g.append((f"mult>={v}", "mult", ">=", v))
    for v in (1.0, 2.0, 3.0):
        g.append((f"anti>={v}", "anti", ">=", v))
    for v in (0.5, 1.0, 1.5, 2.0):
        g.append((f"stretch<={v}", "stretch", "<=", v))
    for v in (2, 3, 5):
        g.append((f"trend_age<={v}", "trend_age", "<=", v))
        g.append((f"osma_age<={v}", "osma_age", "<=", v))
    return g


def _passes(rec, gate):
    _, field, op, val = gate
    x = rec.get(field)
    if x is None or _isnan(x):
        return True   # missing field -> gate can't reject (permissive)
    return x >= val if op == ">=" else x <= val


def _success_rate(recs, gates, green_atr):
    kept = [r for r in recs if all(_passes(r, g) for g in gates)]
    if not kept:
        return 0.0, 0
    succ = sum(1 for r in kept if r["mfe"] >= green_atr * r["atr"])
    return succ / len(kept), len(kept)


def greedy_recipe(recs, green_atr=0.3, min_keep_frac=0.15, max_gates=4):
    """Greedily add gates that raise entry-success while keeping >= min_keep_frac
    of the sample. Returns (gates, success, kept, base)."""
    base, n = _success_rate(recs, [], green_atr)
    min_keep = max(20, int(n * min_keep_frac))
    chosen, cur = [], base
    pool = _candidate_gates()
    while len(chosen) < max_gates:
        best = None
        for g in pool:
            if g in chosen:
                continue
            sr, kept = _success_rate(recs, chosen + [g], green_atr)
            if kept >= min_keep and sr > cur + 0.005:
                if best is None or sr > best[1]:
                    best = (g, sr, kept)
        if not best:
            break
        chosen.append(best[0]); cur = best[1]
    kept = _success_rate(recs, chosen, green_atr)[1]
    return chosen, cur, kept, base


def run(green_atr=0.3):
    recs = mine_rows()
    by_sym = defaultdict(list)
    for r in recs:
        by_sym[r["sym"]].append(r)
    print(f"MINED {len(recs)} unified entries from EA telemetry "
          f"(green = MFE >= {green_atr}xATR = entry direction correct)\n")
    out = {}
    for sym in ("XAUUSD", "BTCUSD", "GER40"):
        rs = by_sym.get(sym, [])
        if len(rs) < 40:
            print(f"{sym}: only {len(rs)} entries — skip"); continue
        gates, sr, kept, base = greedy_recipe(rs, green_atr)
        out[sym] = {"gates": [g[0] for g in gates], "success": round(sr, 3),
                    "kept": kept, "total": len(rs), "base": round(base, 3)}
        print(f"===== {sym}: {len(rs)} entries, base entry-success {base*100:.1f}% =====")
        print(f"  BEST RECIPE: {' AND '.join(g[0] for g in gates) or '(none beat base)'}")
        print(f"  -> entry-success {sr*100:.1f}%  on {kept}/{len(rs)} entries "
              f"({kept/len(rs)*100:.0f}% of signals kept)\n")
    return out


if __name__ == "__main__":
    import sys
    ga = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
    run(ga)
