#!/usr/bin/env bash
set -euo pipefail

TS=$(date +"%Y%m%d_%H%M%S")
OUT_DIR="data/diagnostics"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/static_checks_${TS}.txt"

echo "Running static checks... (this may take a minute)" | tee "$OUT"

# Ensure virtualenv/venv is active or use system python
PYTHON=${PYTHON:-python3}

if ! command -v flake8 >/dev/null 2>&1; then
  echo "flake8 not found; installing into user environment (pip install --user flake8)" | tee -a "$OUT"
  pip install --user flake8
fi
if ! command -v mypy >/dev/null 2>&1; then
  echo "mypy not found; installing into user environment (pip install --user mypy)" | tee -a "$OUT"
  pip install --user mypy
fi
if ! command -v bandit >/dev/null 2>&1; then
  echo "bandit not found; installing into user environment (pip install --user bandit)" | tee -a "$OUT"
  pip install --user bandit
fi

# Run linters; continue even if they fail
echo "\n---- flake8 ----" | tee -a "$OUT"
flake8 src --max-line-length=120 2>&1 | tee -a "$OUT" || true

echo "\n---- mypy (ignore missing imports) ----" | tee -a "$OUT"
mypy --ignore-missing-imports src 2>&1 | tee -a "$OUT" || true

echo "\n---- bandit ----" | tee -a "$OUT"
bandit -r src -lll 2>&1 | tee -a "$OUT" || true

# Save a short summary
echo "\nStatic checks complete. Output saved to $OUT"
