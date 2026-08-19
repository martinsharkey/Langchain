"""
snapshot_state.py — Phase 1 of the test-isolation + safe-restart plan.

Create and restore point-in-time snapshots of the live proven-state stores so
that risky operations (test runs, bot restarts, parameter experiments) can be
rolled back if something goes wrong.

Stores snapshotted:
  - data/config_checkpoints.json
  - data/tuned_params.json
  - data/graduation.json
  - data/symbol_evidence.json
  - data/trading_experience.db
  - data/bot_status.json
  - data/symbol_status.json
  - data/risk_state.json
  - data/qmmp/<SYM>/model.json for every onboarded symbol

CLI:
  python -m scripts.snapshot_state
      Create a new snapshot under data/snapshots/YYYY-MM-DD_HHMMSS/.

  python -m scripts.snapshot_state --list
      List existing snapshots newest-first.

  python -m scripts.snapshot_state --restore data/snapshots/YYYY-MM-DD_HHMMSS
      Atomically restore every file from the snapshot (write .tmp, then rename).

  python -m scripts.snapshot_state --prune 10
      Keep only the 10 newest snapshots and delete the rest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Insert project root so src.config is importable even when run as module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config


CRITICAL_FILES: List[str] = [
    "config_checkpoints.json",
    "tuned_params.json",
    "graduation.json",
    "symbol_evidence.json",
    "trading_experience.db",
    "bot_status.json",
    "symbol_status.json",
    "risk_state.json",
]

MANIFEST_NAME = "manifest.json"


def _data_dir() -> Path:
    return Path(getattr(config, "DATA_DIR", os.path.join(os.getcwd(), "data")))


def _snapshots_dir() -> Path:
    return _data_dir() / "snapshots"


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def _file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _discover_model_jsons(data_dir: Path) -> List[Path]:
    qmmp = data_dir / "qmmp"
    if not qmmp.exists():
        return []
    return sorted(qmmp.rglob("model.json"))


def create_snapshot(label: Optional[str] = None, data_dir: Optional[Path] = None) -> Path:
    """Snapshot critical files. Returns the snapshot directory path."""
    data_dir = data_dir or _data_dir()
    snapshots = (data_dir or _data_dir()) / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)

    name_parts = [_now_str()]
    if label:
        name_parts.append(label.replace(" ", "_"))
    snap_name = "_".join(name_parts)
    snap_dir = snapshots / snap_name
    snap_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for rel in CRITICAL_FILES:
        src = data_dir / rel
        if not src.exists():
            continue
        dst = snap_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        entries.append({
            "path": rel,
            "size": src.stat().st_size,
            "mtime": src.stat().st_mtime,
            "md5": _file_hash(src),
        })

    for model_path in _discover_model_jsons(data_dir):
        rel = model_path.relative_to(data_dir).as_posix()
        dst = snap_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_path, dst)
        entries.append({
            "path": rel,
            "size": model_path.stat().st_size,
            "mtime": model_path.stat().st_mtime,
            "md5": _file_hash(model_path),
        })

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": f"{os.path.basename(sys.argv[0])} snapshot_state",
        "data_dir": str(data_dir.resolve()),
        "label": label,
        "entries": entries,
    }
    manifest_path = snap_dir / MANIFEST_NAME
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    print(f"Snapshot created: {snap_dir}")
    print(f"  files: {len(entries)}")
    return snap_dir


def list_snapshots(data_dir: Optional[Path] = None) -> List[Path]:
    """Return existing snapshot directories newest-first."""
    snapshots = (data_dir or _data_dir()) / "snapshots"
    if not snapshots.exists():
        return []
    dirs = [p for p in snapshots.iterdir() if p.is_dir()]
    return sorted(dirs, key=lambda p: p.name, reverse=True)


def restore_snapshot(snap_dir: Path, data_dir: Optional[Path] = None) -> None:
    """Atomically restore files from a snapshot directory."""
    data_dir = data_dir or _data_dir()
    snap_dir = Path(snap_dir)
    manifest_path = snap_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(f"Snapshot manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    restored = 0
    for entry in manifest.get("entries", []):
        src = snap_dir / entry["path"]
        dst = data_dir / entry["path"]
        if not src.exists():
            print(f"  SKIP missing in snapshot: {entry['path']}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        restored += 1

    print(f"Restored {restored} files from {snap_dir} to {data_dir}")


def prune_snapshots(keep: int, data_dir: Optional[Path] = None) -> int:
    """Delete oldest snapshots, keeping `keep` newest. Returns number deleted."""
    snaps = list_snapshots(data_dir=data_dir)
    to_delete = snaps[keep:]
    for snap in to_delete:
        shutil.rmtree(snap, ignore_errors=True)
    print(f"Pruned {len(to_delete)} snapshots; kept {len(snaps) - len(to_delete)}")
    return len(to_delete)


def verify_snapshot(snap_dir: Path) -> bool:
    """Verify that files in snapshot match their recorded hashes."""
    snap_dir = Path(snap_dir)
    manifest_path = snap_dir / MANIFEST_NAME
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    ok = True
    for entry in manifest.get("entries", []):
        p = snap_dir / entry["path"]
        if not p.exists():
            print(f"  MISSING {entry['path']}")
            ok = False
            continue
        h = _file_hash(p)
        if h != entry.get("md5"):
            print(f"  HASH_MISMATCH {entry['path']}: expected {entry.get('md5')} got {h}")
            ok = False
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Snapshot and restore live proven-state stores."
    )
    ap.add_argument("--data-dir", type=Path, help="Override data directory")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="List snapshots")
    group.add_argument("--restore", type=Path, metavar="SNAPSHOT_DIR", help="Restore a snapshot")
    group.add_argument("--prune", type=int, metavar="N", help="Keep only N newest snapshots")
    group.add_argument("--verify", type=Path, metavar="SNAPSHOT_DIR", help="Verify snapshot integrity")
    ap.add_argument("--label", default=None, help="Optional label for the snapshot name")
    args = ap.parse_args(argv)

    data_dir = args.data_dir or _data_dir()

    if args.list:
        snaps = list_snapshots()
        if not snaps:
            print("No snapshots found.")
            return 0
        print("Snapshots (newest first):")
        for s in snaps:
            print(f"  {s.name}")
        return 0

    if args.restore:
        restore_snapshot(args.restore, data_dir)
        return 0

    if args.prune is not None:
        if args.prune < 1:
            ap.error("--prune must be >= 1")
        prune_snapshots(args.prune)
        return 0

    if args.verify:
        ok = verify_snapshot(args.verify)
        print("Snapshot OK" if ok else "Snapshot FAILED verification")
        return 0 if ok else 1

    snap = create_snapshot(label=args.label, data_dir=data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
