"""
Backtester (L6) — the validation guardrail.

Pulls MONTHS of real MT5 history and replays it bar-by-bar with NO look-ahead:
at each step, indicators are computed ONLY from bars up to that point, strategies
vote, and simulated trades are opened with fixed SL/TP and resolved on later bars.

This is what makes reflection/synthesis honest: a candidate strategy (single or
combination) must beat a baseline OUT-OF-SAMPLE before it earns live weight.

Design notes:
  * No look-ahead: indicators at bar i use bars[:i+1] only.
  * Train/validate split: first fraction is "train" (ignored for scoring),
    remainder is "validate" (scored) — so results aren't fit to the same data.
  * Symbol-agnostic: SL/TP in points scaled by the symbol's own ATR.
  * Runs in a background thread from the adaptive loop; never blocks live trading.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Callable

from src.strategies.indicators import compute_indicator_series
from src.strategies.sessions import session_of
from src.learning.exit_model import TradeState, resolve_exit_tick, resolve_exit_bar
from src.utils.logger import get_logger

logger = get_logger("backtester")


@dataclass
class BacktestResult:
    label: str
    symbol: str
    timeframe: str
    bars_tested: int
    trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    total_r: float
    avg_bars_held: float
    max_drawdown_r: float
    passed: bool = False
    note: str = ""
    session_scores: dict = None  # session -> {trades, wins, losses, gross_win_r, gross_loss_r}


class Backtester:
    def __init__(self, registry, rates_fn: Optional[Callable] = None,
                 ticks_fn: Optional[Callable] = None, data_manager=None,
                 refresh_manager=None):
        """rates_fn/ticks_fn default to the live MT5 data layer. Inject alternatives
        (e.g. src.data_sources.dukascopy.DukascopySource, DataManager) to backtest
        the SAME engine on a DIFFERENT data source.
        Both must match src.mt5.data.get_rates / get_ticks signatures.
        data_manager: optional DataManager instance for freshness checks.
        refresh_manager: optional DataRefreshManager for auto-refresh."""
        self.registry = registry
        if rates_fn is None or ticks_fn is None:
            from src.mt5.data import get_rates as _gr, get_ticks as _gt
            rates_fn = rates_fn or _gr
            ticks_fn = ticks_fn or _gt
        self._get_rates = rates_fn
        self._get_ticks = ticks_fn
        self.data_manager = data_manager
        self.refresh_manager = refresh_manager

    def walkforward_focused(self, symbol, params, sl_atr=1.0, tp_rr=2.0,
                            giveback=0.55, arm=0.5, timeframe="M15",
                            bars=12000, windows=3, warmup=210):
        """
        Walk-forward backtest of the symbol's FOCUSED pockets with a GIVEN
        indicator param set + realistic manager exits (giveback of peak).
        Recomputes indicators with `params` so tuning EMA/OsMA/RSI actually
        changes signals. Returns generalization metrics for the optimizer:
          {pfs, wrs, n_total, generalizes, score}  (score = min PF across windows)
        """
        from src.strategies.indicators import compute_indicator_series
        from src.learning.edge_weights import focused_rules

        # Auto-refresh: ensure data is fresh before backtesting
        if self.refresh_manager is not None:
            self.refresh_manager.ensure_fresh(symbol, timeframe)

        rates = self._get_rates(symbol, timeframe=timeframe, count=bars)
        if not rates or len(rates) < 2000:
            logger.warning(f"[BACKTEST] {symbol} {timeframe}: only {len(rates) if rates else 0} bars "
                           f"(<2000) — cannot validate; warm the cache for a rolling window.")
            return None
        series = compute_indicator_series(rates, params)  # params drive indicators
        rules = focused_rules(symbol) or []
        if not rules:
            logger.warning(f"[BACKTEST] {symbol}: no focused rules — cannot validate")
            return None
        fns = {nm: (self.registry.get(nm).signal_fn, {**self.registry.get(nm).params, **(params or {})})
               for nm, _ in rules if self.registry.get(nm)}
        if not fns:
            logger.warning(f"[BACKTEST] {symbol}: focused rules {rules} have no registry entries")
            return None
        n = len(rates); seg = (n - warmup) // windows

        session_scores = {
            s: {"trades": 0, "wins": 0, "losses": 0, "gross_win_r": 0.0, "gross_loss_r": 0.0}
            for s in ("Asian", "London", "NewYork", "Off")
        }

        # TICK DATA (real-life fills): fetch real bid/ask ticks for the bar window and
        # index them by bar so SL/TP are resolved TICK-BY-TICK in correct sequence with
        # true spread — the MT5 'Every Tick based on Real Ticks' model. Falls back to
        # bar high/low only when ticks are unavailable.
        tick_by_bar = None
        try:
            t0 = int(rates[0]["timestamp"]); t1 = int(rates[-1]["timestamp"]) + 60
            tk = self._get_ticks(symbol, t0, t1)
            if tk and tk["time"]:
                tt = tk["time"]; tb = tk["bid"]; ta = tk["ask"]
                tick_by_bar = [None] * n
                bar_ts = [int(r["timestamp"]) for r in rates]
                ci = 0
                for bi in range(n):
                    end = bar_ts[bi + 1] if bi + 1 < n else bar_ts[bi] + 60
                    seg_t = []
                    while ci < len(tt) and tt[ci] < end:
                        if tt[ci] >= bar_ts[bi]:
                            seg_t.append((tb[ci], ta[ci]))
                        ci += 1
                    tick_by_bar[bi] = seg_t
                logger.info(f"backtest {symbol}: TICK-accurate fills ({len(tt)} ticks over {n} bars)")
        except Exception as e:
            logger.debug(f"tick fetch skip {symbol}: {e}")

        def _resolve_open(ot, i, price, giveback):
            """Return realised R if the trade closes in bar i, else None. Uses ticks
            (correct intrabar sequence + spread) when available; else bar high/low."""
            ticks = tick_by_bar[i] if tick_by_bar else None
            if ticks:
                return resolve_exit_tick(ot, ticks)
            # bar fallback
            hib, lob = rates[i]["high"], rates[i]["low"]
            return resolve_exit_bar(ot, hib, lob, price)

        def _sim(lo, hi):
            w = l = 0; gw = gl = 0.0; ot = None
            for i in range(lo, hi):
                ind = series[i]
                if not ind or not ind.get("close"):
                    continue
                price = ind["close"]; atr = ind.get("atr") or 0
                if atr <= 0:
                    continue
                if ot:
                    r = _resolve_open(ot, i, price, giveback)
                    if r is not None:
                        try:
                            ts = rates[i]["timestamp"]
                            hour = datetime.fromtimestamp(int(ts)).hour
                            sess = session_of(hour)
                        except Exception:
                            sess = "Off"
                        if r > 0:
                            w += 1; gw += r
                            session_scores[sess]["wins"] += 1
                            session_scores[sess]["gross_win_r"] += r
                        else:
                            l += 1; gl += abs(r)
                            session_scores[sess]["losses"] += 1
                            session_scores[sess]["gross_loss_r"] += abs(r)
                        session_scores[sess]["trades"] += 1
                        ot = None
                if ot:
                    continue
                regime = self.registry._detect_market_regime(ind)
                action = None
                for nm, regs in rules:
                    if nm not in fns or regime not in regs:
                        continue
                    try:
                        s = fns[nm][0](ind, fns[nm][1])
                    except Exception:
                        continue
                    if s.action in ("buy", "sell"):
                        action = s.action; break
                if not action:
                    continue
                risk = sl_atr * atr; tpd = tp_rr * risk
                sl = price - risk if action == "buy" else price + risk
                tp = price + tpd if action == "buy" else price - tpd
                ot = TradeState(dir=action, entry=price, sl=sl, tp=tp, risk=risk,
                                rr=tp_rr, peak=price, arm=arm * atr)
            tot = w + l
            pf = round(gw / gl, 2) if gl > 0 else (gw if gw else 0.0)
            return tot, (round(w / tot * 100, 1) if tot else 0), pf, round(gw - gl, 1)

        pfs = []; wrs = []; n_total = 0
        for k in range(windows):
            lo = warmup + k * seg; hi = warmup + (k + 1) * seg if k < windows - 1 else n
            tot, wr, pf, R = _sim(lo, hi)
            if tot < 15:      # too few trades in a window -> unreliable
                for s, d in session_scores.items():
                    if d["gross_loss_r"] > 0:
                        d["pf"] = round(d["gross_win_r"] / d["gross_loss_r"], 2)
                    else:
                        d["pf"] = round(d["gross_win_r"], 2) if d["gross_win_r"] else 0.0
                    d["wr"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0.0
                return {"pfs": pfs, "wrs": wrs, "n_total": n_total,
                        "generalizes": False, "score": -1.0, "session_scores": session_scores}
            pfs.append(pf); wrs.append(wr); n_total += tot
        generalizes = all(p >= 1.0 for p in pfs)
        for s, d in session_scores.items():
            if d["gross_loss_r"] > 0:
                d["pf"] = round(d["gross_win_r"] / d["gross_loss_r"], 2)
            else:
                d["pf"] = round(d["gross_win_r"], 2) if d["gross_win_r"] else 0.0
            d["wr"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0.0
        return {"pfs": pfs, "wrs": wrs, "n_total": n_total,
                "generalizes": generalizes, "score": min(pfs) if pfs else -1.0,
                "session_scores": session_scores}

    def _load_history(self, symbol: str, timeframe: str, bars: int) -> list[dict]:
        # MT5 copy_rates_from_pos caps around ~ tens of thousands; request in one call.
        rates = self._get_rates(symbol, timeframe=timeframe, count=bars)
        if not rates or len(rates) < 300:
            logger.warning(f"backtest: insufficient history for {symbol} {timeframe} "
                           f"({0 if not rates else len(rates)} bars)")
            return []
        return rates

    def run_combo(
        self,
        symbol: str,
        strategy_names: list[str],
        timeframe: str = "M15",
        bars: int = 8000,
        min_agreement: int = 1,
        sl_atr: float = 1.0,
        tp_atr: float = 1.5,
        train_frac: float = 0.5,
        warmup: int = 210,
    ) -> Optional[BacktestResult]:
        """
        Backtest a single strategy or a COMBINATION (strategy_names) requiring
        `min_agreement` of them to agree. Returns a scored BacktestResult on the
        validation split, or None if not enough data.
        """
        rates = self._load_history(symbol, timeframe, bars)
        if not rates:
            return None

        n = len(rates)
        val_start = max(warmup, int(n * train_frac))
        fns = []
        for nm in strategy_names:
            sd = self.registry.get(nm)
            if sd:
                fns.append((nm, sd.signal_fn, sd.params))
        if not fns:
            return None

        # Precompute ALL indicators vectorized (O(n)); each bar reads its row.
        series = compute_indicator_series(rates)
        if not series:
            return None

        trades = 0
        wins = 0
        losses = 0
        gross_win_r = 0.0
        gross_loss_r = 0.0
        r_curve = []
        cum_r = 0.0
        peak = 0.0
        max_dd = 0.0
        bars_held_total = 0
        from src.strategies.sessions import session_of
        session_scores = {
            s: {"trades": 0, "wins": 0, "losses": 0, "gross_win_r": 0.0, "gross_loss_r": 0.0}
            for s in ("Asian", "London", "NewYork", "Off")
        }

        open_trade = None  # dict: dir, entry, sl, tp, bar, session

        for i in range(warmup, n):
            ind = series[i]
            if not ind or ind.get("close") is None:
                continue
            price = ind["close"]
            atr = ind.get("atr") or 0
            if atr <= 0:
                continue

            # resolve an open trade first (check this bar's high/low)
            if open_trade:
                hi = rates[i]["high"]
                lo = rates[i]["low"]
                closed_r = None
                if open_trade["dir"] == "buy":
                    if lo <= open_trade["sl"]:
                        closed_r = -1.0
                    elif hi >= open_trade["tp"]:
                        closed_r = open_trade["rr"]
                else:
                    if hi >= open_trade["sl"]:
                        closed_r = -1.0
                    elif lo <= open_trade["tp"]:
                        closed_r = open_trade["rr"]
                    if closed_r is not None:
                        # Realism haircut: demo/backtests have ~0 slippage+spread which
                        # over-states edge vs a live account. Deduct an assumed cost
                        # (in R units) from every trade so results are LIVE-realistic.
                        from src import config
                        sl_points = open_trade.get("sl_points", 0) or 1
                        cost_r = ((config.ASSUMED_SLIPPAGE_POINTS +
                                   open_trade.get("spread_points", 0) * config.BACKTEST_SPREAD_HAIRCUT)
                                  / sl_points)
                        closed_r -= cost_r
                        scored = i >= val_start
                        if scored:
                            trades += 1
                            cum_r += closed_r
                            r_curve.append(cum_r)
                            peak = max(peak, cum_r)
                            max_dd = max(max_dd, peak - cum_r)
                            bars_held_total += i - open_trade["bar"]
                            if closed_r > 0:
                                wins += 1
                                gross_win_r += closed_r
                            else:
                                losses += 1
                                gross_loss_r += abs(closed_r)
                            sess = open_trade.get("session", "Off")
                            if sess in session_scores:
                                session_scores[sess]["trades"] += 1
                                if closed_r > 0:
                                    session_scores[sess]["wins"] += 1
                                    session_scores[sess]["gross_win_r"] += closed_r
                                else:
                                    session_scores[sess]["losses"] += 1
                                    session_scores[sess]["gross_loss_r"] += abs(closed_r)
                        open_trade = None

            if open_trade:
                continue  # one at a time

            # gather votes
            buys = sells = 0
            for nm, fn, params in fns:
                try:
                    sig = fn(ind, params)
                except Exception:
                    continue
                if sig.action == "buy":
                    buys += 1
                elif sig.action == "sell":
                    sells += 1
            direction = None
            if buys >= min_agreement and buys > sells:
                direction = "buy"
            elif sells >= min_agreement and sells > buys:
                direction = "sell"
            if not direction:
                continue

            sl_dist = sl_atr * atr
            tp_dist = tp_atr * atr
            point = ind.get("point") or 0.01
            if direction == "buy":
                sl = price - sl_dist
                tp = price + tp_dist
            else:
                sl = price + sl_dist
                tp = price - tp_dist
            open_trade = {"dir": direction, "entry": price, "sl": sl, "tp": tp,
                          "bar": i, "rr": tp_dist / sl_dist if sl_dist else 1.5,
                          "sl_points": (sl_dist / point) if point else 1,
                          "spread_points": ind.get("spread_points", 0),
                          "session": session_of(datetime.fromtimestamp(int(rates[i]["timestamp"])).hour)}

        win_rate = round(wins / trades * 100, 1) if trades else 0.0
        profit_factor = round(gross_win_r / gross_loss_r, 2) if gross_loss_r else (gross_win_r or 0.0)
        avg_bars = round(bars_held_total / trades, 1) if trades else 0.0

        result = BacktestResult(
            label="+".join(strategy_names),
            symbol=symbol, timeframe=timeframe,
            bars_tested=n - val_start,
            trades=trades, wins=wins, losses=losses,
            win_rate=win_rate, profit_factor=profit_factor,
            total_r=round(cum_r, 2), avg_bars_held=avg_bars,
            max_drawdown_r=round(max_dd, 2),
            session_scores=session_scores,
        )
        logger.info(f"Backtest {result.label} {symbol} {timeframe}: "
                    f"{trades} trades, WR {win_rate}%, PF {profit_factor}, R {result.total_r}")
        return result

    def evaluate_promotion(
        self, symbol: str, strategy_names: list[str],
        min_trades: int = 20, min_win_rate: float = 50.0,
        min_profit_factor: float = 1.2, **kw,
    ) -> BacktestResult:
        """Run a backtest and decide if the combo is good enough to promote."""
        res = self.run_combo(symbol, strategy_names, **kw)
        if res is None:
            return BacktestResult(label="+".join(strategy_names), symbol=symbol,
                                  timeframe=kw.get("timeframe", "M15"), bars_tested=0,
                                  trades=0, wins=0, losses=0, win_rate=0, profit_factor=0,
                                  total_r=0, avg_bars_held=0, max_drawdown_r=0,
                                  passed=False, note="no data")
        res.passed = (res.trades >= min_trades and res.win_rate >= min_win_rate
                      and res.profit_factor >= min_profit_factor and res.total_r > 0)
        res.note = ("passed out-of-sample" if res.passed
                    else f"failed gate (trades>={min_trades}, WR>={min_win_rate}, "
                         f"PF>={min_profit_factor}, R>0)")
        return res
