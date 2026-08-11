# AGENT ORIENTATION — Read This First (Every Agentic Developer)

> **This document orients any AI/agentic developer (Kilo, Claude, Gemini, Codex,
> IBM Bob, or any future model) working in this workspace. Read it in full before
> making a single change. It sits above all other docs. `AGENTS.md` is the
> project signpost; THIS file is the constitution.**

---

## 0. The One Rule That Overrides Everything

**Every line of code, config, and document in this workspace was authored by
agentic developers across many sessions. There is no "other team." You are the
current owner of ALL of it.**

Consequences of that ownership:

1. **You own every file, even ones you did not write.** "A previous agent wrote
   this" is never an excuse. If it is broken, you fix it. If it is unclear, you
   clarify it. If it conflicts with the current architecture, you reconcile it.
2. **You inherit the full history.** Before changing anything, understand *why*
   it exists. Read the surrounding code, the docs it references, and the git log.
   Assume prior decisions were deliberate until the evidence says otherwise.
3. **You leave the workspace more coherent than you found it.** No orphaned
   files, no half-finished parallel systems, no duplicate implementations.

---

## 1. MANDATORY: Discover Before You Build — Enhance, Never Rebuild

**The single most damaging mistake in this workspace is rebuilding a capability
that already exists because you did not look first.** Almost everything you will
be asked for has already been built in a prior session. Your default assumption
must be: **"this probably already exists — find it and enhance it."**

Before you write ANY new feature, class, file, or "system", you MUST run a
discovery pass and state what you found. This is not optional:

1. **Search the whole workspace for the concept, by many names.** e.g. for a
   "basket/pyramid" feature, grep `basket|pyramid|scale.?in|add.?leg|leg_|GROWTH_`.
   For a "supervisor/reasoning" feature, grep `llm_review|htf|supervisor|react|
   langgraph`. Search `src/`, `tests/`, `*.md`, `config.py`, and the git log.
2. **Read what you find in full** — including whether it is DISABLED behind a flag
   (e.g. `GROWTH_ENABLED=false`), half-finished, or simply not wired in. "It
   doesn't run" almost never means "it doesn't exist."
3. **State the finding to the user before building**: "X already exists in
   `<file:line>`; it does A and B but not C; I will ENHANCE it to add C" — or, if
   genuinely absent, "I searched for A/B/C and found nothing; this is genuinely
   new because …".
4. **Enhancement is the default; rebuild is a last resort** that requires an
   explicit reason the existing code cannot be extended, stated out loud and
   agreed with the user.

If you skip this pass and rebuild something that existed, you have caused a
regression and duplicated maintenance — treat it as a serious error, not a style
nit. When in doubt: **search, read, then ask — do not build.**

---

## 2. Reuse First — Never Build a Parallel System

This codebase already contains a complete learning stack, execution engine,
knowledge stores, backtester, and provider router. **Before you build anything,
search for what already exists and extend it.**

- **Do NOT** create a second RAG, a second optimizer, a second researcher, a
  second config store, or a second "notebook." One of each already exists.
- **Do** wire new capability into the existing component (e.g. add a provider to
  `litellm_providers`, add a node to the existing researcher, add a column to the
  existing `experience_db`).
- If you genuinely believe a fresh component is required, **say so explicitly and
  justify why the existing one cannot be extended** before writing it.

Canonical components (reuse these — do not duplicate):

| Concern | The ONE canonical file | Do not create a rival |
|---|---|---|
| Execution engine | `src/trading/scalp_engine.py` | no second engine |
| Entry signal | `src/strategies/confluence_signal.py` | no second signal fn |
| Trade experience / telemetry | `src/learning/experience_db.py` | no second DB |
| Parameter tuning | `src/learning/param_optimizer.py` | no second optimizer |
| Cognitive loop | `src/learning/continual_researcher.py` (+ `langgraph_researcher.py` wrapper) | no second researcher |
| Local semantic memory | `src/learning/knowledge_store.py` | no second local RAG |
| External knowledge | `src/learning/mql5_knowledge.py` | no second crawler |
| NotebookLM (hosted) | `src/learning/notebooklm_provider.py` | no second connector |
| Chroma access | `src/learning/chroma_client.py` (shared singleton) | no direct clients |
| LLM providers | `litellm_providers/provider_router.py` | no ad-hoc LLM calls |
| **Pyramiding / basket (scale-in)** | `scalp_engine.py` PYRAMIDING block (`GROWTH_*` in `config.py`) — **already built; may be DISABLED via `GROWTH_ENABLED`** | no second basket system |
| **Trade management LLM review** | `scalp_engine.py::_llm_trade_review` (HYBRID_LLM) — enhance this, don't replace | no second manager LLM |
| **Multi-timeframe alignment** | `src/learning/htf_context.py` (M5/M15/M30/H1) | no second HTF reader |
| **Entry-quality / frequency learner** | `src/learning/entry_strength.py` + `entry_frequency.py` (overlay currently disabled on live entries) | no second entry learner |
| **Real-tick backtest / walk-forward** | `src/learning/backtester.py`, `scripts/robust_tester.py`, `iterative_walkforward.py` | no second backtester |

> ⚠️ **Before adding ANY trading behaviour (baskets, exits, scaling, gates,
> reasoning), grep for it first — most of it is already here, sometimes behind a
> disabled flag.** The pyramiding basket, HTF alignment, and LLM trade review all
> pre-exist. Enhance them; do not recreate them.

---

## 3. Do Not Break What Works

- **The live engine's entry path is sacred and LLM-free.** Never put an LLM call,
  network call, or LangGraph reasoning on the trade-trigger path — latency
  destroys the edge. LLMs only assist *trade management* and the *async
  researcher*.
- **Verify before you commit.** Syntax-check every changed file, instantiate the
  engine, and run the test suite. The baseline is **all tests passing** — a
  session that reduces the passing count is a regression, not progress.
- **Never delete learning/baselines to "make it trade."** Tuned params, the
  experience DB, and vector stores are hard-won. Toggle symbols via
  `TRADING_SYMBOLS` / `DISABLED_SYMBOLS`; re-baseline via the EXISTING
  `FloorDiscovery` pipeline. Do not hand-edit floors unless explicitly instructed.

---

## 4. Housekeeping Is Part of the Job

- **Remove your own scratch files.** Temporary trace logs, one-off scripts
  (`rebaseline_*.py`, `ablation_*.py`, `trace_*.log`, throwaway `.bat` files) must
  be deleted before you finish. Do not leave debris for the next agent.
- **No dead code paths.** If you replace a component, remove or clearly retire the
  old one — do not leave two live systems fighting each other.
- **Keep docs truthful.** If you change behaviour, update the doc that describes
  it in the same session. Stale docs are treated as bugs. Older docs may still
  reference deleted files (e.g. `src/main.py`) — if you touch that area, correct
  the doc. Engineering rules live in `PROJECT_RULES.md`.

---

## 5. Source of Truth & Workflow

- **GitHub is the single source of truth** for issues/features/bugs
  (`https://github.com/martinsharkey/Langchain`). Open an issue when you discover
  work; reference issues in commits.
- **Commit with intent.** Small, verified, clearly-messaged commits. State what
  changed and why. Never commit an unverified/half-finished change as "done."
- **Reading order for a new session:**
  1. This file (`AGENT_ORIENTATION.md`)
  2. `AGENTS.md` (current state, what's built, what's next)
  3. `ARCHITECTURE_OVERVIEW.md` + `LEARNING_ARCHITECTURE.md`
  4. `TESTING.md` before running/altering tests
  5. The specific file(s) you intend to change — and their `git log`.

---

## 6. Honesty Contract

- If something is broken, say it plainly. Do not paper over a crash with a
  fallback that hides the failure.
- If you are unsure what the user wants, ask **before** building — do not guess
  and build the wrong thing (a second local RAG when a hosted connector was
  asked for, etc.).
- Never claim work is complete, tested, or pushed when it is not. "Committed
  locally" ≠ "pushed to GitHub." Be exact.

---

*Every agentic developer that touches this workspace is accountable for the whole
of it. Build like the next agent — and the account owner's real capital — depend
on it. They do.*
