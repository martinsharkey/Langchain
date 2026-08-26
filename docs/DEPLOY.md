# Deployment — running the bot standalone on a VPS (#14, #19, #1)

The bot is **editor-agnostic** (no VS Code / Kilo runtime dependency) and runs as a single
process via `app.py`, which starts the dashboard (:5000) + engine + research + CryptoRTI feed.

## Platform constraint (important)
The engine trades through **MetaTrader 5** via the `MetaTrader5` Python package, which is
**Windows-only** and requires a running, logged-in MT5 terminal. Therefore the trading
process must run on a **Windows host/VPS** (or MT5 under Wine — untested). A plain Linux
Docker container CANNOT run the trading engine. The learning/research/dashboard components
are cross-platform, but they need the engine's data, so co-locate them on the Windows VPS.

## Windows VPS deployment (recommended)
1. Provision a Windows VPS; install Python 3.12 + the MT5 terminal (VT Markets), log it in.
2. Clone the repo, create the venv, install deps:
   ```
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt
   ```
3. Create `.env` (see AGENTS.md "API keys / configuration") — set `TRADING_MODE=LIVE_MICRO`,
   `LIVE_MICRO_MAX_LOT`, `DISABLED_SYMBOLS`, LLM keys (or `USE_KILO_GATEWAY=false` + a real
   provider key for standalone), and Dukascopy/learning flags.
4. First run rebuilds machine-local data (gitignored): `python -m src.cryptorti.correlation_miner`
   then `python -m src.cryptorti.whale_rag` (only if using the whale feed).
5. Run it: `python app.py LIVE_MICRO` (dashboard at http://localhost:5000).

## Run as a service (survives logoff / auto-restarts) — NSSM
Use NSSM (the Non-Sucking Service Manager) so it runs headless and restarts on crash:
```
nssm install LangchainBot "C:\path\venv\Scripts\python.exe" "C:\path\langchain\app.py" LIVE_MICRO
nssm set LangchainBot AppDirectory "C:\path\langchain"
nssm set LangchainBot AppStdout "C:\path\langchain\logs\service.out.log"
nssm set LangchainBot AppStderr "C:\path\langchain\logs\service.err.log"
nssm set LangchainBot Start SERVICE_AUTO_START
nssm start LangchainBot
```
(Alternatively Windows Task Scheduler "at startup" running `run_bot.bat`.)

## Dashboard as the single control panel (#19)
The Flask dashboard (:5000) writes `data/control.json`; the engine applies it each cycle
(`_apply_control`): change TRADING_MODE, pause/resume entries, toggle scalping, change
`DISABLED_SYMBOLS`. Expose :5000 only over a VPN / SSH tunnel / firewall allowlist — never
open it to the public internet (it can change live trading mode).

## Distributed split (#1, future)
If/when scaling: keep the **engine on the Windows/MT5 host**, and optionally move the
**research/learning + central knowledge store** to a separate host reading a shared
`data/` (or a synced experience DB). The learning half is already decoupled behind
`LEARNING_ADAPTATION_ENABLED` and reads/writes only `data/`, so it can be relocated without
touching the execution path. Not required for single-VPS operation.
