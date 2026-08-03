"""
Tests for the GoldShark -> real `trades` DB importer.

Asserts the integration invariants:
  - LONG/SHORT map to buy/sell; rows land in the live `trades` table.
  - data_source provenance is tagged (Bug 4).
  - MFE/MAE labels are persisted from the CSV.
  - Look-ahead guard: hindsight peak_/exit_ indicator columns NEVER become
    entry features in indicators_snapshot (Bug 1).
"""
import sys, os, tempfile, csv, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.experience_db import ExperienceDatabase
from src.learning.goldshark_import import GoldSharkImporter


def _write_csv(path, rows, header):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _mk(tmp):
    return ExperienceDatabase(db_path=os.path.join(tmp, "t.db"))


def test_import_maps_and_tags_provenance():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "gs.csv")
        header = ["Symbol", "Direction", "EntryPrice", "EntryMACD", "EntryOsMA",
                  "EntryBulls", "EntryBears", "ATR_14", "MaxProfitPts", "MaxLossPts",
                  "ExitPts", "Profit", "ExitReason"]
        rows = [
            {"Symbol": "XAUUSD", "Direction": "LONG", "EntryPrice": "2000.0",
             "EntryMACD": "0.5", "EntryOsMA": "0.2", "EntryBulls": "1.1", "EntryBears": "0.3",
             "ATR_14": "1.2", "MaxProfitPts": "300", "MaxLossPts": "-80", "ExitPts": "150",
             "Profit": "1.5", "ExitReason": "tp"},
            {"Symbol": "XAUUSD", "Direction": "SHORT", "EntryPrice": "2010.0",
             "EntryMACD": "-0.4", "EntryOsMA": "-0.1", "EntryBulls": "-0.9", "EntryBears": "-0.2",
             "ATR_14": "1.0", "MaxProfitPts": "50", "MaxLossPts": "-200", "ExitPts": "-120",
             "Profit": "-1.2", "ExitReason": "sl"},
        ]
        _write_csv(csv_path, rows, header)

        db = _mk(d)
        res = GoldSharkImporter(db).ingest_csv(csv_path, data_source="SIMULATED_REAL_TICKS")
        assert res["inserted"] == 2 and res["resolved"] == 2, res

        conn = sqlite3.connect(os.path.join(d, "t.db"))
        conn.row_factory = sqlite3.Row
        got = conn.execute("SELECT action, outcome, data_source, mfe_points, mae_points, "
                           "exit_points, indicators_snapshot FROM trades ORDER BY id").fetchall()
        assert [r["action"] for r in got] == ["buy", "sell"]
        assert [r["outcome"] for r in got] == ["win", "loss"]
        assert all(r["data_source"] == "SIMULATED_REAL_TICKS" for r in got)
        assert got[0]["mfe_points"] == 300 and got[0]["mae_points"] == -80
        assert got[0]["exit_points"] == 150
        conn.close()


def test_import_excludes_lookahead_features():
    """Hindsight peak_/exit_ indicator columns must NOT enter indicators_snapshot."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "gs.csv")
        header = ["Symbol", "Direction", "EntryPrice", "EntryMACD",
                  "PeakMACD", "ExitMACD", "MaxProfitPts", "MaxLossPts", "Profit"]
        rows = [{"Symbol": "XAUUSD", "Direction": "LONG", "EntryPrice": "2000.0",
                 "EntryMACD": "0.5", "PeakMACD": "9.9", "ExitMACD": "8.8",
                 "MaxProfitPts": "300", "MaxLossPts": "-80", "Profit": "1.5"}]
        _write_csv(csv_path, rows, header)

        db = _mk(d)
        GoldSharkImporter(db).ingest_csv(csv_path)
        conn = sqlite3.connect(os.path.join(d, "t.db"))
        snap = json.loads(conn.execute("SELECT indicators_snapshot FROM trades").fetchone()[0])
        conn.close()
        assert "macd_line" in snap and snap["macd_line"] == 0.5   # entry feature kept
        # hindsight values must be absent
        for leak in ("peak_macd", "exit_macd", "PeakMACD", "ExitMACD", 9.9, 8.8):
            assert leak not in snap and leak not in snap.values()


def test_simulated_ohlc_is_excluded_from_training_query():
    """Imported SIMULATED_OHLC rows must be filtered out of the ONNX training set."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "gs.csv")
        header = ["Symbol", "Direction", "EntryPrice", "EntryMACD", "MaxProfitPts", "MaxLossPts", "Profit"]
        rows = [{"Symbol": "XAUUSD", "Direction": "LONG", "EntryPrice": "2000.0",
                 "EntryMACD": "0.5", "MaxProfitPts": "300", "MaxLossPts": "-80", "Profit": "1.5"}]
        _write_csv(csv_path, rows, header)
        db = _mk(d)
        GoldSharkImporter(db).ingest_csv(csv_path, data_source="SIMULATED_OHLC")
        conn = sqlite3.connect(os.path.join(d, "t.db"))
        n = conn.execute("SELECT COUNT(*) FROM trades WHERE outcome IN ('win','loss') "
                         "AND (data_source IS NULL OR data_source<>'SIMULATED_OHLC')").fetchone()[0]
        conn.close()
        assert n == 0


def test_master_lifecycle_captures_peak_and_exit_indicators():
    """The Master_Lifecycle schema carries Peak/Exit OsMA/Bulls/Bears — these must be
    persisted as peak_indicators/exit_indicators (seeds the reversal signature), and
    outcome must be derived from BaseExitPts when there is no explicit profit column."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "XAUUSD_Master_Lifecycle.csv")
        header = ["TradeID", "Symbol", "Direction", "EntryTime", "EntryPrice", "EntryOsMA",
                  "EntryBulls", "EntryBears", "ATR_14", "PeakOsMA", "PeakBulls", "PeakBears",
                  "ExitOsMA", "ExitBulls", "ExitBears", "MaxProfitPts", "MaxLossPts", "BaseExitPts"]
        rows = [{"TradeID": "XAU_1", "Symbol": "XAUUSD", "Direction": "LONG", "EntryTime": "2026.05.18 01:05",
                 "EntryPrice": "4551.48", "EntryOsMA": "0.69", "EntryBulls": "5.6", "EntryBears": "2.2",
                 "ATR_14": "3.4", "PeakOsMA": "2.1", "PeakBulls": "8.8", "PeakBears": "4.1",
                 "ExitOsMA": "-0.26", "ExitBulls": "1.5", "ExitBears": "-1.3",
                 "MaxProfitPts": "373", "MaxLossPts": "-567", "BaseExitPts": "150"}]
        _write_csv(csv_path, rows, header)

        db = _mk(d)
        res = GoldSharkImporter(db).ingest_csv(csv_path)
        assert res["resolved"] == 1, res
        conn = sqlite3.connect(os.path.join(d, "t.db"))
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT outcome, mfe_points, mae_points, exit_points, "
                         "peak_indicators, exit_indicators FROM trades").fetchone()
        conn.close()
        assert r["outcome"] == "win"          # derived from BaseExitPts=+150
        assert r["mfe_points"] == 373 and r["mae_points"] == -567
        pk = json.loads(r["peak_indicators"]); ex = json.loads(r["exit_indicators"])
        assert pk["osma"] == 2.1 and pk["bulls_power"] == 8.8
        assert ex["osma"] == -0.26            # OsMA flipped negative at exit (the reversal tell)


def test_ingest_tree_dedupes_by_tradeid():
    """Scanning a tree must dedupe the same TradeID appearing in multiple files, and
    only accept the strict per-trade lifecycle schema."""
    with tempfile.TemporaryDirectory() as d:
        header = ["TradeID", "Symbol", "Direction", "EntryPrice", "EntryOsMA", "PeakOsMA",
                  "ExitOsMA", "MaxProfitPts", "BaseExitPts"]
        row = {"TradeID": "DUP_1", "Symbol": "XAUUSD", "Direction": "LONG", "EntryPrice": "2000",
               "EntryOsMA": "0.3", "PeakOsMA": "0.9", "ExitOsMA": "0.1",
               "MaxProfitPts": "300", "BaseExitPts": "120"}
        os.makedirs(os.path.join(d, "a")); os.makedirs(os.path.join(d, "b"))
        _write_csv(os.path.join(d, "a", "XAUUSD_Master_Lifecycle.csv"), [row], header)
        _write_csv(os.path.join(d, "b", "XAUUSD_Master_Lifecycle.csv"), [row], header)
        db = _mk(d)
        agg = GoldSharkImporter(db).ingest_tree(d)
        assert agg["files"] == 2 and agg["inserted"] == 1 and agg["dupes"] == 1, agg


def test_ingest_tree_rejects_non_lifecycle_schema():
    """A per-BAR ML dump / unified tick log (missing Peak/Exit schema) must be REJECTED,
    not ingested (the pollution that broke the first pass)."""
    with tempfile.TemporaryDirectory() as d:
        # looks like a lifecycle file by name but lacks Peak/Exit columns
        header = ["TradeID", "Symbol", "Direction", "EntryPrice", "MaxProfitPts"]
        rows = [{"TradeID": f"B_{i}", "Symbol": "XAUUSD", "Direction": "LONG",
                 "EntryPrice": "2000", "MaxProfitPts": "3"} for i in range(10)]
        _write_csv(os.path.join(d, "XAUUSD_Master_Lifecycle.csv"), rows, header)
        db = _mk(d)
        agg = GoldSharkImporter(db).ingest_tree(d)
        assert agg["files"] == 0 and agg["inserted"] == 0 and agg["rejected_files"] == 1, agg


if __name__ == "__main__":
    test_import_maps_and_tags_provenance()
    test_import_excludes_lookahead_features()
    test_simulated_ohlc_is_excluded_from_training_query()
    test_master_lifecycle_captures_peak_and_exit_indicators()
    test_ingest_tree_dedupes_by_tradeid()
    test_ingest_tree_rejects_non_lifecycle_schema()
    print("goldshark import tests passed")
