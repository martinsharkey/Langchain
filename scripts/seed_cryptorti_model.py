"""
ONE-OFF CryptoRTI model seeder (manual — NOT automated).

Danny's S3 feature data is a one-time SAMPLING exercise to identify the pattern.
This script pulls the ML-ready v5 `features/` parquet across ALL series (coinbase
+ binance, BTC + ETH; ~395MB total, safe for the ~60GB local limit) ONCE, trains
the per-symbol XGBoost model (target = label_direction_5m, no look-ahead), persists
it to data/models/, and records authority-gateable patterns.

After this one-off seed, the LIVE CryptoRTI signal is the primary source: the bot
scores each inbound signal with the persisted model and augments it from our OWN
accumulated signal outcomes (nightly), never re-pulling this bucket.

We DELIBERATELY never touch the multi-GB raw families (book_events ~7GB,
derivatives/orderbook ~9GB, history_bars ~3GB) — only the derived `features/`.

Run once:  python -m scripts.seed_cryptorti_model
"""
import sys
from src.learning.experience_db import ExperienceDatabase
from src.cryptorti.feature_model import CryptoRTIFeatureModel

# The ML-ready feature series to seed from (derived, ~100MB each — never raw L2).
SERIES = [
    ("coinbase", "BTC-USD"),
    ("binance", "BTCUSDT"),
    # ETH available too if we extend to ETHUSD trading:
    # ("coinbase", "ETH-USD"), ("binance", "ETHUSDT"),
]


def main():
    db = ExperienceDatabase()
    for exchange, sym in SERIES:
        print(f"\n=== ONE-OFF SEED: {exchange}/{sym} ===", flush=True)
        m = CryptoRTIFeatureModel(db, exchange=exchange, symbol_s3=sym)
        dates = m.available_dates()   # bounded by CRYPTORTI_MAX_DAYS
        if not dates:
            print("  no S3 dates (need .env.cryptorti creds). Skipping.")
            continue
        print(f"  training on {len(dates)} days: {dates[0]} .. {dates[-1]}", flush=True)
        res = m.train(dates=dates)
        print(f"  result: {res}", flush=True)
    # authority gate so a proven seed model can go live
    promoted = db.promote_ml_patterns(200, 3, 0.55)
    print(f"\nauthority gate: {promoted} pattern(s) authoritative.")
    print("Done. The live CryptoRTI signal is now primary; this seed won't re-run.")


if __name__ == "__main__":
    main()
