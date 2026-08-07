"""
Catalog MT5 optimisation caches (.opt) and tester .set files across all local MT5 installs
into structured evidence the researcher can use (R10: evidence-first).

.opt files are MT5's PROPRIETARY binary optimisation cache (UTF-16 + binary structs). Their
FILENAMES are reliable structured evidence: <EA>.<SYMBOL>_<broker>.<TF>.<from>.<to>.<model>.<hash>.opt
We parse those deterministically. Full per-pass results inside the binary are NOT reliably
parseable without MT5; the canonical way to unlock them is MT5 Strategy Tester ->
right-click optimisation -> "Export to XML" (which is how the existing optimiser XMLs were
made). This module produces a catalog + a to-export list, and copies .set files.

Usage: python -m tools.catalog_mt5_evidence
"""
from __future__ import annotations
import os, re, json, glob, hashlib
from datetime import datetime, timezone

_INSTALLS = [
    os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal"),
    r"C:\Program Files\Fusion Markets MetaTrader 5",
    r"C:\Program Files\VT Markets (Pty) MT5 Terminal",
    r"C:\Program Files\VT Markets (Pty) MT5 Terminal 2",
]

# <EA>.<SYMBOL>.<TF>.<YYYYMMDD>.<YYYYMMDD>.<model>.<hash>.opt  (broker suffix optional on symbol)
_OPT_RE = re.compile(
    r"^(?P<ea>.+?)\.(?P<symbol>[A-Za-z0-9\-\._]+?)\.(?P<tf>M\d+|H\d+|D1|W1|MN)\."
    r"(?P<frm>\d{8})\.(?P<to>\d{8})\.(?P<model>\d+)\.[0-9A-F]+\.opt$", re.I)

_MODEL = {"0": "every_tick", "1": "1min_ohlc", "2": "open_prices", "3": "math_calc",
          "4": "every_tick_real"}


def catalog(out_dir: str = None) -> dict:
    out_dir = out_dir or os.path.join("data", "reprodata", "mt5_installs")
    os.makedirs(out_dir, exist_ok=True)
    opt_records, set_records = [], []
    seen_opt = set()
    for base in _INSTALLS:
        if not base or not os.path.isdir(base):
            continue
        for path in glob.glob(os.path.join(base, "**", "*.opt"), recursive=True):
            fn = os.path.basename(path)
            key = fn.split(".opt")[0][-40:]  # dedup by tail (hash) across profiles
            if key in seen_opt:
                continue
            seen_opt.add(key)
            m = _OPT_RE.match(fn)
            rec = {"file": fn, "size_mb": round(os.path.getsize(path) / 1e6, 1), "path": path}
            if m:
                d = m.groupdict()
                rec.update({
                    "ea": d["ea"], "symbol": d["symbol"].split("_")[0], "timeframe": d["tf"],
                    "from": d["frm"], "to": d["to"],
                    "model": _MODEL.get(d["model"], d["model"]),
                    "days": (datetime.strptime(d["to"], "%Y%m%d") - datetime.strptime(d["frm"], "%Y%m%d")).days,
                })
            opt_records.append(rec)
        for path in glob.glob(os.path.join(base, "**", "*.set"), recursive=True):
            try:
                with open(path, "rb") as f:
                    h = hashlib.md5(f.read()).hexdigest()
            except Exception:
                continue
            set_records.append({"file": os.path.basename(path), "md5": h, "path": path})

    # dedup sets by content
    uniq_sets = {}
    for s in set_records:
        uniq_sets.setdefault(s["md5"], s)
    ea_counts = {}
    for r in opt_records:
        ea_counts[r.get("ea", "?")] = ea_counts.get(r.get("ea", "?"), 0) + 1

    catalog = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "opt_caches": sorted(opt_records, key=lambda r: -r["size_mb"]),
        "opt_count": len(opt_records),
        "opt_by_ea": dict(sorted(ea_counts.items(), key=lambda x: -x[1])),
        "unique_sets": len(uniq_sets),
        "note": ("Full per-pass forward/backtest data inside .opt is unlocked by MT5 Strategy "
                 "Tester -> Export to XML. Filenames parsed here give EA/symbol/TF/date/model. "
                 "See to_export for the highest-value caches to export next."),
        # highest-value caches to export to XML (biggest = most passes), goldshark/gold first
        "to_export": [r for r in sorted(opt_records, key=lambda r: -r["size_mb"])
                      if r.get("symbol", "").upper().startswith(("XAU", "BTC", "GER"))
                      or "shark" in r.get("ea", "").lower()][:20],
    }
    with open(os.path.join(out_dir, "mt5_evidence_catalog.json"), "w") as f:
        json.dump(catalog, f, indent=1)
    return catalog


if __name__ == "__main__":
    c = catalog()
    print(f"opt caches: {c['opt_count']} | unique sets: {c['unique_sets']}")
    print("top EAs by #optimisations:")
    for ea, n in list(c["opt_by_ea"].items())[:12]:
        print(f"  {ea}: {n}")
    print(f"\nhighest-value gold/BTC/GER/shark caches to export to XML: {len(c['to_export'])}")
    for r in c["to_export"][:10]:
        print(f"  {r.get('ea')} {r.get('symbol')} {r.get('timeframe')} "
              f"{r.get('from')}->{r.get('to')} ({r.get('model')}, {r['size_mb']}MB)")
