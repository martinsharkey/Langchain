"""VectorBT-native indicator enumeration and wrapping.

This module uses VectorBT's out-of-the-box factory to enumerate and wrap
indicators from pandas_ta, ta-lib, and the ``ta`` library, plus VectorBT's own
built-ins. No custom compute layer, no hardcoded indicator list — VectorBT
decides what is available and how to run it.

Key VectorBT facilities used (see ``vectorbt.indicators.factory``):
  - ``IndicatorFactory.get_pandas_ta_indicators()``
  - ``IndicatorFactory.get_talib_indicators()``
  - ``IndicatorFactory.get_ta_indicators()``
  - ``IndicatorFactory.from_pandas_ta(name)``
  - ``IndicatorFactory.from_talib(name)``
  - ``IndicatorFactory.from_ta(name)``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# VectorBT built-in indicators (exposed directly on the vbt namespace).
VECTORBT_BUILTINS = ["ATR", "BBANDS", "MA", "MACD", "MSTD", "OBV", "RSI", "STOCH"]

# pandas_ta functions that VectorBT wraps but that are not standalone trading
# indicators (utility/run-length helpers). Excluded so they don't pollute the
# discovery universe.
_PANDAS_TA_EXCLUDE = {"LONG_RUN", "SHORT_RUN"}

# ta-lib functions that require a second input array (e.g. MAVP needs `periods`)
# and are not standalone single-symbol indicators.
_TALIB_EXCLUDE = {"MAVP"}

# ``ta`` library indicators that VectorBT wraps but that fail to run (e.g. output
# shape mismatch) — excluded from the discovery universe.
_TA_EXCLUDE = {"PSARIndicator"}

# Default parameters for ``ta`` library indicators whose VectorBT wrappers expose
# required parameters without defaults (e.g. ``window``). Supplied so the
# indicators run out of the box.
_TA_DEFAULT_PARAMS = {
    "ADXIndicator": {"window": 14},
    "AroonIndicator": {"window": 25},
    "AverageTrueRange": {"window": 14},
    "AwesomeOscillatorIndicator": {"window1": 5, "window2": 34},
    "BollingerBands": {"window": 20, "window_dev": 2},
    "CCIIndicator": {"window": 20, "constant": 0.015},
    "ChaikinMoneyFlowIndicator": {"window": 20},
    "DPOIndicator": {"window": 20},
    "DonchianChannel": {"window": 20, "offset": 0},
    "EMAIndicator": {"window": 20},
    "EaseOfMovementIndicator": {"window": 14},
    "ForceIndexIndicator": {"window": 13},
    "IchimokuIndicator": {"window1": 9, "window2": 26, "window3": 52, "visual": False},
    "KAMAIndicator": {"window": 10, "pow1": 2, "pow2": 30},
    "KSTIndicator": {"roc1": 10, "roc2": 15, "roc3": 20, "roc4": 30,
                     "window1": 10, "window2": 10, "window3": 10, "window4": 15, "nsig": 9},
    "KeltnerChannel": {"window": 20, "window_atr": 10, "original_version": True, "multiplier": 2},
    "MACD": {"window_slow": 26, "window_fast": 12, "window_sign": 9},
    "MFIIndicator": {"window": 14},
    "MassIndex": {"window_fast": 9, "window_slow": 25},
    "PercentagePriceOscillator": {"window_slow": 26, "window_fast": 12, "window_sign": 9},
    "PercentageVolumeOscillator": {"window_slow": 26, "window_fast": 12, "window_sign": 9},
    "ROCIndicator": {"window": 12},
    "RSIIndicator": {"window": 14},
    "SMAIndicator": {"window": 20},
    "STCIndicator": {"window_slow": 50, "window_fast": 23, "cycle": 10,
                     "smooth1": 3, "smooth2": 3},
    "StochRSIIndicator": {"window": 14, "smooth1": 3, "smooth2": 3},
    "StochasticOscillator": {"window": 14, "smooth_window": 3},
    "TRIXIndicator": {"window": 15},
    "TSIIndicator": {"window_slow": 25, "window_fast": 13},
    "UlcerIndex": {"window": 14},
    "UltimateOscillator": {"window1": 7, "window2": 14, "window3": 28,
                           "weight1": 4, "weight2": 2, "weight3": 1},
    "VolumeWeightedAveragePrice": {"window": 14},
    "VortexIndicator": {"window": 14},
    "WMAIndicator": {"window": 20},
    "WilliamsRIndicator": {"lbp": 14},
}


@dataclass
class Indicator:
    """A wrapped VectorBT indicator ready to run."""

    name: str
    library: str  # "pandas_ta" | "talib" | "ta" | "builtin"
    cls: type  # the generated VectorBT indicator class
    kwargs: Dict = field(default_factory=dict)  # default parameters for .run()


def _import_ta():
    """Import the optional ``ta`` library, or return None if unavailable."""
    try:
        import ta  # noqa: F401
        return ta
    except ImportError:
        return None


def enumerate_indicators() -> Dict[str, Set[str]]:
    """Enumerate all available indicators by library.

    Returns a dict mapping library name to a set of indicator names.
    """
    import vectorbt as vbt

    out: Dict[str, Set[str]] = {
        "builtin": set(VECTORBT_BUILTINS),
    }

    try:
        pta = vbt.IndicatorFactory.get_pandas_ta_indicators()
        out["pandas_ta"] = set(pta) - _PANDAS_TA_EXCLUDE
    except Exception as e:  # noqa: BLE001
        logger.warning(f"pandas_ta enumeration failed: {e}")
        out["pandas_ta"] = set()

    try:
        tal = vbt.IndicatorFactory.get_talib_indicators()
        out["talib"] = set(tal) - _TALIB_EXCLUDE
    except Exception as e:  # noqa: BLE001
        logger.warning(f"talib enumeration failed: {e}")
        out["talib"] = set()

    if _import_ta() is not None:
        try:
            out["ta"] = vbt.IndicatorFactory.get_ta_indicators() - _TA_EXCLUDE
        except Exception as e:  # noqa: BLE001
            logger.warning(f"ta enumeration failed: {e}")
            out["ta"] = set()
    else:
        out["ta"] = set()

    return out


def wrap(name: str, library: str) -> Indicator:
    """Wrap a single indicator into a VectorBT indicator class."""
    import vectorbt as vbt

    if library == "pandas_ta":
        cls = vbt.IndicatorFactory.from_pandas_ta(name)
    elif library == "talib":
        cls = vbt.IndicatorFactory.from_talib(name)
    elif library == "ta":
        cls = vbt.IndicatorFactory.from_ta(name)
    elif library == "builtin":
        cls = getattr(vbt, name)
    else:
        raise ValueError(f"Unknown library: {library}")

    # Provide default parameters for indicators that need them.
    kwargs: Dict = {}
    if library == "builtin":
        kwargs = _BUILTIN_DEFAULTS.get(name, {})
    elif library == "ta":
        kwargs = _TA_DEFAULT_PARAMS.get(name, {})

    return Indicator(name=name, library=library, cls=cls, kwargs=kwargs)


# Default parameters for VectorBT built-in indicators.
_BUILTIN_DEFAULTS = {
    "ATR": {"window": 14},
    "BBANDS": {"window": 20},
    "MA": {"window": 20},
    "MACD": {"fast": 12, "slow": 26},
    "MSTD": {"window": 20},
    "OBV": {},
    "RSI": {"window": 14},
    "STOCH": {},
}


def all_indicators() -> List[Indicator]:
    """Wrap every enumerated indicator into a runnable Indicator list."""
    result: List[Indicator] = []
    for library, names in enumerate_indicators().items():
        for name in sorted(names):
            try:
                result.append(wrap(name, library))
            except Exception as e:  # noqa: BLE001
                logger.debug(f"wrap {library}:{name} failed: {e}")
    return result


def run_indicator(
    ind: Indicator,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    volume: pd.Series,
    **params,
):
    """Run a wrapped indicator, passing only the inputs it declares.

    ``input_names`` on the generated class tells us exactly which OHLCV inputs
    the indicator needs (e.g. RSI needs only ``close``; AD needs
    ``high, low, close, volume``). We pass the matching inputs plus any
    parameter overrides.
    """
    inputs = {
        "close": close,
        "high": high,
        "low": low,
        "open": open_,
        "open_": open_,
        "volume": volume,
    }
    kwargs = {k: inputs[k] for k in ind.cls.input_names if k in inputs}
    # Apply default parameters for ``ta`` library indicators that require them.
    if ind.library == "ta":
        defaults = _TA_DEFAULT_PARAMS.get(ind.name, {})
        for k, v in defaults.items():
            kwargs.setdefault(k, v)
    kwargs.update(params)
    return ind.cls.run(**kwargs)


__all__ = [
    "Indicator",
    "VECTORBT_BUILTINS",
    "enumerate_indicators",
    "wrap",
    "all_indicators",
    "run_indicator",
]
