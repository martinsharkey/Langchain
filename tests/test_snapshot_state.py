"""
Tests for scripts/snapshot_state.py — Phase 1 of the safe-restart plan.
No MT5 or live data required; all state files are created in a temp directory.
"""
import sys, os, json, tempfile, shutil, hashlib, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path

import scripts.snapshot_state as ss


@pytest.fixture
def temp_data():
    d = tempfile.mkdtemp()
    (Path(d) / "config_checkpoints.json").write_text(json.dumps({"XAUUSD": {"best": {}}}))
    (Path(d) / "tuned_params.json").write_text(json.dumps({"XAUUSD": {"sl_atr": 0.8}}))
    (Path(d) / "graduation.json").write_text(json.dumps({"XAUUSD": "PROVING"}))
    (Path(d) / "symbol_evidence.json").write_text(json.dumps({"XAUUSD": {"n": 1}}))
    (Path(d) / "trading_experience.db").write_bytes(b"sqlite")
    (Path(d) / "bot_status.json").write_text(json.dumps({"running": True}))
    (Path(d) / "symbol_status.json").write_text(json.dumps({"XAUUSD": "ok"}))
    (Path(d) / "risk_state.json").write_text(json.dumps({"halted": False}))

    qmmp = Path(d) / "qmmp" / "XAUUSD"
    qmmp.mkdir(parents=True)
    (qmmp / "model.json").write_text(json.dumps({"symbol": "XAUUSD", "build": 1}))

    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_create_snapshot_copies_all_critical_files(temp_data):
    snap = ss.create_snapshot(data_dir=Path(temp_data))
    assert snap.exists()
    manifest = json.load(open(snap / "manifest.json", encoding="utf-8"))
    paths = {e["path"] for e in manifest["entries"]}
    expected = {
        "config_checkpoints.json",
        "tuned_params.json",
        "graduation.json",
        "symbol_evidence.json",
        "trading_experience.db",
        "bot_status.json",
        "symbol_status.json",
        "risk_state.json",
        "qmmp/XAUUSD/model.json",
    }
    assert expected <= paths


def test_restore_snapshot_updates_files(temp_data):
    data_dir = Path(temp_data)
    snap = ss.create_snapshot(data_dir=data_dir)

    # mutate live files
    (data_dir / "config_checkpoints.json").write_text(json.dumps({"XAUUSD": {"best": {"changed": True}}}))
    (data_dir / "tuned_params.json").write_text(json.dumps({"XAUUSD": {"sl_atr": 9.9}}))

    ss.restore_snapshot(snap, data_dir=data_dir)

    assert json.load(open(data_dir / "config_checkpoints.json")) == {"XAUUSD": {"best": {}}}
    assert json.load(open(data_dir / "tuned_params.json")) == {"XAUUSD": {"sl_atr": 0.8}}


def test_list_snapshots_newest_first(temp_data):
    data_dir = Path(temp_data)
    s1 = ss.create_snapshot(label="a", data_dir=data_dir)
    time.sleep(0.05)
    s2 = ss.create_snapshot(label="b", data_dir=data_dir)
    snaps = ss.list_snapshots(data_dir=data_dir)
    names = [s.name for s in snaps]
    assert s2.name in names
    assert s1.name in names
    assert names.index(s2.name) < names.index(s1.name)


def test_prune_keeps_n_newest(temp_data):
    # use a fresh data_dir subfolder so prior run snapshots don't interfere
    data_dir = Path(temp_data) / "prune_data"
    data_dir.mkdir()
    for f in ["config_checkpoints.json", "tuned_params.json"]:
        shutil.copy(Path(temp_data) / f, data_dir / f)
    created = [ss.create_snapshot(label=f"snap{i}", data_dir=data_dir).name for i in range(4)]
    time.sleep(0.05)
    deleted = ss.prune_snapshots(2, data_dir=data_dir)
    remaining = {s.name for s in ss.list_snapshots(data_dir=data_dir)}
    assert deleted == 2
    assert len(remaining) == 2
    assert remaining == set(created[-2:])


def test_verify_snapshot_detects_corruption(temp_data):
    data_dir = Path(temp_data)
    snap = ss.create_snapshot(data_dir=data_dir)
    assert ss.verify_snapshot(snap) is True
    # corrupt a file inside the snapshot
    (snap / "config_checkpoints.json").write_text("{}")
    assert ss.verify_snapshot(snap) is False


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
