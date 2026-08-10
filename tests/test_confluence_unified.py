"""
Guardrail (#46): there must be exactly ONE confluence rule set.

The bug that caused months of mis-validated backtests was TWO confluence
implementations (live osma_confluence.py vs backtested confluence_signal.py) that
silently drifted. These tests assert the single-source-of-truth invariant so drift
cannot silently return: the live strategy must DELEGATE to confluence_signal, and it
must NOT re-implement the soft-check / Bulls-Bears rules itself.
"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_live_strategy_delegates_to_shared_confluence():
    import src.strategies.osma_confluence as live
    src = inspect.getsource(live)
    # must import + call the shared evaluator
    assert "evaluate_confluence_bar" in src, "live strategy must use the shared confluence evaluator"
    assert "from src.strategies.confluence_signal import" in src


def test_live_strategy_does_not_reimplement_rules():
    import src.strategies.osma_confluence as live
    src = inspect.getsource(live)
    # it must NOT contain its own Bulls/Bears or soft-check rule logic anymore
    assert "bears > -abs(bulls)" not in src, "old lenient Bulls/Bears rule must be gone"
    assert "_soft_checks" not in src, "live strategy must not define its own soft checks"


def test_shared_confluence_has_the_corrected_bulls_bears_rule():
    import src.strategies.confluence_signal as cs
    src = inspect.getsource(cs._soft_checks)
    assert "bulls > 0 and bears > 0" in src, "long rule must be Bulls>0 AND Bears>0"
    assert "bears < 0 and bulls < 0" in src, "short rule must be Bears<0 AND Bulls<0"
    assert "bears > -abs(bulls)" not in src, "old lenient rule must be gone"


def test_shared_evaluator_returns_trigger_kind():
    from src.strategies.confluence_signal import evaluate_confluence_bar
    # a clear confirmed long cross with full confluence
    ind = {"close": 100, "osma": 0.5, "osma_prev": -0.3, "macd_line": 1.2,
           "ema_fast": 99.5, "ema_prev": 99.0, "atr": 1.0, "atr_prev": 0.8,
           "bulls_power": 2.0, "bears_power": 0.5, "rsi": 55, "med_atr": 1.0}
    r = evaluate_confluence_bar(ind, {})
    assert "trigger_kind" in r and r["trigger_kind"] in ("cross", "anticipated", None)
    assert r["action"] in ("buy", "sell", "hold")


if __name__ == "__main__":
    test_live_strategy_delegates_to_shared_confluence()
    test_live_strategy_does_not_reimplement_rules()
    test_shared_confluence_has_the_corrected_bulls_bears_rule()
    test_shared_evaluator_returns_trigger_kind()
    print("confluence unification guardrail tests passed")
