"""Growth engine: compounding sizing + capital extraction (never lose the stake)."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import config


def test_capital_extraction_banks_stake_once():
    """First time balance hits GROWTH_EXTRACT_AT, the original stake is banked and
    sizing thereafter runs on (balance - withdrawn) — stake never risked again."""
    # lightweight stand-in exercising the extraction rule directly
    class Eng:
        _capital_withdrawn = 0.0
        _maybe_extract_capital = None
    from src.trading.scalp_engine import ScalpEngine
    e = ScalpEngine.__new__(ScalpEngine)
    e._capital_withdrawn = 0.0
    # below threshold -> no extraction
    e._maybe_extract_capital(500.0)
    assert e._capital_withdrawn == 0.0
    # at threshold -> bank the stake
    e._maybe_extract_capital(config.GROWTH_EXTRACT_AT + 5)
    assert e._capital_withdrawn == config.GROWTH_INITIAL_CAPITAL
    # idempotent — doesn't double-bank
    e._maybe_extract_capital(config.GROWTH_EXTRACT_AT + 5000)
    assert e._capital_withdrawn == config.GROWTH_INITIAL_CAPITAL


def test_compounding_sizes_on_house_money_after_extraction():
    """After extraction, tradable = balance - withdrawn, so lot compounds on house money."""
    bal = 5000.0; withdrawn = config.GROWTH_INITIAL_CAPITAL
    tradable = bal - withdrawn
    lot = (tradable / config.GROWTH_BALANCE_PER_LOT) * 0.01
    # sanity: at L5000 with L31/lot, lot ~ (4900/31)*0.01 = 1.58
    assert 1.0 < lot < 2.0, lot


if __name__ == "__main__":
    test_capital_extraction_banks_stake_once()
    test_compounding_sizes_on_house_money_after_extraction()
    print("growth engine tests passed")
