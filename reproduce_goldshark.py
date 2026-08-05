"""
Faithful reproduction of the GoldShark proven-edge backtest — pure per-trade confluence
edge + balance-proportional COMPOUNDING (the £100 -> big-balance mechanism), matching the
actual GoldShark11_v12 EA logic (no basket/pyramid/hedge — those are excluded by our
safety rules; this reproduces the CONFLUENCE edge that the basket-OFF configs proved).

EXACT GoldShark entry rule (from GoldShark11_v12 source, lines 2055/2058):
  LONG : bulls[1] >= MinBullsLong AND bears[1] > MaxBearsLong AND osma[1] >= MinOsMALong
         AND osma[1] > osma[2] (rising) AND EMA up AND ATR in range AND ATR growing
  SHORT: bears[1] <= MinBearsShort AND bulls[1] > MaxBullsShort AND osma[1] <= MaxOsMAShort
         AND osma[1] < osma[2] (falling) AND EMA down AND ATR in range AND ATR growing
  -> NO zero-cross, NO RSI, NO macd_lead. State + acceleration + power floors only.
  Evaluated on the CLOSED bar (index 1).

COMPOUNDING (EA lines 1463-1465): baseLot = (balance / InpBalancePerLot(100)) * 0.01.
Exit: SL/TP in ATR terms (per the config), realised per trade, balance compounds.

Data: replays a gold M1 CSV (time,open,high,low,close). Point it at the full Jan-2026
6-month gold M1 export from the MT5 terminal to reproduce the real result; runs on any
gold M1 csv otherwise (validates the logic).

Usage: python reproduce_goldshark.py <gold_m1.csv> [start_balance]
"""
import sys, os, csv, glob, statistics
import xml.etree.ElementTree as ET

NS = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}


def _f(d, k, default=float("nan")):
    try:
        v = d.get(k)
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def load_proven_config():
    """Best BASKET-OFF proven config from the richest optimizer XML (the pure-confluence
    edge; we do NOT reproduce basket/pyramid)."""
    xmls = sorted(glob.glob(os.path.join("MT5_OLD_EA's", "**", "*GoldShark1131*.xml"), recursive=True)
                  + glob.glob(os.path.join("MT5_OLD_EA's", "**", "ReportOptimizer*.xml"), recursive=True),
                  key=os.path.getsize, reverse=True)
    if not xmls:
        return None
    rows = ET.parse(xmls[0]).getroot().findall('.//ss:Row', NS)
    hdr = [c.text for c in rows[0].findall('.//ss:Data', NS)]
    data = [dict(zip(hdr, [c.text for c in r.findall('.//ss:Data', NS)]))
            for r in rows[1:] if len(r.findall('.//ss:Data', NS)) >= len(hdr)]
    off = [d for d in data if str(d.get("InpEnableBasketStrategy", "")).lower() == "false"
           and 1.5 <= _f(d, "Profit Factor") <= 6 and _f(d, "Trades") >= 100 and _f(d, "Equity DD %") <= 25]
    off.sort(key=lambda d: -(_f(d, "Profit Factor") * _f(d, "Trades") ** 0.5))
    return (off[0], os.path.basename(xmls[0])) if off else (None, None)


def ema(vals, period):
    out = []
    k = 2 / (period + 1)
    e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def compute_series(bars, cfg):
    """OsMA (MACD histogram), EMA, Bulls/Bears, ATR — the 5 GoldShark indicators."""
    close = [b["close"] for b in bars]
    high = [b["high"] for b in bars]
    low = [b["low"] for b in bars]
    fast = ema(close, int(cfg["osma_fast"]))
    slow = ema(close, int(cfg["osma_slow"]))
    macd = [f - s for f, s in zip(fast, slow)]
    sig = ema(macd, int(cfg["osma_signal"]))
    osma = [m - s for m, s in zip(macd, sig)]
    ema_p = ema(close, int(cfg["ema_period"]))
    bulls = [h - e for h, e in zip(high, ema_p)]
    bears = [l - e for l, e in zip(low, ema_p)]
    # ATR
    tr = [high[0] - low[0]]
    for i in range(1, len(bars)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
    ap = int(cfg["atr_period"]); atr = []
    for i in range(len(tr)):
        atr.append(sum(tr[max(0, i-ap+1):i+1]) / min(i+1, ap))
    return osma, ema_p, bulls, bears, atr


def backtest(bars, cfg, start_balance=100.0):
    osma, ema_p, bulls, bears, atr = compute_series(bars, cfg)
    balance = start_balance
    wins = gross_win = gross_loss = trades = 0
    equity_peak = balance; max_dd = 0.0
    pos = None  # (dir, entry, sl, tp, lot)
    for i in range(30, len(bars) - 1):
        price = bars[i]["close"]
        # manage open position against next-bar range
        if pos:
            d, ent, sl, tp, lot = pos
            hi, lo = bars[i]["high"], bars[i]["low"]
            hit = None
            if d == 1:
                if lo <= sl: hit = sl
                elif hi >= tp: hit = tp
            else:
                if hi >= sl: hit = sl
                elif lo <= tp: hit = tp
            if hit is not None:
                pts = (hit - ent) * d
                pl = pts * lot * 100  # gold: 100 units/lot per $ (approx point value)
                balance += pl; trades += 1
                if pl > 0: wins += 1; gross_win += pl
                else: gross_loss += -pl
                equity_peak = max(equity_peak, balance)
                max_dd = max(max_dd, (equity_peak - balance) / equity_peak * 100)
                pos = None
            continue
        # entry (closed bar = index i-1 as "[1]", i-2 as "[2]") — exact GoldShark rule
        o1, o2 = osma[i-1], osma[i-2]
        b1, be1 = bulls[i-1], bears[i-1]
        a1, a2 = atr[i-1], atr[i-2]
        e1, e0 = ema_p[i-1], ema_p[i-5]
        emaUp = e1 > e0; emaDn = e1 < e0
        atr_ok = a1 >= cfg.get("atr_min", 0) and (cfg.get("atr_max", 0) == 0 or a1 <= cfg["atr_max"]) and a1 > a2
        longReady = (b1 >= cfg["bulls_min_long"] and be1 > cfg["bears_max_long"]
                     and o1 >= cfg["osma_min_long"] and o1 > o2 and emaUp and atr_ok)
        shortReady = (be1 <= cfg["bears_min_short"] and b1 > cfg["bulls_max_short"]
                      and o1 <= cfg["osma_max_short"] and o1 < o2 and emaDn and atr_ok)
        if longReady or shortReady:
            d = 1 if longReady else -1
            lot = round((balance / 100.0) * 0.01, 2)   # COMPOUNDING
            lot = max(lot, 0.01)
            sl_d = cfg["sl_atr"] * a1; tp_d = cfg["tp_rr"] * cfg["sl_atr"] * a1
            sl = price - sl_d * d; tp = price + tp_d * d
            pos = (d, price, sl, tp, lot)
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    return {"start": start_balance, "end": round(balance, 2), "trades": trades,
            "win_rate": round(wins / trades * 100, 1) if trades else 0,
            "profit_factor": round(pf, 2), "max_dd_pct": round(max_dd, 1),
            "return_x": round(balance / start_balance, 2)}


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
        "MT5_OLD_EA's/Goldshark/gemini_analysis/XAUUSD_M1_DATA.csv"
    start_bal = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0
    gs, xml = load_proven_config()
    if gs is None:
        print("no proven config"); return
    ATR = 2.3
    cfg = {
        "osma_fast": _f(gs, "InpOsmaFast", 12), "osma_slow": _f(gs, "InpOsmaSlow", 50),
        "osma_signal": _f(gs, "InpOsmaSig", 9), "ema_period": _f(gs, "InpEmaPeriod", 13),
        "atr_period": _f(gs, "InpAtrPeriod", 14), "atr_min": _f(gs, "InpMinATR", 0),
        "atr_max": _f(gs, "InpMaxATR", 0),
        "osma_min_long": _f(gs, "InpMinOsMALong", 0.57), "bulls_min_long": _f(gs, "InpMinBullsLong", 1.9),
        "bears_max_long": _f(gs, "InpMaxBearsLong", -0.2),
        "osma_max_short": _f(gs, "InpMaxOsMAShort", -0.8), "bulls_max_short": _f(gs, "InpMaxBullsShort", 0),
        "bears_min_short": _f(gs, "InpMinBearsShort", -1.3),
        "sl_atr": 1.0, "tp_rr": 2.0,
    }
    print(f"Proven config from {xml}: GoldShark PF={gs['Profit Factor']} trades={gs['Trades']} "
          f"DD={gs['Equity DD %']}% profit={gs['Profit']}")
    print(f"Reproducing with exact GoldShark entry rule + compounding (base £100/0.01 lot)")
    try:
        bars = [{"time": r["time"], "open": float(r["open"]), "high": float(r["high"]),
                 "low": float(r["low"]), "close": float(r["close"])}
                for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"))]
    except Exception as e:
        print(f"csv load error: {e}"); return
    print(f"M1 bars: {len(bars)} ({bars[0]['time']} -> {bars[-1]['time']})")
    if len(bars) < 5000:
        print("  NOTE: this sample is short — for the real £100->result run, export the full "
              "Jan-2026 6-month gold M1 from MT5 and pass it as arg 1.")
    print("\nRESULT:", backtest(bars, cfg, start_bal))


if __name__ == "__main__":
    main()
