"""
Backup / restore the bot's LEARNING + STATE that is NOT in git.

Everything the bot *learns* (experience DB, ChromaDB knowledge, hypotheses,
whale outcomes, ONNX models, edge weights, state json) is gitignored and lives
only on the machine it ran on. This tool snapshots all of it into a single
timestamped ZIP so the learning is portable and crash-safe.

Usage:
    python tools/backup_learning.py                 # ZIP -> data/backups/
    python tools/backup_learning.py --dest "G:\\My Drive\\LangchainBackups"
    python tools/backup_learning.py --lite          # skip big history/parquet
    python tools/backup_learning.py --include-secrets  # also .env + cryptorti creds/certs
    python tools/backup_learning.py --restore <zip>  # restore into the repo

The ZIP preserves relative paths, so unzipping at the repo root on another
machine (e.g. your laptop) drops every file back where the code expects it.
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Core learning/state that MUST travel (small, always included)
CORE = [
    "data/trading_experience.db",
    "data/hypotheses.db",
    "data/trading_knowledge.db",
    "data/whale_outcomes.db",
    "data/chromadb_store",       # RAG knowledge store (dir)
    "data/models",               # ONNX models (dir)
    "data/edge_weights.json",
    "data/cryptorti_correlation.json",
    "LEARNING_LOG.md",
    # runtime state (may or may not exist)
    "bot_status.json",
    "risk_state.json",
    "symbol_stats.json",
    "cryptorti_signals.json",
    "session_schedule.json",
]

# Large historical data (included unless --lite)
HEAVY = [
    "data/cryptorti_features",   # ~270MB parquet
    "data/goldshark_history",    # ~126MB xml/csv
    "data/whale_cache",
    "data/history_cache",
]

# Secrets (only with --include-secrets; needed to RUN, keep private!)
SECRETS = [
    ".env",
    "cryptorti/.env.cryptorti",
    "cryptorti/certs",
]


def _iter_files(rel):
    """Yield (abs_path, arcname) for a file or directory relative to REPO."""
    ap = os.path.join(REPO, rel)
    if os.path.isfile(ap):
        yield ap, rel.replace("\\", "/")
    elif os.path.isdir(ap):
        for root, _dirs, files in os.walk(ap):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, REPO).replace("\\", "/")
                yield full, arc


def backup(dest_dir: str, lite: bool, include_secrets: bool) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "lite" if lite else "full"
    if include_secrets:
        tag += "+secrets"
    out = os.path.join(dest_dir, f"langchain_learning_{tag}_{ts}.zip")

    items = list(CORE)
    if not lite:
        items += HEAVY
    if include_secrets:
        items += SECRETS

    n = 0
    total = 0
    missing = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in items:
            found = False
            for full, arc in _iter_files(rel):
                z.write(full, arc)
                n += 1
                total += os.path.getsize(full)
                found = True
            if not found:
                missing.append(rel)
    print(f"backup -> {out}")
    print(f"  {n} files, {total/1048576:.1f} MB uncompressed, "
          f"zip {os.path.getsize(out)/1048576:.1f} MB")
    if missing:
        print(f"  (not present, skipped: {', '.join(missing)})")
    return out


def _rotate(dest_dir: str, keep: int):
    """Keep only the newest `keep` backup zips in dest_dir."""
    try:
        zips = sorted(
            (os.path.join(dest_dir, f) for f in os.listdir(dest_dir)
             if f.startswith("langchain_learning_") and f.endswith(".zip")),
            key=os.path.getmtime, reverse=True,
        )
        for old in zips[max(0, keep):]:
            try:
                os.remove(old)
            except Exception:
                pass
    except Exception:
        pass


def run_auto_backup(dest_dir: str, keep: int = 8, lite: bool = True,
                    include_secrets: bool = False):
    """Periodic auto-backup entry for the engine. Lite by default (fast/small),
    rotates old zips, and never raises into the caller."""
    try:
        path = backup(dest_dir, lite=lite, include_secrets=include_secrets)
        _rotate(dest_dir, keep)
        return path
    except Exception as e:  # pragma: no cover
        print(f"auto-backup failed: {e}")
        return None


def restore(zip_path: str):
    if not os.path.exists(zip_path):
        print(f"ERROR: {zip_path} not found")
        return
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        print(f"restoring {len(names)} files into {REPO} ...")
        z.extractall(REPO)
    print("restore complete. Learning + state are back in place.")


def main():
    ap = argparse.ArgumentParser(description="Backup/restore bot learning (not in git)")
    ap.add_argument("--dest", default=os.path.join(REPO, "data", "backups"),
                    help="destination directory for the ZIP")
    ap.add_argument("--lite", action="store_true",
                    help="skip large history/parquet (core learning only, ~30MB)")
    ap.add_argument("--include-secrets", action="store_true",
                    help="also include .env + cryptorti creds/certs (PRIVATE)")
    ap.add_argument("--restore", metavar="ZIP", help="restore FROM this zip into the repo")
    args = ap.parse_args()

    if args.restore:
        restore(args.restore)
    else:
        backup(args.dest, args.lite, args.include_secrets)


if __name__ == "__main__":
    main()
