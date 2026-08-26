"""Signal generation using VectorBT's native signal methods.

VectorBT's generated indicator classes expose comparison and combination methods
out of the box (``.above()``, ``.below()``, ``.crossed_above()``, ``.crossed_below()``,
``&``, ``|``). This module maps an indicator's outputs to entry/exit signals using
those native methods — no hand-written oscillator/band/crossover logic.

The signal convention is category-driven:
  - oscillator: value below low -> entry, above high -> exit
  - band:       close below lower band -> entry, above upper band -> exit
  - crossover:  fast crosses above slow -> entry, below -> exit
  - trend:      close crosses above MA -> entry, below -> exit
  - volume:     value crosses above its own lag -> entry, below -> exit
  - generic:    value crosses above its rolling mean -> entry, below -> exit

Each generator returns (entries, exits) as pandas Series (VectorBT-native), which
can be combined with ``&`` / ``|`` and passed directly to
``vbt.Portfolio.from_signals``.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _first_output(ind) -> pd.Series:
    """Return the first output of a run indicator as a pandas Series."""
    for name in ind.output_names:
        try:
            return getattr(ind, name)
        except Exception:
            continue
    raise ValueError("indicator has no outputs")


def _oscillator(ind, low, high, key=None):
    """value < low -> entry, value > high -> exit (native .below/.above)."""
    v = _first_output(ind) if key is None else getattr(ind, key)
    return v.vbt.below(low), v.vbt.above(high)


def _band(ind, lower_key, upper_key):
    """close < lower band -> entry, close > upper band -> exit (native)."""
    lower = getattr(ind, lower_key)
    upper = getattr(ind, upper_key)
    return ind.close.vbt.below(lower), ind.close.vbt.above(upper)


def _crossover(ind, fast_key, slow_key):
    """fast crosses above slow -> entry, below -> exit (native)."""
    fast = getattr(ind, fast_key)
    slow = getattr(ind, slow_key)
    return fast.vbt.crossed_above(slow), fast.vbt.crossed_below(slow)


def _trend(ind, ma_key):
    """close crosses above MA -> entry, below -> exit (native)."""
    ma = getattr(ind, ma_key)
    return ind.close.vbt.crossed_above(ma), ind.close.vbt.crossed_below(ma)


def _volume(ind, key=None):
    """value crosses above its own lag -> entry, below -> exit (native)."""
    v = _first_output(ind) if key is None else getattr(ind, key)
    lag = v.shift(1)
    return v.vbt.crossed_above(lag), v.vbt.crossed_below(lag)


def _generic(ind):
    """value crosses above its rolling mean -> entry, below -> exit (native)."""
    v = _first_output(ind)
    mean = v.rolling(20, min_periods=5).mean()
    return v.vbt.crossed_above(mean), v.vbt.crossed_below(mean)


# Curated specs: (library, name) -> callable(ind) -> (entries, exits).
# Output keys are the VectorBT output_names (lowercase for pandas_ta, e.g.
# 'rsi', 'bbl', 'bbu', 'macd', 'macds').
_CURATED: Dict[Tuple[str, str], callable] = {
    # pandas_ta oscillators
    ("pandas_ta", "RSI"): lambda i: _oscillator(i, 30, 70, "rsi"),
    ("pandas_ta", "STOCH"): lambda i: _oscillator(i, 20, 80, "stochk"),
    ("pandas_ta", "STOCHRSI"): lambda i: _oscillator(i, 20, 80, "stochrsi_k"),
    ("pandas_ta", "CCI"): lambda i: _oscillator(i, -100, 100, "cci"),
    ("pandas_ta", "WILLR"): lambda i: _oscillator(i, -80, -20, "willr"),
    ("pandas_ta", "CMO"): lambda i: _oscillator(i, -50, 50, "cmo"),
    ("pandas_ta", "MFI"): lambda i: _oscillator(i, 20, 80, "mfi"),
    ("pandas_ta", "UO"): lambda i: _oscillator(i, 40, 60, "uo"),
    ("pandas_ta", "KST"): lambda i: _oscillator(i, -1, 1, "kst"),
    ("pandas_ta", "TSI"): lambda i: _oscillator(i, -25, 25, "tsi"),
    ("pandas_ta", "ROC"): lambda i: _oscillator(i, -5, 5, "roc"),
    ("pandas_ta", "MOM"): lambda i: _oscillator(i, -5, 5, "mom"),
    ("pandas_ta", "PPO"): lambda i: _oscillator(i, -1, 1, "ppo"),
    ("pandas_ta", "APO"): lambda i: _oscillator(i, -1, 1, "apo"),
    ("pandas_ta", "BIAS"): lambda i: _oscillator(i, -5, 5, "bias"),
    ("pandas_ta", "BOP"): lambda i: _oscillator(i, -0.5, 0.5, "bop"),
    ("pandas_ta", "CFO"): lambda i: _oscillator(i, -5, 5, "cfo"),
    ("pandas_ta", "CG"): lambda i: _oscillator(i, -10000, 10000, "cg"),
    ("pandas_ta", "COPPOCK"): lambda i: _oscillator(i, 0, 0, "coppock"),
    ("pandas_ta", "CTI"): lambda i: _oscillator(i, -0.9, 0.9, "cti"),
    ("pandas_ta", "ER"): lambda i: _oscillator(i, 0.2, 0.8, "er"),
    ("pandas_ta", "FISHER"): lambda i: _oscillator(i, -1, 1, "fishert"),
    ("pandas_ta", "INERTIA"): lambda i: _oscillator(i, 20, 80, "inertia"),
    ("pandas_ta", "KDJ"): lambda i: _oscillator(i, 20, 80, "k"),
    ("pandas_ta", "PGO"): lambda i: _oscillator(i, -1, 1, "pgo"),
    ("pandas_ta", "PSL"): lambda i: _oscillator(i, -1, 1, "psl"),
    ("pandas_ta", "QQE"): lambda i: _oscillator(i, 20, 80, "qqe"),
    ("pandas_ta", "RSX"): lambda i: _oscillator(i, 30, 70, "rsx"),
    ("pandas_ta", "RVGI"): lambda i: _oscillator(i, -8, 8, "rvgi"),
    ("pandas_ta", "RVI"): lambda i: _oscillator(i, 40, 60, "rvi"),
    ("pandas_ta", "SLOPE"): lambda i: _oscillator(i, -0.1, 0.1, "slope"),
    ("pandas_ta", "SMI"): lambda i: _oscillator(i, -40, 40, "smi"),
    ("pandas_ta", "SQUEEZE"): lambda i: _oscillator(i, -0.5, 0.5, "sqz"),
    ("pandas_ta", "STC"): lambda i: _oscillator(i, 25, 75, "stc"),
    ("pandas_ta", "TMO"): lambda i: _oscillator(i, -5, 5, "tmo"),
    ("pandas_ta", "TRIX"): lambda i: _oscillator(i, -0.5, 0.5, "trix"),
    ("pandas_ta", "VHF"): lambda i: _oscillator(i, 0.2, 0.8, "vhf"),
    ("pandas_ta", "VORTEX"): lambda i: _oscillator(i, 0.8, 1.2, "vtxp"),
    ("pandas_ta", "ZSCORE"): lambda i: _oscillator(i, -1, 1, "zs"),
    # pandas_ta bands
    ("pandas_ta", "BBANDS"): lambda i: _band(i, "bbl", "bbu"),
    ("pandas_ta", "KC"): lambda i: _band(i, "kcl", "kcu"),
    ("pandas_ta", "DONCHIAN"): lambda i: _band(i, "dcl", "dcu"),
    ("pandas_ta", "ACCBANDS"): lambda i: _band(i, "accbands_l", "accbands_u"),
    ("pandas_ta", "ABERRATION"): lambda i: _band(i, "aberration_l", "aberration_u"),
    ("pandas_ta", "CHANDELIER_EXIT"): lambda i: _band(i, "chdlrextl", "chdlrexts"),
    ("pandas_ta", "HWC"): lambda i: _band(i, "hwl", "hwu"),
    # pandas_ta crossovers
    ("pandas_ta", "MACD"): lambda i: _crossover(i, "macd", "macds"),
    ("pandas_ta", "ADOSC"): lambda i: _crossover(i, "adosc", "adosc_signal"),
    ("pandas_ta", "AROON"): lambda i: _crossover(i, "aroonu", "aroond"),
    # pandas_ta trend
    ("pandas_ta", "SMA"): lambda i: _trend(i, "sma"),
    ("pandas_ta", "EMA"): lambda i: _trend(i, "ema"),
    ("pandas_ta", "WMA"): lambda i: _trend(i, "wma"),
    ("pandas_ta", "DEMA"): lambda i: _trend(i, "dema"),
    ("pandas_ta", "TEMA"): lambda i: _trend(i, "tema"),
    ("pandas_ta", "TRIMA"): lambda i: _trend(i, "trima"),
    ("pandas_ta", "HMA"): lambda i: _trend(i, "hma"),
    ("pandas_ta", "KAMA"): lambda i: _trend(i, "kama"),
    ("pandas_ta", "ALMA"): lambda i: _trend(i, "alma"),
    ("pandas_ta", "FWMA"): lambda i: _trend(i, "fwma"),
    ("pandas_ta", "HWMA"): lambda i: _trend(i, "hwma"),
    ("pandas_ta", "JMA"): lambda i: _trend(i, "jma"),
    ("pandas_ta", "LINREG"): lambda i: _trend(i, "linreg"),
    ("pandas_ta", "MCGD"): lambda i: _trend(i, "mcgd"),
    ("pandas_ta", "MIDPOINT"): lambda i: _trend(i, "midpoint"),
    ("pandas_ta", "MIDPRICE"): lambda i: _trend(i, "midprice"),
    ("pandas_ta", "PWMA"): lambda i: _trend(i, "pwma"),
    ("pandas_ta", "RMA"): lambda i: _trend(i, "rma"),
    ("pandas_ta", "SINWMA"): lambda i: _trend(i, "sinwma"),
    ("pandas_ta", "SMMA"): lambda i: _trend(i, "smma"),
    ("pandas_ta", "SSF"): lambda i: _trend(i, "ssf"),
    ("pandas_ta", "SSF3"): lambda i: _trend(i, "ssf3"),
    ("pandas_ta", "SWMA"): lambda i: _trend(i, "swma"),
    ("pandas_ta", "T3"): lambda i: _trend(i, "t3"),
    ("pandas_ta", "VIDYA"): lambda i: _trend(i, "vidya"),
    ("pandas_ta", "VWMA"): lambda i: _trend(i, "vwma"),
    ("pandas_ta", "ZLMA"): lambda i: _trend(i, "zl"),
    ("pandas_ta", "SUPERTREND"): lambda i: _trend(i, "supert"),
    ("pandas_ta", "PSAR"): lambda i: _trend(i, "psarl"),
    ("pandas_ta", "TTM_TREND"): lambda i: _trend(i, "ttm_trnd"),
    ("pandas_ta", "TRENDFLEX"): lambda i: _trend(i, "trendflex"),
    ("pandas_ta", "ALPHATREND"): lambda i: _trend(i, "alphat"),
    ("pandas_ta", "AMAT"): lambda i: _trend(i, "amate_lr"),
    ("pandas_ta", "DECAY"): lambda i: _trend(i, "ldecay"),
    ("pandas_ta", "HT_TRENDLINE"): lambda i: _trend(i, "ht_tl"),
    ("pandas_ta", "ZIGZAG"): lambda i: _trend(i, "zigzags"),
    ("pandas_ta", "VWAP"): lambda i: _trend(i, "vwap"),
    # pandas_ta volume
    ("pandas_ta", "OBV"): lambda i: _volume(i, "obv"),
    ("pandas_ta", "AD"): lambda i: _volume(i, "ado"),
    ("pandas_ta", "CMF"): lambda i: _volume(i, "cmf"),
    ("pandas_ta", "EFI"): lambda i: _volume(i, "efi"),
    ("pandas_ta", "EOM"): lambda i: _volume(i, "eom"),
    ("pandas_ta", "KVO"): lambda i: _volume(i, "kvo"),
    ("pandas_ta", "NVI"): lambda i: _volume(i, "nvi"),
    ("pandas_ta", "PVI"): lambda i: _volume(i, "pvi"),
    ("pandas_ta", "PVO"): lambda i: _volume(i, "pvo"),
    ("pandas_ta", "PVOL"): lambda i: _volume(i, "pvol"),
    ("pandas_ta", "PVR"): lambda i: _volume(i, "pvr"),
    ("pandas_ta", "PVT"): lambda i: _volume(i, "pvt"),
    ("pandas_ta", "TSV"): lambda i: _volume(i, "tsv"),
    ("pandas_ta", "VHM"): lambda i: _volume(i, "vhm"),
    ("pandas_ta", "VP"): lambda i: _volume(i, "vp"),
    ("pandas_ta", "AOBV"): lambda i: _volume(i, "obv"),
    # talib oscillators
    ("talib", "RSI"): lambda i: _oscillator(i, 30, 70, "rsi"),
    ("talib", "STOCH"): lambda i: _oscillator(i, 20, 80, "slowk"),
    ("talib", "STOCHF"): lambda i: _oscillator(i, 20, 80, "fastk"),
    ("talib", "STOCHRSI"): lambda i: _oscillator(i, 20, 80, "fastk"),
    ("talib", "CCI"): lambda i: _oscillator(i, -100, 100, "cci"),
    ("talib", "WILLR"): lambda i: _oscillator(i, -80, -20, "willr"),
    ("talib", "CMO"): lambda i: _oscillator(i, -50, 50, "cmo"),
    ("talib", "MFI"): lambda i: _oscillator(i, 20, 80, "mfi"),
    ("talib", "ULTOSC"): lambda i: _oscillator(i, 40, 60, "ultosc"),
    ("talib", "ROC"): lambda i: _oscillator(i, -5, 5, "roc"),
    ("talib", "ROCP"): lambda i: _oscillator(i, -5, 5, "rocp"),
    ("talib", "MOM"): lambda i: _oscillator(i, -5, 5, "mom"),
    ("talib", "PPO"): lambda i: _oscillator(i, -1, 1, "ppo"),
    ("talib", "APO"): lambda i: _oscillator(i, -1, 1, "apo"),
    ("talib", "TRIX"): lambda i: _oscillator(i, -0.5, 0.5, "trix"),
    ("talib", "ADX"): lambda i: _oscillator(i, 20, 40, "adx"),
    ("talib", "ADXR"): lambda i: _oscillator(i, 20, 40, "adxr"),
    ("talib", "DX"): lambda i: _oscillator(i, 20, 40, "dx"),
    ("talib", "AROONOSC"): lambda i: _oscillator(i, -50, 50, "aroonosc"),
    ("talib", "BOP"): lambda i: _oscillator(i, -0.5, 0.5, "bop"),
    # talib bands
    ("talib", "BBANDS"): lambda i: _band(i, "lowerband", "upperband"),
    # talib crossovers
    ("talib", "MACD"): lambda i: _crossover(i, "macd", "macdsignal"),
    # talib trend
    ("talib", "SMA"): lambda i: _trend(i, "sma"),
    ("talib", "EMA"): lambda i: _trend(i, "ema"),
    ("talib", "WMA"): lambda i: _trend(i, "wma"),
    ("talib", "DEMA"): lambda i: _trend(i, "dema"),
    ("talib", "TEMA"): lambda i: _trend(i, "tema"),
    ("talib", "TRIMA"): lambda i: _trend(i, "trima"),
    ("talib", "KAMA"): lambda i: _trend(i, "kama"),
    ("talib", "T3"): lambda i: _trend(i, "t3"),
    ("talib", "MIDPOINT"): lambda i: _trend(i, "midpoint"),
    ("talib", "MIDPRICE"): lambda i: _trend(i, "midprice"),
    ("talib", "SAR"): lambda i: _trend(i, "sar"),
    ("talib", "HT_TRENDLINE"): lambda i: _trend(i, "ht_trendline"),
    ("talib", "LINEARREG"): lambda i: _trend(i, "linearreg"),
    ("talib", "TSF"): lambda i: _trend(i, "tsf"),
    # talib volume
    ("talib", "OBV"): lambda i: _volume(i, "obv"),
    ("talib", "AD"): lambda i: _volume(i, "ad"),
    ("talib", "ADOSC"): lambda i: _volume(i, "adosc"),
    # builtin
    ("builtin", "RSI"): lambda i: _oscillator(i, 30, 70, "rsi"),
    ("builtin", "BBANDS"): lambda i: _band(i, "lower", "upper"),
    ("builtin", "MACD"): lambda i: _crossover(i, "macd", "signal"),
    ("builtin", "MA"): lambda i: _trend(i, "ma"),
    ("builtin", "ATR"): lambda i: _oscillator(i, 0.5, 1.5, "atr"),
    ("builtin", "MSTD"): lambda i: _oscillator(i, 0.5, 1.5, "mstd"),
    ("builtin", "OBV"): lambda i: _volume(i, "obv"),
    ("builtin", "STOCH"): lambda i: _oscillator(i, 20, 80, "percent_k"),
    # ta library
    ("ta", "RSIIndicator"): lambda i: _oscillator(i, 30, 70, "rsi"),
    ("ta", "StochasticOscillator"): lambda i: _oscillator(i, 20, 80, "stoch"),
    ("ta", "StochRSIIndicator"): lambda i: _oscillator(i, 20, 80, "stochrsi_k"),
    ("ta", "CCIIndicator"): lambda i: _oscillator(i, -100, 100, "cci"),
    ("ta", "WilliamsRIndicator"): lambda i: _oscillator(i, -80, -20, "williams_r"),
    ("ta", "MFIIndicator"): lambda i: _oscillator(i, 20, 80, "money_flow_index"),
    ("ta", "UltimateOscillator"): lambda i: _oscillator(i, 40, 60, "ultimate_oscillator"),
    ("ta", "ROCIndicator"): lambda i: _oscillator(i, -5, 5, "roc"),
    ("ta", "PercentagePriceOscillator"): lambda i: _oscillator(i, -1, 1, "ppo"),
    ("ta", "TRIXIndicator"): lambda i: _oscillator(i, -0.5, 0.5, "trix"),
    ("ta", "ADXIndicator"): lambda i: _oscillator(i, 20, 40, "adx"),
    ("ta", "AroonIndicator"): lambda i: _crossover(i, "aroon_up", "aroon_down"),
    ("ta", "BollingerBands"): lambda i: _band(i, "bollinger_lband", "bollinger_hband"),
    ("ta", "KeltnerChannel"): lambda i: _band(i, "keltner_channel_lband", "keltner_channel_hband"),
    ("ta", "DonchianChannel"): lambda i: _band(i, "donchian_channel_lband", "donchian_channel_hband"),
    ("ta", "MACD"): lambda i: _crossover(i, "macd", "macd_signal"),
    ("ta", "SMAIndicator"): lambda i: _trend(i, "sma_indicator"),
    ("ta", "EMAIndicator"): lambda i: _trend(i, "ema_indicator"),
    ("ta", "WMAIndicator"): lambda i: _trend(i, "wma"),
    ("ta", "KAMAIndicator"): lambda i: _trend(i, "kama"),
    ("ta", "IchimokuIndicator"): lambda i: _trend(i, "ichimoku_a"),
    ("ta", "OnBalanceVolumeIndicator"): lambda i: _volume(i, "on_balance_volume"),
    ("ta", "AccDistIndexIndicator"): lambda i: _volume(i, "acc_dist_index"),
    ("ta", "ChaikinMoneyFlowIndicator"): lambda i: _volume(i, "chaikin_money_flow"),
    ("ta", "EaseOfMovementIndicator"): lambda i: _volume(i, "ease_of_movement"),
    ("ta", "ForceIndexIndicator"): lambda i: _volume(i, "force_index"),
    ("ta", "NegativeVolumeIndexIndicator"): lambda i: _volume(i, "negative_volume_index"),
    ("ta", "VolumePriceTrendIndicator"): lambda i: _volume(i, "volume_price_trend"),
    ("ta", "VolumeWeightedAveragePrice"): lambda i: _trend(i, "volume_weighted_average_price"),
    ("ta", "VortexIndicator"): lambda i: _oscillator(i, 0.8, 1.2, "vortex_indicator_pos"),
    ("ta", "AwesomeOscillatorIndicator"): lambda i: _oscillator(i, 0, 0, "awesome_oscillator"),
    ("ta", "KSTIndicator"): lambda i: _oscillator(i, -1, 1, "kst"),
    ("ta", "TSIIndicator"): lambda i: _oscillator(i, -25, 25, "tsi"),
    ("ta", "STCIndicator"): lambda i: _oscillator(i, 25, 75, "stc"),
    ("ta", "DPOIndicator"): lambda i: _oscillator(i, -5, 5, "dpo"),
    ("ta", "MassIndex"): lambda i: _oscillator(i, 25, 27, "mass_index"),
    ("ta", "UlcerIndex"): lambda i: _oscillator(i, 0.5, 1.5, "ulcer_index"),
    ("ta", "CumulativeReturnIndicator"): lambda i: _volume(i, "cumulative_return"),
    ("ta", "DailyReturnIndicator"): lambda i: _volume(i, "daily_return"),
    ("ta", "DailyLogReturnIndicator"): lambda i: _volume(i, "daily_log_return"),
}


def generate_signals(ind, library: str, name: str) -> Tuple[pd.Series, pd.Series]:
    """Generate (entries, exits) for a run indicator using native methods.

    Uses a curated spec when available, otherwise a generic mean-reversion
    signal on the first output. Returns pandas Series (VectorBT-native).
    """
    key = (library, name)
    if key in _CURATED:
        try:
            return _CURATED[key](ind)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"curated signal {library}:{name} failed ({e}); using generic")
    return _generic(ind)


def combine_signals(
    entries_list: List[pd.Series],
    exits_list: List[pd.Series],
    mode: str = "and",
) -> Tuple[pd.Series, pd.Series]:
    """Combine multiple entry/exit signal Series with AND or OR logic.

    Uses VectorBT-native ``&`` / ``|`` operators.
    """
    if not entries_list:
        return pd.Series(dtype=bool), pd.Series(dtype=bool)

    entries = entries_list[0]
    exits = exits_list[0]
    for e, x in zip(entries_list[1:], exits_list[1:]):
        if mode == "and":
            entries = entries & e
            exits = exits & x
        else:
            entries = entries | e
            exits = exits | x
    return entries, exits


__all__ = ["generate_signals", "combine_signals"]
