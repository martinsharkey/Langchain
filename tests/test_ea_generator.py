"""
Tests for scripts.qmmp.ea_generator (#89).

Covers:
- build_ea output structure (mq5, set, manifest)
- deterministic Magic number per symbol
- verify_ea pass/fail on mismatched inputs
- .set and .params.json consistency with model.json
- grouped input alignment
"""
import sys, os, json, re, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.config import magic_for_symbol
from scripts.qmmp.ea_generator import build_ea, verify_ea, write_ea


@pytest.fixture
def xau_model():
    return {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "build": 1,
        "entry": {"osma_params": {"fast": 12, "slow": 26, "signal": 9}},
        "floors": {
            "osma_mag": {"Asian": 10, "London": 20, "NewYork": 30},
            "ema_align": {"Asian": 5, "London": 10, "NewYork": 15},
            "bulls": {"Asian_Long": 20, "Asian_Short": -20, "London_Long": 30, "London_Short": -30, "NewYork_Long": 40, "NewYork_Short": -40},
            "bears": {"Asian_Long": -10, "Asian_Short": 10, "London_Long": -20, "London_Short": 20, "NewYork_Long": -30, "NewYork_Short": 30},
            "atr": {"Asian": 100, "London": 200, "NewYork": 300},
        },
        "exit": {"sl": 50000, "be": 5000, "be_lock": 500, "trail": 2000, "add": 2000, "early": 0.15, "max_legs": 4},
        "money_management": {"gbp_per_001": 50.0, "lot_cap_per_account": 100},
        "onboarded_at": "2026-08-19",
        "ea_version": "1.00",
    }


def test_build_ea_returns_mq5_set_and_manifest(xau_model):
    mq5, set_src, manifest = build_ea(xau_model)
    assert isinstance(mq5, str)
    assert "GoldShark_XAUUSD.mq5" in mq5 or "GoldShark_XAUUSD" in mq5
    assert isinstance(set_src, str)
    assert "GoldShark_XAUUSD.set" in set_src or "GoldShark" in set_src
    assert isinstance(manifest, dict)
    assert "Magic" in manifest
    assert "OsMA_Fast" in manifest
    assert "HardSL_pts" in manifest


def test_magic_is_deterministic(xau_model):
    _, _, manifest1 = build_ea(xau_model)
    _, _, manifest2 = build_ea(xau_model)
    assert manifest1["Magic"] == manifest2["Magic"]
    assert manifest1["Magic"] == magic_for_symbol("XAUUSD")


def test_verify_ea_passes_on_clean_generation(xau_model):
    with tempfile.TemporaryDirectory() as d:
        mq5_path = write_ea(xau_model, d)
        problems = verify_ea(xau_model, mq5_path)
        assert problems == [], f"verify failed: {problems}"


def test_verify_ea_detects_missing_input(xau_model):
    with tempfile.TemporaryDirectory() as d:
        mq5_path = write_ea(xau_model, d)
        src = open(mq5_path, encoding="utf-8").read()
        src = re.sub(r"^input\s+(?:int|double)\s+OsMA_Fast.*$", "", src, flags=re.M)
        with open(mq5_path, "w", encoding="utf-8") as f:
            f.write(src)
        problems = verify_ea(xau_model, mq5_path)
        assert any("OsMA_Fast" in p and "MISSING" in p for p in problems)


def test_verify_ea_detects_value_mismatch(xau_model):
    with tempfile.TemporaryDirectory() as d:
        mq5_path = write_ea(xau_model, d)
        src = open(mq5_path, encoding="utf-8").read()
        src = src.replace("input int    OsMA_Slow = 26;", "input int    OsMA_Slow = 99;")
        with open(mq5_path, "w", encoding="utf-8") as f:
            f.write(src)
        problems = verify_ea(xau_model, mq5_path)
        assert any("OsMA_Slow" in p and "!=" in p for p in problems)


def test_set_file_contains_all_inputs(xau_model):
    with tempfile.TemporaryDirectory() as d:
        mq5_path = write_ea(xau_model, d)
        set_path = mq5_path.replace(".mq5", ".set")
        set_src = open(set_path, encoding="utf-8").read()
        _, _, manifest = build_ea(xau_model)
        for name in manifest:
            assert name in set_src, f"{name} missing from .set file"


def test_params_json_matches_manifest(xau_model):
    with tempfile.TemporaryDirectory() as d:
        mq5_path = write_ea(xau_model, d)
        man_path = mq5_path.replace(".mq5", ".params.json")
        man = json.load(open(man_path, encoding="utf-8"))
        _, _, manifest = build_ea(xau_model)
        assert man == manifest


def test_input_groups_are_contiguous(xau_model):
    mq5, _, _ = build_ea(xau_model)
    groups = re.findall(r'input group "([^"]+)"', mq5)
    assert len(groups) == 7
    assert groups == ["Core / risk", "Session / time", "Entry / OsMA",
                      "Per-session strength floors (0 = OFF)", "Exit: basket trail + early pyramid",
                      "Money management", "Logging"]


def test_config_snapshot_is_deterministic(xau_model):
    mq5_1, _, _ = build_ea(xau_model)
    mq5_2, _, _ = build_ea(xau_model)
    assert mq5_1 == mq5_2


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
