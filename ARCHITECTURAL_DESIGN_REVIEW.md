# ARCHITECTURAL DESIGN REVIEW
## Testing Framework + Symbol Research + Handoff System

**Review Date:** 2026-07-30  
**Scope:** Analyze proposed system architecture before implementation  
**Approach:** Think like an architect, not a coder

---

## WHAT YOU'RE PROPOSING (Decoded)

You want a **multi-agent handoff workflow** where:
1. **Tester Agent** - Discovers, enhances, runs tests; logs issues
2. **Developer Agent** - Reviews issues, fixes code, commits
3. **Symbol Research Agent** - Continuously learns about XAUUSD behaviors
4. **Version Control** - Ensures coherent handoffs across agents
5. **Feedback Loop** - Issues → Fixes → Tests → Repeat

This is **not just testing**. This is **autonomous CI/CD with learning**.

---

## ARCHITECTURAL ANALYSIS

### Current Stack We Already Have
```
✅ LangChain ReAct agents (5 specialized agents)
✅ LangGraph for orchestration
✅ ChromaDB for RAG/learning
✅ SQLite for structured data
✅ MT5 connector for market data
✅ Multi-LLM fallback system
✅ GitHub integration capability (via git commands)
```

### What's Missing (Not Implemented Yet)
```
❌ Agent handoff mechanism (who does what, when)
❌ Version tracking system
❌ Symbol research knowledge base
❌ Test suite infrastructure
❌ Issue logging and tracking
❌ Code review workflow
```

---

## THE CORE PROBLEM WE NEED TO SOLVE

### Problem #1: Agent Choreography (The Handoff Problem)
**Current state:** Agents don't hand off work cleanly; no concept of "state transfer"

**What we need:** 
- Agent A completes work
- Transfers context/files/issues to Agent B
- Agent B knows exactly what to do with it
- Agent B completes work
- Transfers back to Agent A

**This requires:**
- Shared context database
- State machine for workflow
- Clear interface between agents
- Version awareness

### Problem #2: Symbol Research Gap
**Current state:** Bot has strategies but no specialized knowledge about XAUUSD specifically

**What we need:**
- Continuous research on XAUUSD behavior
- Learn proven trading strategies
- Identify market patterns
- Understand what moves gold prices
- Build symbol-specific knowledge base

**But here's the key issue:**
- This should be **independent** from trading cycle
- Should run **continuously** gathering knowledge
- Should inform but **not block** trading decisions
- Needs separate infrastructure (browser automation, web scraping)

### Problem #3: Version Coherence
**Current state:** No versioning; don't know if code/tests/knowledge match

**What we need:**
- Semver (MAJOR.MINOR.PATCH)
- Tracked at: bot version, test version, symbol research version
- Each agent checks version compatibility before accepting handoff
- Reject if versions don't align

---

## ARCHITECTURAL PROPOSAL (Think Like Architect)

### Layer 1: Workflow State Machine (Foundation)
```
A clean, minimal layer that manages handoffs:

States:
  - RESEARCH_READY → TESTING_READY → DEVELOPMENT_READY → TESTING_READY → LIVE
  
Transitions:
  - Only allow valid transitions
  - Each transition includes version check
  - Each transition logs to audit trail
  
Owned by: LangGraph orchestrator (new)
```

### Layer 2: Shared Context (Communication)
```
Three critical pieces of shared context:

1. VERSIONING TABLE (SQLite)
   - bot_version: "1.0.0"
   - test_suite_version: "1.0.0"
   - symbol_research_version: "1.0.0"
   - last_updated: timestamp
   - compatibility_notes: JSON

2. ISSUE LOG (SQLite + GitHub Issues)
   - issue_id: auto
   - type: "bug" | "feature" | "enhancement"
   - status: "open" | "in_review" | "in_progress" | "fixed"
   - owner: agent_name
   - version_found: "1.0.0"
   - version_fixed: null (until dev fixes)
   - github_issue_url: link

3. SYMBOL RESEARCH KB (ChromaDB)
   - Separate from trading patterns
   - Contains: Research findings, proven strategies, correlations
   - Updated by: Symbol Research Agent only
   - Consumed by: Strategy Agent (read-only during trading)
```

### Layer 3: Individual Agents (Applications)

#### Agent 1: SYMBOL RESEARCH AGENT (New)
```
Purpose: Run independently, continuously research XAUUSD

Schedule: Background process (not tied to trading cycle)

Responsibilities:
  - Browse market research websites (Chrome headless + Playwright)
  - Scrape economic data sources
  - Monitor geopolitical news
  - Extract proven strategies from trading blogs/research
  - Identify correlations (interest rates, USD strength, etc)
  - Store findings in symbol_research KB (ChromaDB)
  - Update version when new knowledge acquired

Does NOT:
  - Execute trades
  - Modify bot code
  - Block trading cycle
  - Make investment decisions

Technology:
  - Playwright (browser automation)
  - BeautifulSoup (scraping)
  - ChromaDB (store research)
  - Separate background process (via background_process tool)
```

#### Agent 2: TESTER AGENT (Enhanced)
```
Purpose: Autonomous testing with learning

Workflow:
  1. Check bot_version vs test_suite_version (version gate)
  2. Query "what tests exist?" from SQLite test registry
  3. Query "any new code changes?" from git log + symbol_research version
  4. For each new feature: enhance existing tests or create new
  5. Run complete test suite
  6. For failures: create issue in SQLite + GitHub
  7. Log detailed results
  8. Update test_suite_version
  9. Hand off to DEV AGENT with issue list

Does NOT:
  - Fix code
  - Modify GitHub beyond issues
  - Make trading decisions

Technology:
  - pytest (test framework)
  - SQLite (test registry + issue log)
  - GitHub API (create issues)
  - Version checking logic
```

#### Agent 3: DEVELOPER AGENT (Enhanced)
```
Purpose: Code review, fix issues, implement features

Workflow:
  1. Check version compatibility before accepting handoff
  2. Query issue log (status="open")
  3. For each issue:
     a. Review code related to issue
     b. Understand root cause
     c. Write fix
     d. Commit to branch
     e. Update issue status → "in_progress" → "fixed"
  4. Update bot_version (PATCH increment)
  5. Hand off to TESTER AGENT

Does NOT:
  - Create pull requests (explicit request only)
  - Push to main (explicit request only)
  - Make trading decisions

Technology:
  - Git (version control)
  - SQLite (issue tracking)
  - Code analysis tools
```

#### Agent 4: TRADING CYCLE AGENT (Existing - Minor Enhancement)
```
Purpose: Execute trades, run bot

Enhancement:
  - Check symbol_research_version at cycle start
  - If new research available: inject into strategy decisions (read-only)
  - Don't block on research (async consumption)
  - Log which research was considered for each decision
  
Technology:
  - Existing MT5 connector
  - New: async read of symbol_research KB
```

---

## VERSION SYSTEM DESIGN

```
Semver Format: MAJOR.MINOR.PATCH-COMPONENT

Examples:
  1.0.0-bot           (bot/learning system)
  1.0.0-tests         (test suite)
  1.0.0-symbol        (symbol research)

Version Table (SQLite):
  component    | version | last_updated | git_commit | metadata
  -------------|---------|--------------|------------|----------
  bot          | 1.0.0   | 2026-07-30   | a3f4d2b   | {features: [...]}
  tests        | 1.0.0   | 2026-07-30   | b5e2c1a   | {coverage: 85%}
  symbol       | 1.0.0   | 2026-07-30   | c7d8f9e   | {sources: [...]}

Version Compatibility Matrix:
  bot 1.0.0 works with: tests 1.0.x, symbol 1.0.x
  If test 2.0.0 appears but bot 1.0.0: VERSION MISMATCH → trigger review
```

---

## CRITICAL ARCHITECTURAL DECISIONS

### Decision 1: Symbol Research Independence ✅
**Why separate?**
- Research is **slow** (web scraping, waiting for pages)
- Trading cycle is **time-critical** (sub-second decisions)
- Research should be **continuous** (24/7), trading is **market-hours**
- Failure in research should **not block** trading

**Implementation:**
- Background process (via background_process tool)
- Separate database tables
- Async read from trading cycle (non-blocking)
- Update versioning when research finds new insights

### Decision 2: Issue Log Dual Write ✅
**Why both SQLite and GitHub?**
- SQLite: **Agents read/write** this (internal workflow)
- GitHub: **Humans track** this (external visibility)
- Sync direction: SQLite → GitHub (one-way)
- GitHub issues are reference; SQLite is source of truth for agents

**Implementation:**
- Agents write to SQLite issue_log
- Periodic sync: SQLite → GitHub API
- Humans can comment on GitHub, but agents ignore comments
- Single source of truth: SQLite

### Decision 3: Version Gates (Not Blocking) ✅
**Why not hard block?**
- Flexibility for experimental features
- But **alert** when versions misaligned
- Tester can choose: "proceed anyway" or "wait for fix"
- Log this decision for audit trail

**Implementation:**
```
Pseudo-code:
if bot_version != test_suite_version:
    ALERT("Version mismatch detected")
    log_event("version_mismatch", bot: "1.0.0", test: "1.0.1")
    if user_has_approved("proceed"):
        PROCEED_WITH_WARNING()
    else:
        WAIT_FOR_ALIGNMENT()
```

### Decision 4: Agent Handoff Protocol ✅
**What gets transferred?**
```
Handoff Package:
  - version_info (all 3 versions)
  - issue_log (all open issues)
  - symbol_research_updates (if any new knowledge)
  - git_commit (last commit hash)
  - state_checkpoint (SQLite dump)
  - metadata (timing, who handed off, why)
```

**Implementation:**
- SQL view: "current_handoff_package()"
- Atomic transaction (all or nothing)
- Signature verification (agent checksums handoff)
- Audit trail (who got what, when)

---

## WHY THIS ARCHITECTURE WORKS

| Aspect | How It Works |
|--------|------------|
| **Separation of Concerns** | Each agent has 1 responsibility; doesn't own others' domains |
| **Async Research** | Symbol research runs 24/7 without blocking trades |
| **Version Safety** | Prevents incompatible agents from interfering |
| **Audit Trail** | Every handoff, every version change, every issue logged |
| **Learning** | Symbol research + experience database both feed into decisions |
| **Scalability** | Can add more agents (e.g., Risk Agent, Performance Analyst) without changing core |
| **Leverage Existing** | Uses LangChain, LangGraph, ChromaDB, SQLite already in use |

---

## WHAT NOT TO DO (Anti-Patterns)

❌ **Don't:** Make symbol research block trading  
✅ **Do:** Run it async, inject findings post-decision

❌ **Don't:** Hard-block on version mismatch  
✅ **Do:** Alert, log, let user decide with awareness

❌ **Don't:** Create pull requests automatically  
✅ **Do:** Let developer review issues first, commit to branch manually

❌ **Don't:** Write test code without understanding new features  
✅ **Do:** Have Tester Agent query "what changed?" before writing tests

❌ **Don't:** Store research in same ChromaDB as trading patterns  
✅ **Do:** Separate databases (symbol_research_kb vs trading_patterns_kb)

---

## IMPLEMENTATION PHASING

### Phase 1: Foundation (8-12 hours)
1. Create version tracking system (SQLite table)
2. Create issue log system (SQLite + GitHub sync)
3. Implement version gates (alert logic)
4. Implement handoff protocol (atomic transfer)

### Phase 2: Agent Enhancement (16-20 hours)
1. Enhance Tester Agent (query capabilities, test registry)
2. Enhance Developer Agent (issue queue, version updates)
3. Enhance Trading Agent (async research consumption)
4. Create Tester ↔ Developer handoff workflow

### Phase 3: Symbol Research Agent (12-16 hours)
1. Design research schema (what we want to learn)
2. Implement browser automation (Playwright)
3. Implement research worker (async process)
4. Integrate with trading cycle (read-only access)

### Phase 4: Integration Testing (4-6 hours)
1. Full workflow: Trade → Tester → Developer → Tester → Trade
2. Verify version gates work
3. Verify handoff is atomic
4. Verify symbol research doesn't block trading

**Total: 40-54 hours** (significant but manageable in phases)

---

## KEY INSIGHT: This Isn't Just Testing

What you're describing is actually:
- **CI/CD Pipeline** (with agents as stages)
- **Knowledge Management System** (symbol research)
- **Issue Tracking Workflow** (automated logging)
- **Version Control Strategy** (multi-component tracking)
- **Handoff Protocol** (agent choreography)

This is enterprise-grade infrastructure. It's not a simple test suite—it's a **self-healing, self-improving trading system with audit trails**.

---

## RECOMMENDATION

Implement in order:
1. **Version System** (foundation - MUST do first)
2. **Handoff Protocol** (enables agent coordination)
3. **Tester/Developer Enhancement** (core workflow)
4. **Symbol Research Agent** (async learning)

Once Phase 2 is done, you have a **working cycle**: Tester → Dev → Tester → Trade

Symbol research (Phase 3) is independent and can run in parallel while bot trades.

---

**Verdict:** This is architecturally sound. It leverages everything you already have (LangChain, LangGraph, ChromaDB, SQLite). It's implementable in phases. It's scalable and auditable.

Should we proceed with this design?
