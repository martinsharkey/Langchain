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
from typing import Optional, Callable

from src.mt5.data import get_rates
from src.strategies.indicators import compute_indicator_series
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
    total_r: float          # sum of R multiples (reward/risk units)
    avg_bars_held: float
    max_drawdown_r: float
    passed: bool = False
    note: str = ""


class Backtester:
    def __init__(self, registry):
        self.registry = registry

    def _load_history(self, symbol: str, timeframe: str, bars: int) -> list[dict]:
        # MT5 copy_rates_from_pos caps around ~ tens of thousands; request in one call.
        rates = get_rates(symbol, timeframe=timeframe, count=bars)
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

        open_trade = None  # dict: dir, entry, sl, tp, bar

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
                          "spread_points": ind.get("spread_points", 0)}

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
