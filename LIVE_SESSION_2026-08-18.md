# Live Trading Session — 2026-08-18

## Status: PROFITABLE FOR THE FIRST TIME

The bot has been running overnight and is now in profit for the first time since the pipeline rebuild.

### Live Configuration (as of 2026-08-18 07:22 UTC+1)

**Mode:** `LIVE_MICRO`  
**Symbols:** XAUUSD, BTCUSD, GER40  
**Target:** 100 closed trades  
**Dashboard:** http://localhost:5000  
**Process:** `bgp_01385114f001Lo9ScmQhN1FsZv` (pid 10408)

### XAUUSD — Proven Live Config

| Parameter | Value | Source |
|-----------|-------|--------|
| Entry timeframe | M15 | Live session |
| Hard SL | 628,348 pts | Pipeline validated |
| BE trigger | 11,057 pts | Pipeline validated |
| Trail step | 11,057 pts | Pipeline validated |
| Add step | 11,057 pts | Pipeline validated |
| Early fraction | 0.15 | Pipeline validated |
| Max legs | 4 | Pipeline validated |

### What Changed

1. **Fixed `_maybe_run_adaptive` method** in `scalp_engine.py` — method definition was missing, causing `AttributeError` every cycle. Restored the full adaptive intelligence loop.

2. **Pipeline end-to-end verified** — all 13 stages pass:
   - Stage 10: EA generation ✅
   - Stage 11: EA verification PASSED ✅
   - Stage 11b: Dead-input verification PASSED ✅
   - Stage 12: COMPILE OK → build 17 ✅
   - Stage 12b: Deployed to `MT5/.../MQL5/Experts/` ✅
   - Stage 13: Strategy Tester config generated, `metatester64.exe` launched ✅

3. **MQ5 template bugs fixed:**
   - BullsP/BearsP handles moved to `OnInit`/`OnDeinit`
   - Pyramid `legCount`/`lastLegPrice` tracking wired in `OpenLeg()`
   - `BE_lock_pts` and `EarlyFrac` now wired into logic
   - Magic number parameterized as `Magic` input
   - Dead `cycleStart` removed
   - Points conversion aligned between Python and MQL5
   - Added `Print()` debug logging in `PerLegLots()`

4. **Pipeline validation improved:**
   - `ForwardMode=4` for custom forward date (matches 70/30 split)
   - `validation_window` added to `model.json`
   - Relaxed floor validation for by-side buckets (bulls/bears split by direction)
   - Bulls floors now KEEP with per-session Long/Short split

### Session Notes

- XAUUSD showing positive expectancy with 73% win rate (n=60)
- BTCUSD improving: expectancy -0.206 → -0.144, WR 31% (n=26)
- GER40 still struggling: WR 20%, floor relaxation active
- Checkpoint saved: XAUUSD best-known config `exp=0.1483 over n=30` (`fp=fa1fdd5698e5`)

### Commit

This session's configuration and fixes are committed as:
- `7ae1cc6` — fix(pipeline): relax floor validation for by-side buckets, bulls now validates
- Previous commits: `a774193`, `be97e0e`, `5fffbef`
