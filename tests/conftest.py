"""
pytest configuration for test isolation.

By default, every test runs against a temporary copy of `data/` so the live
proven-state stores are never mutated. Tests that genuinely need real MT5 or
live data must be marked with `@pytest.mark.live` and are skipped unless
`-m live` is passed.

Modules that cache `config.DATA_DIR`-derived paths at import time are
monkeypatched here so they point at the temp directory.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from src import config


def _copy_data_to_temp() -> Path:
    src = Path(config.DATA_DIR)
    tmp = Path(tempfile.mkdtemp(prefix="langchain_data_"))
    if src.exists():
        for item in src.iterdir():
            if item.name == "snapshots":
                continue
            dst = tmp / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)
    else:
        tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def _patch_cached_paths(data_dir: Path):
    """Monkeypatch module-level path constants that were cached at import time."""
    import src.learning.config_checkpointer as cp_mod
    import src.learning.param_optimizer as po_mod
    import src.trading.risk_manager as rm_mod
    import src.trading.scalp_engine as se_mod
    import src.trading.symbol_stats as ss_mod
    import src.cryptorti.signal_client as sc_mod
    import src.cryptorti.correlation_miner as cm_mod
    import src.learning.entry_strength as es_mod
    import src.learning.onboarding_tracker as ot_mod

    cp_mod.CHECKPOINT_PATH = str(data_dir / "config_checkpoints.json")
    po_mod.TUNED_PATH = str(data_dir / "tuned_params.json")
    rm_mod.STATE_PATH = str(data_dir / "risk_state.json")
    se_mod.STATUS_PATH = str(data_dir / "bot_status.json")
    ss_mod.STATS_PATH = str(data_dir / "symbol_stats.json")
    sc_mod.SIGNALS_PATH = str(data_dir / "cryptorti_signals.json")
    cm_mod.TABLE_PATH = str(data_dir / "cryptorti_correlation.json")
    es_mod.ENTRY_RELAX_PATH = str(data_dir / "entry_relax_caps.json")
    ot_mod.BASE_PATH = str(data_dir)


@pytest.fixture(scope="session", autouse=True)
def _auto_isolate_data():
    """Automatically redirect all cached paths to a temp copy of `data/`."""
    original_data_dir = config.DATA_DIR
    tmp = _copy_data_to_temp()
    config.DATA_DIR = str(tmp)
    _patch_cached_paths(tmp)
    yield tmp
    config.DATA_DIR = original_data_dir
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="session", autouse=False)
def isolated_data_dir():
    """Provide a temporary copy of `data/` and redirect all cached paths to it."""
    original_data_dir = config.DATA_DIR
    tmp = _copy_data_to_temp()
    try:
        config.DATA_DIR = str(tmp)
        _patch_cached_paths(tmp)
        yield tmp
    finally:
        config.DATA_DIR = original_data_dir
        shutil.rmtree(tmp, ignore_errors=True)


def pytest_configure(config):
    config.addinivalue_line("markers", "live: tests that require real MT5/live data")


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m") == "not live":
        skip_live = pytest.mark.skip(reason="need -m live to run")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)
