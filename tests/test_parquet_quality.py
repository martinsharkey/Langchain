"""Data-quality tests for qmmp parquet files."""
import sys, os
import glob
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import polars as pl


QMMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "qmmp")


def _find_parquets(pattern="**/*.parquet"):
    return glob.glob(os.path.join(QMMP_DIR, pattern), recursive=True)


def test_all_parquet_files_readable():
    files = _find_parquets()
    assert len(files) > 0, "No parquet files found in data/qmmp/"
    for f in files:
        df = pl.read_parquet(f)
        assert len(df) > 0, f"{f} is empty"


def test_ohlcv_parquet_schema():
    files = [f for f in _find_parquets("*/H1.parquet") if "features" not in f]
    if not files:
        pytest.skip("No H1.parquet files found")
    required = {"time", "open", "high", "low", "close", "volume"}
    for f in files[:3]:
        df = pl.read_parquet(f)
        missing = required - set(df.columns)
        assert not missing, f"{f} missing columns: {missing}"


def test_no_duplicate_timestamps():
    files = [f for f in _find_parquets("*/H1.parquet") if "features" not in f]
    if not files:
        pytest.skip("No H1.parquet files found")
    for f in files[:3]:
        df = pl.read_parquet(f)
        dup_count = df["time"].is_duplicated().sum()
        assert dup_count == 0, f"{f} has {dup_count} duplicate timestamps"


def test_no_nulls_in_ohlcv():
    files = [f for f in _find_parquets("*/H1.parquet") if "features" not in f]
    if not files:
        pytest.skip("No H1.parquet files found")
    for f in files[:3]:
        df = pl.read_parquet(f)
        for col in ("open", "high", "low", "close"):
            null_count = df[col].null_count()
            assert null_count == 0, f"{f} column {col} has {null_count} nulls"


def test_ohlc_validity():
    files = [f for f in _find_parquets("*/H1.parquet") if "features" not in f]
    if not files:
        pytest.skip("No H1.parquet files found")
    for f in files[:3]:
        df = pl.read_parquet(f)
        invalid_high = (df["high"] < df["low"]).sum()
        invalid_open = (df["open"] > df["high"]).sum() + (df["open"] < df["low"]).sum()
        invalid_close = (df["close"] > df["high"]).sum() + (df["close"] < df["low"]).sum()
        assert invalid_high == 0, f"{f} has {invalid_high} bars where high < low"
        assert invalid_open == 0, f"{f} has {invalid_open} bars where open outside high/low"
        assert invalid_close == 0, f"{f} has {invalid_close} bars where close outside high/low"


def test_time_is_utc():
    files = [f for f in _find_parquets("*/H1.parquet") if "features" not in f]
    if not files:
        pytest.skip("No H1.parquet files found")
    for f in files[:3]:
        df = pl.read_parquet(f)
        tz = df["time"].dtype
        tz_str = str(tz)
        assert "UTC" in tz_str or "Z" in tz_str, f"{f} time column timezone is {tz_str}, expected UTC"


def test_session_columns_are_boolean():
    files = [f for f in _find_parquets("*/H1.parquet") if "features" not in f]
    if not files:
        pytest.skip("No H1.parquet files found")
    session_cols = ("session_asia", "session_london", "session_ny")
    for f in files[:3]:
        df = pl.read_parquet(f)
        for col in session_cols:
            if col in df.columns:
                assert df[col].dtype == pl.Boolean, f"{f} column {col} is {df[col].dtype}, expected Boolean"


def test_weekend_bar_count_is_logged():
    files = [f for f in _find_parquets("*/H1.parquet") if "features" not in f]
    if not files:
        pytest.skip("No H1.parquet files found")
    for f in files[:3]:
        if "BTCUSD" in f or "GER40" in f:
            continue
        df = pl.read_parquet(f)
        weekends = df.filter(df["time"].dt.weekday() >= 5)
        print(f"{os.path.basename(f)}: {len(weekends)} weekend bars")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
