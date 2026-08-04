# Data Sources Catalogue

> Every data source this project uses, where it lives, how it's ingested, and its
> provenance. Keep this current — a new source or location goes here immediately.

## 1. GoldShark / EA telemetry logs (proven-EA trade history)

The historical trade telemetry from the successful MQL5 EAs (GoldShark family,
EMA_OSMA_ATR). This is the source of the **entry edge** (~85-95% entry-direction
success) and the seed for the reversal-signature + entry-quality learning.

| Location | Content |
|---|---|
| `C:\Users\MartinSharkey\Documents\machine learning\ea_data_archive\{XAUUSD,BTCUSD}\*_Master_Lifecycle_Consolidated.csv` | Cleanest per-trade lifecycle (entry+peak+exit indicators + MFE/MAE). The 95%+ best-config set. |
| `C:\Users\MartinSharkey\AppData\Roaming\MetaQuotes\Terminal\<GUID>\MQL5\Files\*_Master_Lifecycle.csv` | Live-written per-trade lifecycle logs from the running EAs. Primary GUID: `930119AA53207C8778B41171FBFFB46F`. |
| `...\Terminal\<GUID>\MQL5\Files\*_ATR_TM_Lifecycle*.csv` | EMA_OSMA_ATR EA lifecycle logs. |
| `...\Documents\machine learning\` (gemini_analysis, goldshark9_analysis, global_feature_store) | Analysis exports + engineered feature stores. |
| `...\Documents\Langchain\MT5_OLD_EA's\{Goldshark,OrderFlow}\*.mq5` | The EA SOURCE (definitions of FinalMultiplier, IsMomentumFresh, runway, etc). |

**Per-trade lifecycle schema (the one we mine):** `TradeID, Symbol, Direction,
EntryTime, EntryPrice, EntryOsMA, EntryBulls, EntryBears, EMASlope, PriceStretch,
OsMA_Accel, ATR_14, FinalMultiplier, Anticipation_55s, DirTrendAge, DirOsmaSignAge,
Peak{Time,Price,OsMA,Bulls,Bears}, Exit{Time,Price,OsMA,Bulls,Bears}, MaxProfitPts
(MFE), MaxLossPts (MAE), BaseExitPts, ...`

**Ingestion:**
- `src/learning/goldshark_import.py` — `ingest_tree(roots)` mines TRUE per-trade
  lifecycle files (strict: excludes per-bar `_ML`/`IntraCandle`/`Telemetry`/`Unified`
  tick dumps and garbage), dedupes by TradeID, writes into the live `trades` table
  tagged `data_source='SIMULATED_REAL_TICKS'` with peak/exit indicator snapshots.
- `tools/mine_ea_telemetry.py` — read-only miner + incremental entry-gate harness.

**Provenance rule:** tagged `SIMULATED_REAL_TICKS` → INCLUDED in reversal-signature /
entry-quality study, EXCLUDED from ONNX entry-model training (which needs live ticks).
Never ingest the corrupt/huge tick-dump files (they produced phantom MFE).

## 2. CryptoRTI whale signal (Danny) — two channels

| Channel | Location | Use |
|---|---|---|
| **WebSocket push (authoritative)** | `wss://3.213.39.89:8443`, mTLS certs in `langchain/cryptorti/certs/*.pem` | Live event-driven whale signals -> `src/cryptorti/signal_client.py`. Q11 decision: this is the authoritative path. |
| **S3 history** | bucket `crypto-rti-prod-us-east-1` (`cryptorti/.env.cryptorti`: AWS creds) | Historical whale/correlation mining -> `src/cryptorti/s3_client.py`, `correlation_miner.py`. |
| Derived | `data/cryptorti_correlation.json`, `data/whale_outcomes.db` | Mined correlation table + `WhaleOutcomeStore` (live outcomes). Rebuild: `python -m src.cryptorti.correlation_miner` then `python -m src.cryptorti.whale_rag`. |

Whale model: `src/cryptorti/wave_predictor.py` + `whale_rag.py` (ChromaDB
`whale_wave_patterns`). Self-sustaining: grows from live WebSocket events.
Open Danny questions: `cryptorti/martin_qna.md`.

## 3. Live MT5 market data (VT Markets demo)

- Terminal: `Langchain/MT5/VT Markets (Pty) MT5 Terminal/terminal64.exe` (must be
  running + logged in). Account 1176166, server VTMarkets-Demo, GBP.
- Rates/ticks via the `MetaTrader5` Python package (`src/mt5/`, `broker_adapter.py`).
- **One MT5 session per process** — do NOT run a second `mt5.initialize()`/`shutdown()`
  against the same terminal while the engine runs; it clobbers the engine's session
  (symptom: `MT5 not connected / No data for <symbol>`). Restart the engine to recover.

## 4. The bot's own learning stores (generated, machine-local, gitignored)

| Store | Content |
|---|---|
| `data/trading_experience.db` | `trades` table: every live + imported trade, entry snapshot, MFE/MAE, exit_points, peak/exit indicators, `data_source`. The ground truth. |
| `data/edge_weights.json` | Discovered per-symbol edge overlay. **Empty pockets are ignored** (must never block entry). |
| `data/config_checkpoints.json` | Best-known configs + failed directions. |
| `data/chromadb_store/` | Pattern RAG + KnowledgeStore (offline MiniLM). |
| `data/whale_outcomes.db` | Live whale signal -> realised outcome. |
| `data/monitor/live_monitor_*.jsonl` | Live monitor telemetry (entry/manage/exit). |

## Data-hygiene rules (learned the hard way)

1. **Only per-trade lifecycle files** are trade telemetry — never per-bar/tick dumps.
2. **MFE/MAE sanity**: reject values > a few ATR beyond price (phantom-tick guard).
3. **Provenance tagging** on every ingested/recorded trade (`data_source`).
4. **Dedupe by TradeID** across files (the same trade appears in many exports).
5. All `data/` is gitignored + machine-local; a fresh clone re-mines.
