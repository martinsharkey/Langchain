# Workspace Rules

> **Authority:** This file governs how every session, commit, test run, and
> deployment behaves in this repo. `AGENTS.md` is the signpost; this file is
> the rulebook. When they conflict, this file wins. When this file is silent,
> defer to `src/core_rules.py` for trading-system rules.

## 0. New Agent Orientation (MANDATORY)

Any agent new to this workspace MUST read the following files **before**
modifying code or making decisions:
1. `AGENTS.md` — project state, current focus, ground rules
2. `WORKSPACE_RULES.md` — this file (session hygiene, commit discipline, etc.)
3. `ARCHITECTURE.md` — current built state, component map, data flow
4. `ARCHITECTURE_OVERVIEW.md` — high-level system map and cycle diagram
5. `src/core_rules.py` — the enforced trading-system rules (R1–R10)

These are the five-file minimum orientation. Skipping them is a violation of
this workspace's onboarding protocol.

---

## 1. Session Continuity & History

### 1.1 Mandatory Session Log
Every session MUST end with an entry appended to `SESSION_LOG.md`.
The entry MUST contain:
- **Date, time, and branch name**
- **Goal** — what this session set out to do
- **Actions taken** — bullets with rationale
- **Outcomes** — what changed, what was fixed, what was built
- **Current state** — bot status, balance, open issues, next steps
- **Commit hashes** — every commit made this session

Format template:
```markdown
## Session YYYY-MM-DD — <short goal>
**Branch:** <branch>
**Mode:** <TRADING_MODE>
**Status:** <brief status>

### What we did
- <action> — <rationale> — <outcome>

### What changed
- Files: <list>
- Commits: <hash list>

### Current state
- <bot status, key metrics>

### Next
- <next steps>
```

### 1.2 Session Context Summary
For sessions that implement significant new architecture or make key decisions,
also update `SESSION_CONTEXT_SUMMARY.md` (root of `Documents/Langchain/`) with:
- What was decided
- Why
- What to do next
- Key files to review

### 1.3 Todo Log
- `TODO.md` is the **historical mirror only**.
- The **live task list** is always GitHub Issues (`gh issue list`).
- Before starting any work: run `gh issue list` and read the backlog.
- When a new bug/feature/idea is discovered: open a GitHub issue immediately.
- Reference issues in every commit (`fix(#12): ...`, `feat(#7): ...`).
- Close issues via PR/commit keywords or manually after merge.

### 1.4 State Recovery
If chat history is lost, recover context from:
1. `AGENTS.md` — project state and current focus
2. `SESSION_LOG.md` — recent build history
3. `SESSION_CONTEXT_SUMMARY.md` — latest architectural decisions
4. GitHub Issues — the live backlog and discussion
5. `LIVE_SESSION_*.md` — most recent live trading session notes

---

## 2. GitHub as Single Source of Truth

- **All** bugs, features, TODOs, and architectural decisions live in
  GitHub Issues on `https://github.com/martinsharkey/Langchain`.
- Do NOT maintain parallel trackers in local docs for active work.
- Labels: `bug`, `feature`, `learning`, `cryptorti`, `danny-blocked`, `infra`,
  `enhancement`, `trading-safety`.
- Milestones track release-bound work (e.g., `v1.0`, `onboarding-pipeline`).
- PRs must reference the issue(s) they resolve.

---

## 3. Commit & Push Discipline

### 3.1 After Every Session
- Stage only intended files (`git add -p`).
- Write a concise commit message that matches repo style:
  `type(scope): short description` — e.g., `fix(pipeline): relax floor validation`
- Commit MUST reference at least one GitHub issue number when applicable.
- **Push to origin before ending the session.** No un-pushed commits at session end.
- If a commit fails pre-commit hooks: fix the issue, do not skip hooks.

### 3.2 Atomic Commits
- One logical change per commit.
- Do NOT mix refactoring, feature work, and doc changes in one commit.
- WIP commits are allowed during a session but MUST be squashed before push.

---

## 4. Testing Requirements

### 4.1 Before Considering Work Complete
Every change MUST be validated by one of:
- **Unit tests** — add or update tests in `tests/`. Run: `python -m pytest tests -q`
- **Offline harness** — backtest/walkforward/robust_tester for strategy changes
- **Live observation** — for wiring changes, verify via dashboard endpoints
- **Integration test** — `examples/test_full_daily_cycle.py` for end-to-end paths

### 4.2 Test Suite Must Pass
- All 151+ tests must pass before a branch is merged to `main`.
- Skipped tests must have a tracked GitHub issue explaining why.
- New code that lacks tests is incomplete code.

### 4.3 CI/CD Gate
- `.github/workflows/ci.yml` MUST exist and be active.
- Every push to `main` and every PR must pass the CI test suite.
- If CI is broken, fix it before merging anything else.

---

## 5. Code Hygiene & Housekeeping

### 5.1 No Redundant Code
- Do NOT leave dead code, commented-out blocks, or unused imports.
- If a file/function/module is no longer referenced, delete it.
- Superseded files (e.g., old dashboards, old EAs, old agent loops) MUST be
  removed, not left in the tree.

### 5.2 Scheduled Housekeeping
Run `python housekeeping.py` at least once per session. It checks:
- Data-flow integrity (closed trades, pending orphans, provenance)
- Overlay sanity (stale focused pockets)
- Process hygiene (no duplicate engine processes)
- Old log/monitor file cleanup (>14 days)

### 5.3 Stale Document Cleanup
- `plans/` is for **active** plans only. Completed or obsolete plans are deleted.
- Old session notes that are superseded by `SESSION_LOG.md` are deleted.
- Before deleting: `git rm` and commit with message `chore: remove stale <file>`.

### 5.4 Current Stale Items (clean up in next session)
- `plans/architecture-plan.md` — references Wine/macOS bridge (no longer relevant)
- `plans/mt5-bridge-fix-plan.md` — Docker bridge was abandoned
- `plans/mt5-bridge-research-plan.md` — superseded by native Windows MT5
- `mt5_screen.png` — binary screenshot, not needed in repo
- `env.txt`, `env_out.txt` — credentials on disk (see Security section)

---

## 6. Architecture Maintenance

### 6.1 Docs Must Track Code
When the code structure changes:
- Update `ARCHITECTURE.md` and do not create duplicate architecture documents
- Update `README.md` project layout section
- Update `AGENTS.md` "Key paths" section
- Update `TESTING.md` if test harnesses change

### 6.2 Architecture Review Cadence
- At the start of every major phase, review `ARCHITECTURE.md` for drift.
- If a component's responsibility changes, update the architecture doc
  **before** merging the code change.
- The architecture docs are the contract; code is the implementation.

### 6.3 Core Rules
- `src/core_rules.py` is the **single source of truth** for trading rules.
- `AGENTS.md` and `.kilo/skill/trading-core-rules/SKILL.md` mirror it.
- All three must stay in sync. If a rule changes:
  1. Update `src/core_rules.py` FIRST
  2. Update `AGENTS.md` core rules section
  3. Update `SKILL.md`
  4. Only then change the code

---

## 7. Tool & Dependency Approval

### 7.1 No New Tools Without Approval
- Do NOT install new Python packages, add new system tools, or introduce new
  frameworks without explicit human approval in the console.
- If a dependency is needed: propose it, get approval, then add to
  `requirements.txt` with a pinned minimum version.

### 7.2 Existing Tooling
- The project uses: langchain, langgraph, litellm, chromadb, MetaTrader5,
  pandas, numpy, ta, rich, httpx, aiohttp, APScheduler, optuna, pytest,
  skl2onnx, onnxruntime, scikit-learn, sentence-transformers, boto3.
- Do NOT replace these without discussion.

---

## 8. Security

### 8.1 Never Commit Secrets
- `.env`, `.env.*`, `cryptorti/.env.cryptorti`, `cryptorti/certs/*.pem`,
  `*.key`, `aws_credentials*`, `env.txt`, `env_out.txt` are gitignored.
- If a secret is ever committed: rotate it immediately and scrub git history.
- `.env.example` contains placeholders only — never real values.

### 8.2 Credential Hygiene
- `env.txt` and `env_out.txt` contain real MT5 credentials on disk.
  **Delete them** — they are gitignored but still present.
- If MT5 password or any API key is exposed in chat: rotate immediately.
- For CI/VPS: use GitHub Actions Secrets or host environment secrets.
  Never write secrets to disk on a shared machine.

### 8.3 Dashboard Exposure
- The Flask dashboard (:5000) can change live trading mode.
- Never expose it to the public internet.
- Use VPN, SSH tunnel, or firewall allowlist only.

---

## 9. Live Trading Safety

### 9.1 Mode Defaults
- Default mode is `OBSERVE` (no orders).
- Promotion to `LIVE_MICRO` or `LIVE` requires human approval.
- `TRADING_MODE` is set in `.env` or via the dashboard control panel.

### 9.2 Kill Switch
- `data/KILL_SWITCH` file exists. Touching it halts all entries immediately.
- `LEARNING_ADAPTATION_ENABLED` freeze is the soft kill for self-learning.
- `LEARNING_AUTO_REVERT_ENABLED` keeps reverting bad configs even when
  adaptation is frozen.

### 9.3 Readiness Gate
- The bot should not promote to `LIVE` until:
  - 100+ clean closed trades on demo
  - Profit factor ≥ 1.3
  - Win rate ≥ 50%
  - Positive realised expectancy over 3+ months

---

## 10. Branching & Merging

### 10.1 Branch Strategy
- `main` is the deployable, tested, stable branch.
- Feature branches: `feat/<short-name>` or `fix/<issue-number>-<short-name>`
- Experimental branches: `exp/<name>` — may be force-pushed, do not depend on them
- `fix/17-11-manage-live-positions` is a long-lived feature branch awaiting merge.

### 10.2 Merge Requirements
- PR must pass CI.
- PR must have at least one reviewer (human or self-review with test proof).
- Squash-merges preferred for feature branches.
- Do NOT merge to `main` with failing tests or un-pushed commits.

---

## 11. Redundant Code & File Cleanup Checklist

Run this checklist at the start of every session:

- [ ] Are there any files in `plans/` that are no longer current? Delete them.
- [ ] Are there any `SESSION_CONTEXT_SUMMARY.md` duplicates? Consolidate.
- [ ] Are there any `.png`, `.pdf`, `.csv` in the repo that belong in `data/` or should be gitignored?
- [ ] Are there any `__pycache__/` or `.pyc` files tracked? They should not be.
- [ ] Are there any old dashboard/app launcher scripts (`app_old.py`, `run_bot.py`, etc.)?
- [ ] Are there any dead imports or commented-out code blocks?
- [ ] Is `src/main.py` (legacy multi-agent loop) still present? If yes, delete it.
- [ ] Are `env.txt` and `env_out.txt` present on disk? Delete them immediately.
- [ ] Is `.github/workflows/ci.yml` present? If not, copy from `ci_templates/ci.yml.template`.

---

## 12. Quick Reference — Commands

```bash
# Start the bot (single launcher)
python app.py LIVE_MICRO

# Run the full test suite
python -m pytest tests -q

# Run core rules assertion
python -m src.core_rules

# Run housekeeping report
python housekeeping.py

# Check GitHub issues (live backlog)
gh issue list

# Create a new issue
gh issue create --title "..." --label bug

# Push current branch
git push origin <branch>

# Activate CI (one-time setup)
mkdir -p .github/workflows && cp ci_templates/ci.yml.template .github/workflows/ci.yml
```

---

**Last updated:** 2026-08-18
**Applies to:** `martinsharkey/Langchain` — the Langchain MT5 trading bot
**Enforced by:** `AGENTS.md` signpost + this file + `src/core_rules.py`
