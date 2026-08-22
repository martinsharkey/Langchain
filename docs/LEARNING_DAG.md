# Learning Module Initialization DAG

Source: `src/trading/scalp_engine.py:129-360`.

This document records the exact startup order and dependencies of the learning stack so future refactors do not accidentally create circular imports or use an uninitialized component.

## Layer 0 — Foundation

`ExperienceDatabase` is created first; every later module receives it as a dependency.

## Layer 1 — Independent analytics

Order matters only in that each gets the same `ExperienceDatabase`:

1. `PerformanceResearcher(experience_db)`
2. `EdgeCalculator(experience_db)`
3. `SymbolGovernor(knowledge_base)` — may create a fallback `KnowledgeBase`
4. `TradePostMortem(experience_db, knowledge_base)` — reuses governor's KB

## Layer 2 — Data + Optimizer

5. `DataManager` + `DataRefreshManager` — offline-first data layer; no learning dependency.
6. `ParameterOptimizer(registry, backtest_fn)` — requires `DataManager` via `_make_backtester()`.

## Layer 3 — Knowledge + Checkpointer

7. `KnowledgeStore()` — embedded Chroma/MiniLM; downloads model once. Non-fatal.
8. `sync_project_knowledge(ks)` — copies durable project notes into the live store.
9. `DatastoreIngestor.scan_and_ingest()` — absorbs existing datastore files.
10. `ConfigCheckpointer(knowledge_store)` — needs `KnowledgeStore` for semantic failure memory.

## Layer 4 — Reflection / Research

11. `MQL5Knowledge()` — optional RAG over mql5 docs.
12. `EdgeDiscovery(registry, backtester, knowledge_store)` — uses registry + backtester.
13. `ContinualResearcher(..., make_backtester_fn=self._make_backtester, change_validator=..., knowledge_store=..., edge_discovery=...)` — consumes almost everything above.

## Layer 5 — Bridges

14. `OptunaLiveBridge(param_optimizer, change_validator, learning_log)` — daily Optuna → live tuned params.

## Dependency summary

```
ExperienceDatabase
  ├─ PerformanceResearcher
  ├─ EdgeCalculator
  ├─ SymbolGovernor ─┐
  └─ TradePostMortem ◄┘

DataManager
  └─ _make_backtester()
       └─ ParameterOptimizer
            └─ OptunaLiveBridge

KnowledgeStore
  ├─ sync_project_knowledge
  ├─ DatastoreIngestor
  ├─ ConfigCheckpointer
  ├─ EdgeDiscovery
  └─ ContinualResearcher
       ├─ ChangeValidator
       ├─ EdgeDiscovery
       └─ ParameterOptimizer (via current_params_fn)
```

## Rules for modifying initialization

- Do **not** move `KnowledgeStore` creation before `ExperienceDatabase`.
- `ContinualResearcher` must be created **after** `ParameterOptimizer`, `ConfigCheckpointer`, and `EdgeDiscovery`.
- `_make_backtester()` uses `self.registry` and `self.data_manager`; call it only after those exist.
- All component construction is wrapped in `try/except` so a single missing model/download does not prevent trading.
