"""
Reproduce the GoldShark proven-edge backtest in OUR engine.

Takes the best BASKET-OFF proven config from the MT5 optimizer XML (the pure-confluence
edge — we deliberately do NOT replicate basket/pyramid/hedge money-management), maps its
raw indicator + power-floor settings to our ATR-normalized confluence params, and runs
OUR backtester (walkforward_focused) on gold M1 history to see whether we reproduce a
comparable Profit Factor. This validates that our confluence faithfully implements the
proven edge — the foundation for trusting the live bot.

Run standalone (engine must be stopped so MT5 session is free):
    python reproduce_goldshark.py
"""
import xml.etree.ElementTree as ET, glob, os, statistics

NS = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
GOLD_ATR = 2.3   # gold M1 ATR in price, to convert GoldShark raw floors -> ATR units


def _f(d, k):
    try:
        return float(d.get(k) or "nan")
    except (TypeError, ValueError):
        return float("nan")


def load_best_basket_off():
    xmls = sorted(glob.glob(os.path.join("..", "MT5_OLD_EA's", "**", "*GoldShark1131*.xml"),
                            recursive=True), key=os.path.getsize, reverse=True)
    if not xmls:
        xmls = sorted(glob.glob(os.path.join("..", "MT5_OLD_EA's", "**", "ReportOptimizer*.xml"),
                                recursive=True), key=os.path.getsize, reverse=True)
    rows = ET.parse(xmls[0]).getroot().findall('.//ss:Row', NS)
    hdr = [c.text for c in rows[0].findall('.//ss:Data', NS)]
    data = [dict(zip(hdr, [c.text for c in r.findall('.//ss:Data', NS)]))
            for r in rows[1:] if len(r.findall('.//ss:Data', NS)) >= len(hdr)]
    # BASKET OFF + robust (not curve-fit outliers): PF 1.5-6, trades>=100, DD<=25
    off = [d for d in data if str(d.get("InpEnableBasketStrategy", "")).lower() == "false"
           and 1.5 <= _f(d, "Profit Factor") <= 6.0 and _f(d, "Trades") >= 100
           and _f(d, "Equity DD %") <= 25]
    off.sort(key=lambda d: -(_f(d, "Profit Factor") * (_f(d, "Trades") ** 0.5)))
    return off[0] if off else None, xmls[0]


def to_our_params(gs: dict) -> dict:
    """Map GoldShark raw config -> our confluence params (strength floors ATR-normalized)."""
    return {
        "osma_fast": int(_f(gs, "InpOsmaFast")), "osma_slow": int(_f(gs, "InpOsmaSlow")),
        "osma_signal": int(_f(gs, "InpOsmaSig")), "ema_period": int(_f(gs, "InpEmaPeriod")),
        "atr_period": int(_f(gs, "InpAtrPeriod")), "min_ema_slope": _f(gs, "InpMinEmaSlope"),
        "max_momentum_age": int(_f(gs, "InpMaxMomentumAge")),
        "osma_min_long": round(_f(gs, "InpMinOsMALong") / GOLD_ATR, 3),
        "bulls_min_long": round(_f(gs, "InpMinBullsLong") / GOLD_ATR, 3),
        "osma_max_short": round(_f(gs, "InpMaxOsMAShort") / GOLD_ATR, 3),
        "bears_max_short": round(_f(gs, "InpMinBearsShort") / GOLD_ATR, 3),
        "rsi_long_max": 100.0, "rsi_short_min": 0.0,   # GoldShark uses no RSI
        "allow_fresh_momentum": True, "min_confluence": 3,
    }


def main():
    gs, xml = load_best_basket_off()
    if gs is None:
        print("no basket-off proven config found"); return
    print(f"GoldShark target (basket-OFF, from {os.path.basename(xml)}):")
    print(f"  PF={gs['Profit Factor']}  trades={gs['Trades']}  DD={gs['Equity DD %']}%  profit={gs['Profit']}")
    params = to_our_params(gs)
    print(f"  mapped params: {params}")

    from src.learning.backtester import Backtester
    from src.learning.strategy_registry import StrategyRegistry
    bt = Backtester(StrategyRegistry())
    for tf in ("M1", "M5"):
        for sym in ("XAUUSD-ECN", "XAUUSD"):
            try:
                res = bt.walkforward_focused(sym, params, sl_atr=params.get("sl_atr", 0.8),
                                             tp_rr=params.get("tp_rr", 2.0), timeframe=tf, bars=40000)
            except Exception as e:
                print(f"  {sym} {tf}: error {e}"); continue
            if res:
                print(f"\nOUR backtest {sym} {tf}: PF(min-window)={res.get('score')} "
                      f"pfs={res.get('pfs')} wrs={res.get('wrs')} n={res.get('n_total')} "
                      f"generalizes={res.get('generalizes')}")
                return
    print("\n(no result — MT5 history unavailable? ensure terminal is running + engine stopped)")


if __name__ == "__main__":
    main()
