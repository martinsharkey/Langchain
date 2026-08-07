"""
Canonical GoldShark optimiser column map — the SINGLE source of truth mapping our config
param names to the GoldShark/MT5 `Inp*` optimiser-report column aliases.

Both the evolutionary optimiser's seed model (evolutionary_optimizer._COLMAP / _seed_score)
and the researcher's evidence verdict (continual_researcher._optimiser_cluster) consume this
so they never drift and disagree on the exact evidence they are built to reconcile.

Each value is a TUPLE of accepted column-name aliases (different GoldShark EA versions used
different names); the first alias present in a report wins.
"""

# our_param -> (Inp column aliases, first-present wins)
GOLDSHARK_COLMAP = {
    "osma_min_long":    ("InpMinOsMALong", "InpLongOsMAMin"),
    "bulls_min_long":   ("InpMinBullsLong", "InpLongBullsMin"),
    "bears_min_long":   ("InpMaxBearsLong", "InpMinBearsLong"),
    "atr_min":          ("InpMinATR", "InpMinAtrValue"),
    "atr_max":          ("InpMaxATR",),
    "min_ema_slope":    ("InpMinEmaSlope",),
    "osma_max_short":   ("InpMaxOsMAShort",),
    "max_momentum_age": ("InpMaxMomentumAge",),
    "sl_atr":           ("InpSLATR",),
    "tp_rr":            ("InpTPRR",),
    "hard_sl_points":   ("InpHardStopLossPts",),
    "trail_points":     ("InpTrailBufferPts",),
}


def col_for(param: str, header) -> str:
    """Return the first alias column present in `header` for our `param`, or ''."""
    for c in GOLDSHARK_COLMAP.get(param, ()):
        if c in header:
            return c
    return ""


def value_for(param: str, row: dict, f):
    """Read our `param`'s value from a parsed pass `row` using the first alias present.
    `f` is the numeric coercion helper (parse_optimizer_report._f)."""
    for c in GOLDSHARK_COLMAP.get(param, ()):
        if c in row and row.get(c) not in ("", None):
            return f(row, c)
    return 0.0
