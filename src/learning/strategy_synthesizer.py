"""
StrategySynthesizer (L5) — turn a validated-intent hypothesis into a real,
runnable candidate strategy registered as status='testing'.

A synthesized strategy is a COMBINATION of existing strategy signal functions
(the hypothesis picks which to combine) plus an optional FILTER derived from the
reflection (e.g. only trade when adx<25, or avoid a session/regime). This is the
concrete mechanism behind "swap one indicator out, combine one or more, score
periods for poor entry" — expressed as composable strategy functions.

The candidate earns NO live ensemble weight until the Backtester passes it
(handled by the adaptive loop). Until then it is evaluated in `status='testing'`.
"""

from __future__ import annotations

from typing import Callable, Optional

from src.strategies.base import Signal
from src.utils.logger import get_logger

logger = get_logger("strategy_synthesizer")


def _parse_filter(filt: str) -> Callable[[dict], bool]:
    """
    Turn a simple filter string into a predicate(indicators)->bool (True = allow).
    Supported: 'adx<25', 'adx>25', 'rsi<70', 'avoid_session:late_ny',
    'avoid_regime:volatile'. Unknown -> always allow.
    """
    filt = (filt or "").strip().lower()
    if not filt:
        return lambda ind: True

    if filt.startswith("avoid_session:"):
        bad = filt.split(":", 1)[1]
        from src.learning.indicator_scorer import _session_of
        import datetime as _dt

        def pred(ind):
            # session unknown at signal time in backtest; allow (session gate is live-only)
            return True
        return pred

    if filt.startswith("avoid_regime:"):
        bad = filt.split(":", 1)[1]
        return lambda ind: (ind.get("regime") or "") != bad

    # numeric comparison like adx<25
    for op in ("<=", ">=", "<", ">"):
        if op in filt:
            key, val = filt.split(op, 1)
            key = key.strip(); 
            try:
                threshold = float(val.strip())
            except ValueError:
                return lambda ind: True

            def pred(ind, k=key, o=op, t=threshold):
                v = ind.get(k)
                if not isinstance(v, (int, float)):
                    return True
                if o == "<":
                    return v < t
                if o == ">":
                    return v > t
                if o == "<=":
                    return v <= t
                if o == ">=":
                    return v >= t
                return True
            return pred

    return lambda ind: True


def make_combined_strategy(
    registry, strategy_names: list[str], filter_str: str = "",
    min_agreement: int = 1,
) -> Callable[[dict, dict], Signal]:
    """
    Build a signal_fn that runs the named existing strategies, requires
    `min_agreement` to agree on a direction, and applies the optional filter.
    """
    fns = []
    for nm in strategy_names:
        sd = registry.get(nm)
        if sd:
            fns.append((nm, sd.signal_fn, sd.params))
    predicate = _parse_filter(filter_str)

    def signal_fn(indicators: dict, params: dict) -> Signal:
        if not predicate(indicators):
            return Signal(action="hold", reason="synth filter blocked", confidence=0.0)
        buys = sells = 0
        conf_sum = 0.0
        for nm, fn, p in fns:
            try:
                s = fn(indicators, p)
            except Exception:
                continue
            if s.action == "buy":
                buys += 1; conf_sum += s.confidence
            elif s.action == "sell":
                sells += 1; conf_sum += s.confidence
        close = indicators.get("close")
        if buys >= min_agreement and buys > sells:
            return Signal(action="buy", confidence=min(conf_sum / max(buys, 1), 1.0),
                          price=close, reason=f"synth buy ({buys} agree)")
        if sells >= min_agreement and sells > buys:
            return Signal(action="sell", confidence=min(conf_sum / max(sells, 1), 1.0),
                          price=close, reason=f"synth sell ({sells} agree)")
        return Signal(action="hold", reason="synth no agreement", confidence=0.0)

    return signal_fn


class StrategySynthesizer:
    def __init__(self, registry):
        self.registry = registry

    def synthesize(self, hypothesis: dict) -> Optional[str]:
        """
        Register a candidate strategy from a hypothesis dict
        (keys: id, symbol, strategies, filter). Returns the new strategy name or None.
        """
        strategies = hypothesis.get("strategies") or []
        if not strategies:
            logger.info("Synthesizer: hypothesis has no usable strategies")
            return None
        filt = hypothesis.get("filter") or ""
        hid = hypothesis.get("id", "x")
        name = f"SYNTH_{hid}_" + "_".join(s.split("_")[0][:4] for s in strategies[:3])
        if filt:
            name += "_" + filt.replace(":", "").replace("<", "lt").replace(">", "gt")[:10]
        name = name[:48]

        if self.registry.get(name):
            return name  # already exists

        min_agree = 1 if len(strategies) == 1 else max(1, len(strategies) - 1)
        fn = make_combined_strategy(self.registry, strategies, filt, min_agreement=min_agree)
        self.registry.register_custom(
            name=name, signal_fn=fn,
            description=f"Synthesized from hypothesis #{hid}: {strategies} filter='{filt}'",
            indicators_used=["close"], min_confidence=0.45, weight=1.0, status="testing",
        )
        logger.info(f"Synthesized candidate strategy '{name}' (status=testing)")
        return name
