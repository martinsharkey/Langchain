# Minimal README addition for diagnostics

Added diagnostics scripts and CI workflow to help investigate storage/processing issues and run static checks.

Files added:
- scripts/disk_report.py     -> run on the affected machine to list largest files and DB sizes
- scripts/run_static_checks.sh -> runs flake8, mypy, bandit and writes outputs to data/diagnostics
- .github/workflows/static_checks.yml -> GitHub Actions workflow to run static checks on push/PR

Run 'python scripts/disk_report.py' on the crashed PC and paste the resulting file (data/diagnostics/disk_report_*.txt) here so I can continue the deep investigation.
