# Review Workspace

> This folder is the dedicated two-way review area for external review agents.
> It is NOT a parallel issue tracker; GitHub Issues remains the single source of
> truth. Use this folder to capture findings, recommendations, and roadmap updates
> before and while filing issues.

## Purpose

The review agent will:
1. Read the current architecture docs (`ARCHITECTURE_OVERVIEW.md`, `AGENTS.md`,
   `WORKSPACE_RULES.md`, `src/core_rules.py`).
2. Inspect the code changed in the 2026-08-19 session (issues #79-#86).
3. Record observations, risks, and concrete recommendations in
   `review/ISSUES_LOG.md`.
4. Open GitHub issues for anything that needs code changes, with a reference
   back to this folder.
5. Update `review/ROADMAP.md` as the living enhancement backlog.

## Scope of this review

The 2026-08-19 session delivered:
- `src/mt5/data.py` — `mt5_lock()` on `get_rates`/`get_ticks` (#79).
- `src/trading/scalp_engine.py` + `src/learning/adaptive_loop.py` — Dukascopy
  source wired into the adaptive backtester (#80).
- `scripts/qmmp/ea_generator.py` — redesigned EA with grouped inputs (#82),
  live `model.json` reload (#83), CSV lifecycle logging (#84).
- `docs/ea_pattern_audit.md` — patterns sampled from existing MQL5 EAs (#86).
- `docs/multi_symbol_architecture.md` — multi-symbol scaling design (#85).
- `ARCHITECTURE_OVERVIEW.md` and `AGENTS.md` updated to reflect the above.

Review focus areas:
- Correctness and thread safety of `mt5_lock()` usage.
- Whether Dukascopy-backed adaptive validation actually improves strategy promotion.
- EA generator maintainability, MT5 portability, and runtime reload reliability.
- Lifecycle logging coverage (what is missing at modify/close/BE events).
- Multi-symbol design readiness and operational gaps.
- Any drift between docs and code.

## Files in this folder

| File | Purpose |
|---|---|
| `README.md` | This file — process and scope. |
| `ISSUES_LOG.md` | Running log of review findings and their GitHub issue links. |
| `ROADMAP.md` | Living enhancement backlog, mapped to GitHub milestones/labels. |

## How to record a finding

1. Add an entry to `ISSUES_LOG.md` under the appropriate theme.
2. Assign a tentative severity: `critical`, `high`, `medium`, `low`, `note`.
3. If a code change is required, open a GitHub issue:
   - Title: concise summary.
   - Body: context, risk, proposed fix, affected files, acceptance criteria.
   - Label: choose from `bug`, `trading-safety`, `enhancement`, `learning`, `infra`, `review`.
   - Reference: link back to `review/ISSUES_LOG.md#finding-id`.
4. Update `ROADMAP.md` if the finding fits a planned theme.

## How the user will respond

- The user will read `ISSUES_LOG.md` and the linked GitHub issues.
- Accepted items will be prioritized in the next session and turned into code.
- Declined items will be marked `wontfix` with a short rationale in the log.
- The review agent should keep this folder updated as the conversation progresses.
