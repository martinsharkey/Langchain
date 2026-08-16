# Adaptive Intelligence Architecture (L3-L6 + Reflection)

The target learning architecture: a ReAct-style loop where the bot reasons about
failed trades, scores indicators, forms questions, asks an LLM, proposes new /
recombined strategies, validates them on real MT5 history (continual backtest),
and only promotes what genuinely works - writing every lesson to memory.

Built on top of the existing working pieces (16 strategies, weighted ensemble,
RAG at entry, A/B trade management, real reconciliation).

## Flow

1. LIVE TRADING -> experience DB records real outcomes + per-indicator scores +
   entry context (session, candle geometry, regime).
2. After N closed losers (or on schedule) -> L4 ReflectionAgent (ReAct):
   observe losses -> score which indicators misfired -> FORM A QUESTION ->
   ask the LLM -> get a concrete, testable hypothesis.
   e.g. "RSI longs fail when ADX>30 during the 21:00 gold session; try adding an
   ADX<25 filter or swapping RSI for a trend indicator."
3. Hypothesis written to the knowledge base as a PENDING EXPERIMENT (not a live
   rule change) with the indicator scores and a proposed strategy combination.
4. L5 StrategySynthesizer turns a hypothesis into a CANDIDATE strategy
   (indicator swap / combination / parameter tweak) and registers it via
   register_custom(status="testing") - it can be evaluated but earns no live
   weight yet.
5. L6 Continual Backtester pulls MONTHS of real MT5 bars (get_rates), replays
   them with NO look-ahead, and scores single + combined strategies for entry
   and exit quality (win rate, profit factor, drawdown, avg bars-to-target).
6. PROMOTION GATE: a testing strategy only becomes active (earns ensemble
   weight) if it beats the incumbent out-of-sample by a margin. Otherwise it is
   archived with its score so the bot does not retry the same dead end.
7. MEMORY: hypotheses, indicator scores, and backtest results are stored and
   recalled - the RAG + knowledge base - so future decisions and future
   reflections build on past ones.

## Components (files)

- src/learning/indicator_scorer.py       - per-indicator entry-quality scoring
- src/learning/backtester.py             - L6 no-look-ahead MT5-history backtest
- src/learning/reflection_agent.py       - L4 ReAct reflection -> hypotheses
- src/learning/strategy_synthesizer.py   - L5 hypothesis -> candidate strategy
- src/learning/adaptive_loop.py          - orchestrates L4/L5/L6, promotion gate
- experience_db + knowledge_base         - persistence for scores/hypotheses/results
- scalp_engine                           - calls adaptive_loop on a cadence;
                                           records indicator scores + context

## Guardrails (so we do not fool ourselves - the Hermes trap)

- Reflection NEVER changes live rules directly; it only proposes hypotheses.
- New strategies start status="testing" and trade nothing until backtest-passed.
- Promotion requires OUT-OF-SAMPLE improvement (train/validate split on history).
- Every promotion/rejection is logged with the evidence, and archived hypotheses
  are remembered so the bot does not loop on the same idea.
- Indicator scores and reflections are advisory inputs, not overrides of the
  deterministic risk/session/broker-SL safety layer.

## Continual backtest (delegation)

The live engine delegates candidate strategy combinations to the backtester,
which runs against real MT5 history (months of bars per symbol/timeframe). It
pattern-matches single strategies and combinations to find safe entries/exits,
returns a scorecard, and the promotion gate decides. This runs in the background
so it never blocks live trading.
