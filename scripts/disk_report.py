#!/usr/bin/env python3
"""
Disk and DB diagnostic script for Langchain repo.
Run on the affected machine to produce a concise report of largest files,
directory sizes, and SQLite DB sizes so we can identify storage bloat.

Usage: python scripts/disk_report.py
Writes: data/diagnostics/disk_report_<timestamp>.txt
"""
from __future__ import annotations
import os
import sys
import time
import sqlite3
from pathlib import Path
from typing import List, Tuple

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
LOGS_DIR = BASE / "logs"
OUT_DIR = DATA_DIR / "diagnostics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TS = time.strftime("%Y%m%d_%H%M%S")
OUT_PATH = OUT_DIR / f"disk_report_{TS}.txt"

# Directories to inspect (relative to repo root)
TARGET_DIRS = [DATA_DIR, LOGS_DIR, BASE]


def sizeof_fmt(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024.0:
            return f"{num:3.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"


def get_dir_size(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                fp = Path(root) / f
                total += fp.stat().st_size
            except Exception:
                continue
    return total


def list_top_files(path: Path, top_n: int = 30) -> List[Tuple[int, str]]:
    files = []
    for root, dirs, filenames in os.walk(path, onerror=lambda e: None):
        for fname in filenames:
            try:
                fp = Path(root) / fname
                files.append((fp.stat().st_size, str(fp)))
            except Exception:
                continue
    files.sort(reverse=True)
    return files[:top_n]


def sqlite_size(path: Path) -> str:
    try:
        conn = sqlite3.connect(str(path))
        cur = conn.cursor()
        cur.execute("PRAGMA page_count;")
        page_count = cur.fetchone()[0]
        cur.execute("PRAGMA page_size;")
        page_size = cur.fetchone()[0]
        conn.close()
        size = page_count * page_size
        return sizeof_fmt(size)
    except Exception as e:
        return f"error: {e}"


def main():
    lines = []
    lines.append(f"DISK REPORT: {TS}")
    lines.append(f"BASE: {BASE}")
    lines.append("")

    # Directory sizes
    lines.append("-- DIRECTORY SIZES --")
    for d in TARGET_DIRS:
        try:
            if d.exists():
                sz = get_dir_size(d)
                lines.append(f"{d}: {sizeof_fmt(sz)} ({sz} bytes)")
            else:
                lines.append(f"{d}: MISSING")
        except Exception as e:
            lines.append(f"{d}: ERROR {e}")
    lines.append("")

    # Top files in data and logs
    for d in [DATA_DIR, LOGS_DIR]:
        lines.append(f"-- TOP FILES IN {d} --")
        if not d.exists():
            lines.append("  (dir missing)")
            lines.append("")
            continue
        tops = list_top_files(d, top_n=30)
        if not tops:
            lines.append("  (no files)")
        for sz, p in tops:
            lines.append(f"  {sizeof_fmt(sz):8} {p}")
        lines.append("")

    # SQLite DB sizes in data/
    lines.append("-- SQLITE DB SIZES (data/*.db) --")
    if DATA_DIR.exists():
        for db in DATA_DIR.glob("*.db"):
            try:
                lines.append(f"  {db.name}: {sqlite_size(db)}")
            except Exception as e:
                lines.append(f"  {db.name}: error {e}")
    else:
        lines.append("  data/ directory missing")
    lines.append("")

    # Count files
    lines.append("-- FILE COUNTS --")
    for d in [DATA_DIR, LOGS_DIR, BASE]:
        try:
            cnt = sum(1 for _ in d.rglob("*") if _.is_file()) if d.exists() else 0
            lines.append(f"  {d}: {cnt} files")
        except Exception as e:
            lines.append(f"  {d}: error {e}")
    lines.append("")

    # Suggest next steps
    lines.append("-- SUGGESTED NEXT STEPS --")
    lines.append("  - If any single file > 1GB, inspect it and consider archiving/compressing or deleting.")
    lines.append("  - If DB sizes are large, consider VACUUM (sqlite) and inspect tables with .tables/.schema.")
    lines.append("  - Run 'python scripts/disk_report.py' on the crashed machine and paste the generated report file here.")

    out = "\n".join(lines)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(out)
    print(out)
    print(f"\nSaved diagnostics to: {OUT_PATH}")


if __name__ == '__main__':
    main()
