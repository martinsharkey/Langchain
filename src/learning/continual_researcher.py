"""
Continual ReAct Researcher (#32).

Runs on a daily cadence and, per traded symbol, performs a reason -> act ->
observe -> reflect cycle that USES the mql5 knowledge RAG (#22) on an ongoing
basis to improve trading — not a one-off crawl:

  1. REVIEW  live results per symbol (realised expectancy, PF, win rate, recent
             degradation, dominant exit/failure mode) from the experience DB.
  2. QUERY   the mql5 RAG (#22) for that symbol's failure mode -> is there a
             better indicator / parameter direction / technique to try?
  3. REASON  combine (our results + retrieved knowledge) into a concrete,
             testable hypothesis (which knob to move, which regime, why).
  4. ACT     hand validated hypotheses to the SAME walk-forward gate: the
             per-symbol edge-discovery sweep (#31) + param_optimizer. Only
             gate-passing changes go live (the engine already applies the
             overlay + tuned params; the #27 checkpointer keeps/reverts).
  5. REFLECT store every hypothesis + outcome in the KnowledgeStore so learning
             compounds and failed directions aren't retried.

AUTO-FILE GITHUB ISSUES: when the researcher finds something needing CODE (a new
symbol worth adding, a new indicator/technique, an ONNX/ML opportunity, a data
gap), it opens a deduped GitHub issue via `gh` so NO discovery is a dead end.

Cheap + rate-limited (daily), offline-after-fetch, non-fatal. Nothing bypasses
the walk-forward gate.
"""

from __future__ import annotations

import os
import time
import json
import shutil
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("continual_researcher")


class ContinualResearcher:
    def __init__(self, experience_db, mql5_knowledge=None, knowledge_store=None,
                 edge_discovery=None, repo: str = "martinsharkey/Langchain",
                 pattern_optimizer=None, apply_exit_config=None, excursion_analyzer=None,
                 robust_tester=None, optimizer_reports_dir=None,
                 current_params_fn=None, apply_tuned_fn=None, onnx_predictor=None,
                 change_validator=None):
        self.db = experience_db
        self.mql5 = mql5_knowledge
        self.ks = knowledge_store
        self.edge_discovery = edge_discovery
        self.repo = repo
        self._last_run_day = None
        # #40: discover + LOCK IN the MACD-leads-OsMA pattern's best exits per symbol
        self.pattern_optimizer = pattern_optimizer
        self.apply_exit_config = apply_exit_config  # callable(symbol, sl_atr, tp_rr)
        self._pattern_locked = {}
        # #41: per-symbol OsMA-cycle excursion analyzer (how far the symbol moves,
        # peak/trough, wick) -> symbol-specific exit calibration.
        self.excursion_analyzer = excursion_analyzer
        self._excursion = {}
        # #44: robust random-window optimiser (full confluence, mql5 ranges) — the
        # researcher's own discovery loop. Runs on a slow cadence; applies the
        # winning config only if it passes a MAJORITY of random windows.
        self.robust_tester = robust_tester
        self._robust = {}
        # RICH EVIDENCE (GoldShark optimiser BT/FT reports) so the researcher can measure our indicator settings
        # against the historic proven data, not just live trades. All optional/non-fatal:
        #   optimizer_reports_dir: dir of MT5 optimiser SpreadsheetML XMLs (BT/FT).
        #   current_params_fn: callable(symbol) -> live indicator params dict.
        self.optimizer_reports_dir = optimizer_reports_dir or os.path.join(
            "data", "reprodata", "goldshark13", "optimiser_reports")
        self.current_params_fn = current_params_fn
        self.apply_tuned_fn = apply_tuned_fn
        self.onnx_predictor = onnx_predictor
        self.change_validator = change_validator
        self._evidence_cache = {}
        # Single per-symbol EVIDENCE STORE: every BT/FT result (live review, optimiser
        # cluster) is persisted here so ALL testing data lives in one
        # place the researcher reads across sessions. data/symbol_evidence.json.
        try:
            from src import config
            self._evidence_path = os.path.join(config.DATA_DIR, "symbol_evidence.json")
        except Exception:
            self._evidence_path = os.path.join("data", "symbol_evidence.json")

    def _load_evidence_store(self) -> dict:
        try:
            if os.path.exists(self._evidence_path):
                with open(self._evidence_path) as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"evidence store load skip: {e}")
        return {}

    def _save_evidence(self, sym: str, record: dict):
        """Persist one symbol's latest evidence record (append to history, keep last 20)."""
        try:
            store = self._load_evidence_store()
            s = store.setdefault(sym.upper(), {"history": []})
            s["latest"] = record
            s["history"] = (s.get("history", []) + [record])[-20:]
            tmp = self._evidence_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(store, f, indent=1)
            os.replace(tmp, self._evidence_path)
        except Exception as e:
            logger.debug(f"evidence store save skip {sym}: {e}")

    def lock_in_pattern(self, base_symbol: str, resolved: str = None) -> dict:
        """
        #40 CORE: discover the best exit config for the MACD-leads-OsMA pattern on
        this symbol and LOCK IT IN (write to live tuned params). This is how the
        bot auto-finds "let winners run / cut losers early" per symbol. Gated by
        the pattern optimizer's PF/sample gate; the #27 checkpointer then verifies
        realised expectancy and reverts if it doesn't hold up.
        """
        if self.pattern_optimizer is None:
            return {"found": False, "reason": "no pattern optimizer"}
        sym = resolved or base_symbol
        try:
            res = self.pattern_optimizer.discover(sym)
        except Exception as e:
            logger.debug(f"pattern discover skip {base_symbol}: {e}")
            return {"found": False, "reason": str(e)[:80]}
        if not res.get("found"):
            return res
        best = res["best"]
        # write the winning exit config live (sl_atr / tp_rr) if a writer is wired
        if self.apply_exit_config is not None:
            try:
                self.apply_exit_config(base_symbol, best["sl_atr"], best["tp_rr"])
            except Exception as e:
                logger.debug(f"apply exit config skip {base_symbol}: {e}")
        self._pattern_locked[base_symbol.upper()] = best
        logger.warning(f"[PATTERN-LOCK] {base_symbol}: MACD-leads-OsMA best exits "
                       f"sl_atr {best['sl_atr']} tp_rr {best['tp_rr']} "
                       f"({res['alt_filter']} filter, WR {best['win_rate']}% PF {best['profit_factor']}, "
                       f"n {best['trades']}) -> locked into live tuned params")
        if self.ks is not None:
            try:
                self.ks.remember(
                    key=f"pattern_lock_{base_symbol.upper()}", kind="finding",
                    topic=f"pattern exits {base_symbol.upper()}", source="pattern_optimizer",
                    text=(f"{base_symbol.upper()} MACD-leads-OsMA best exits: sl_atr {best['sl_atr']}, "
                          f"tp_rr {best['tp_rr']} ({res['alt_filter']} MTF filter) -> WR {best['win_rate']}% "
                          f"PF {best['profit_factor']} exp {best['expectancy']} over {best['trades']} triggers. "
                          f"Wide-stop/right-TP = let winners run, cut losers early. Locked live; checkpointer verifies."))
            except Exception:
                pass
        return res

    def pattern_snapshot(self) -> dict:
        return dict(self._pattern_locked)

    def measure_excursion(self, base_symbol: str, resolved: str = None) -> dict:
        """#41: measure the symbol's OsMA-cycle excursion (peak/trough/wick) so the
        exit is calibrated to how far THIS symbol actually moves. Stored in the RAG."""
        if self.excursion_analyzer is None:
            return {"found": False}
        try:
            r = self.excursion_analyzer.measure(resolved or base_symbol)
        except Exception as e:
            logger.debug(f"excursion measure skip {base_symbol}: {e}")
            return {"found": False, "reason": str(e)[:80]}
        if r.get("found"):
            self._excursion[base_symbol.upper()] = r
            rec = r["recommendation"]
            # ACTION IT (not just store): apply the excursion-derived exit config
            # LIVE, blended with the pattern-lock config. The #27 checkpointer then
            # verifies realised expectancy and reverts if it doesn't hold up.
            if self.apply_exit_config is not None and rec.get("suggested_sl_atr") and rec.get("suggested_tp_rr"):
                try:
                    self.apply_exit_config(base_symbol, rec["suggested_sl_atr"],
                                           rec["suggested_tp_rr"], source="excursion")
                except TypeError:
                    self.apply_exit_config(base_symbol, rec["suggested_sl_atr"], rec["suggested_tp_rr"])
                except Exception as e:
                    logger.debug(f"excursion apply skip {base_symbol}: {e}")
            if self.ks is not None:
                try:
                    rec = r["recommendation"]
                    self.ks.remember(
                        key=f"excursion_{base_symbol.upper()}", kind="finding",
                        topic=f"excursion {base_symbol.upper()}", source="excursion_analyzer",
                        text=(f"{base_symbol.upper()} OsMA-cycle excursion ({r['osma_cycles']} cycles): "
                              f"median peak-in-favour {r['median_peak_pts']}pts, adverse "
                              f"{r['median_trough_pts']}pts, wick {r['median_wick_pts']}pts, "
                              f"peak/trough {r['peak_to_trough_ratio']}. Exit rec: sl_atr "
                              f"{rec['suggested_sl_atr']}, tp_rr {rec['suggested_tp_rr']} (stop wide "
                              f"enough to survive adverse+wick; TP ~70% of typical peak = exit near "
                              f"OsMA reversal, don't give it back). Entries ~95% correct direction; "
                              f"exit management is the leak."))
                except Exception:
                    pass
        return r

    def excursion_snapshot(self) -> dict:
        return {k: v.get("recommendation") for k, v in self._excursion.items()}

    def validate_hypothesis(self, key: str, claim: str, evidence: dict,
                            verdict: str, confidence: str = "medium") -> dict:
        """
        Record an EXTERNALLY-derived finding (from an analysis script / chat session)
        into the bot's knowledge system as a VALIDATED finding so it isn't lost.
        verdict in {agree, disagree, inconclusive} with supporting `evidence`.
        Stored under a stable key (updates in place); recallable by the researcher /
        DynamicFixer, and overturnable later if new data disagrees.
        """
        rec = {"key": key, "claim": claim, "verdict": verdict,
               "confidence": confidence, "evidence": evidence}
        self._validated = getattr(self, "_validated", {})
        self._validated[key] = rec
        if self.ks is not None:
            try:
                self.ks.remember(
                    key=f"validated_{key}", kind="finding", topic="research validation",
                    source="continual_researcher.validate_hypothesis",
                    text=(f"[{verdict.upper()} / conf {confidence}] {claim} | evidence: {evidence}. "
                          f"Validated research finding; supersede only with new data."))
            except Exception as e:
                logger.debug(f"validate_hypothesis store skip: {e}")
        logger.info(f"[VALIDATE] {key}: {verdict} ({confidence}) -- {claim}")
        return rec

    def validated_snapshot(self) -> dict:
        return dict(getattr(self, "_validated", {}))

    def robust_optimise(self, base_symbol: str, resolved: str = None) -> dict:
        """
        #44: run the FULL-confluence random-window robust optimiser (mql5-doc ranges)
        for this symbol and, if the winning config passes a MAJORITY of random date
        windows (regime-agnostic), APPLY its exit config live + store the finding.
        This is the researcher's own discovery loop, closing to real actions.
        """
        if self.robust_tester is None:
            return {"found": False}
        try:
            payload = self.robust_tester.optimise(resolved or base_symbol)
        except Exception as e:
            logger.debug(f"robust optimise skip {base_symbol}: {e}")
            return {"found": False, "reason": str(e)[:80]}
        rb = (payload or {}).get("final_robustness", {})
        cfg = (payload or {}).get("final_config", {})
        if not cfg or rb.get("pass_rate", 0) < 0.6:
            return {"found": False, "robustness": rb}
        self._robust[base_symbol.upper()] = {"config": cfg, "robustness": rb,
                                              "full_window": payload.get("full_window")}
        # ACTION: apply the robust exit config live (checkpointer then verifies/reverts)
        if self.apply_exit_config is not None and cfg.get("sl_atr") and cfg.get("tp_rr"):
            try:
                self.apply_exit_config(base_symbol, cfg["sl_atr"], cfg["tp_rr"], source="robust")
            except TypeError:
                self.apply_exit_config(base_symbol, cfg["sl_atr"], cfg["tp_rr"])
            except Exception:
                pass
        if self.ks is not None:
            try:
                self.ks.remember(
                    key=f"robust_config_{base_symbol.upper()}", kind="finding",
                    topic=f"robust config {base_symbol.upper()}", source="robust_tester",
                    text=(f"{base_symbol.upper()} full-confluence robust config (mql5-range tuned): "
                          f"pass_rate {rb.get('pass_rate')} median PF {rb.get('median_pf')} across "
                          f"random date windows. sl_atr {cfg.get('sl_atr')} tp_rr {cfg.get('tp_rr')} "
                          f"osma {cfg.get('osma_fast')}/{cfg.get('osma_slow')} ema {cfg.get('ema_period')} "
                          f"power {cfg.get('power_period')} rsi {cfg.get('rsi_period')} "
                          f"min_confluence {cfg.get('min_confluence')}. Applied live; checkpointer verifies."))
            except Exception:
                pass
        return {"found": True, "config": cfg, "robustness": rb}

    def robust_snapshot(self) -> dict:
        return dict(self._robust)

    # ── 1. REVIEW ──
    def review_symbol(self, base_symbol: str, limit: int = 40) -> dict:
        """Summarise recent realised performance + dominant failure mode."""
        import sqlite3
        out = {"symbol": base_symbol.upper(), "n": 0}
        try:
            conn = sqlite3.connect(self.db.db_path)
            conn.row_factory = sqlite3.Row
            q = ("SELECT outcome, profit_loss, exit_reason, strategy_used FROM trades "
                 "WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
                 "AND (exit_reason IS NULL OR exit_reason<>'pre_rebuild_synthetic') ")
            params: list = [base_symbol.upper() + "%"]
            # Restrict to the live OsMA_Confluence era (cutover + recency + OsMA-only) AND
            # exclude ALL simulated sources (the clause now drops SIMULATED_REAL_TICKS too).
            try:
                lw, lp = self.db.learning_window_clause(exclude_sim_ohlc=True)
                q += lw
                params.extend(lp)
            except Exception as _e:
                # Fail-open would silently re-admit simulated/poison data — make it visible.
                logger.warning(f"learning_window_clause failed for {base_symbol}; "
                               f"review runs UNFILTERED this cycle: {_e}")
            q += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, tuple(params)).fetchall()
            conn.close()
        except Exception as e:
            logger.debug(f"review skip {base_symbol}: {e}")
            return out
        n = len(rows)
        if n == 0:
            return out
        wins = sum(1 for r in rows if r["outcome"] == "win")
        pnl = sum((r["profit_loss"] or 0) for r in rows)
        # dominant exit reason (failure mode proxy) among losers
        from collections import Counter
        loss_exits = Counter((r["exit_reason"] or "unknown") for r in rows if r["outcome"] == "loss")
        worst_strats = Counter()
        for r in rows:
            if r["outcome"] == "loss":
                worst_strats[r["strategy_used"] or "unknown"] += 1
        out.update({
            "n": n, "win_rate": round(wins / n * 100, 1),
            "expectancy": round(pnl / n, 4), "net_pnl": round(pnl, 2),
            "dominant_loss_exit": (loss_exits.most_common(1)[0][0] if loss_exits else None),
            "worst_strategy": (worst_strats.most_common(1)[0][0] if worst_strats else None),
        })
        return out

    # ── per-symbol INDICATOR SCALE profiling (indicator values differ hugely by symbol) ──
    def profile_indicator_scale(self, base_symbol: str, resolved: str = None) -> dict:
        """
        Explore a symbol's indicator SCALE so thresholds are calibrated per symbol,
        not copied from gold. Indicator absolute values differ by orders of
        magnitude across symbols (BTC ~63000 vs XAUUSD ~2600), so ATR/OsMA/power
        magnitudes are not comparable. Returns normalised, symbol-relative stats
        (ATR as % of price, median |OsMA| relative to ATR, power ranges) and
        stores them in the KnowledgeStore for the tuner/researcher to use.
        """
        prof = {"symbol": base_symbol.upper()}
        try:
            import statistics
            from src.mt5.data import get_rates
            from src.strategies.indicators import compute_indicator_series
            from src import config as _cfg
            rates = get_rates(resolved or base_symbol, timeframe=_cfg.ENTRY_TIMEFRAME, count=300)
            if not rates or len(rates) < 60:
                return prof
            series = compute_indicator_series(rates, None)
            closes = [b.get("close") for b in series if b.get("close")]
            atrs = [b.get("atr") for b in series if b.get("atr")]
            osmas = [abs(b.get("osma") or 0) for b in series if b.get("close")]
            bulls = [b.get("bulls_power") or 0 for b in series if b.get("close")]
            if closes and atrs:
                med_price = statistics.median(closes)
                med_atr = statistics.median(atrs)
                prof.update({
                    "median_price": round(med_price, 2),
                    "median_atr": round(med_atr, 4),
                    # ATR as % of price -> comparable across symbols
                    "atr_pct_of_price": round(med_atr / med_price * 100, 4) if med_price else 0,
                    "median_abs_osma": round(statistics.median(osmas), 4) if osmas else 0,
                    # OsMA magnitude relative to ATR (symbol-agnostic entry-strength ref)
                    "osma_over_atr": round(statistics.median(osmas) / med_atr, 3) if (osmas and med_atr) else 0,
                    "median_abs_bulls": round(statistics.median([abs(b) for b in bulls]), 4) if bulls else 0,
                })
        except Exception as e:
            logger.debug(f"indicator scale profile skip {base_symbol}: {e}")
            return prof
        if self.ks is not None and prof.get("atr_pct_of_price"):
            try:
                self.ks.remember(
                    key=f"indicator_scale_{base_symbol.upper()}", kind="finding",
                    topic=f"indicator scale {base_symbol.upper()}", source="continual_researcher",
                    text=(f"{base_symbol.upper()} indicator SCALE (calibrate thresholds to THIS, "
                          f"not gold): ATR ~{prof['atr_pct_of_price']}% of price, median |OsMA| "
                          f"{prof['median_abs_osma']} (~{prof.get('osma_over_atr')}x ATR), median "
                          f"|Bulls| {prof.get('median_abs_bulls')}. Absolute indicator values are "
                          f"NOT comparable to other symbols; use ATR-relative / %-of-price gates."))
            except Exception:
                pass
        return prof

    def gold_evidence(self, base_symbol: str) -> dict:
        """Measure our CURRENT live indicator settings against the RICH historic
        evidence: (a) the GoldShark optimiser BACKTEST+FORWARD passes for this symbol
        and (b) a Dukascopy backtest of the current settings. Writes a finding to the
        knowledge store so the bot's tuning is informed by all of it. Fully non-fatal
        and cached per day — never blocks the research cycle."""
        sym = base_symbol.upper()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._evidence_cache.get(sym, {}).get("day") == day:
            return self._evidence_cache[sym]
        ev = {"symbol": sym, "day": day, "optimiser": None, "finding": None}

        # current live params (indicator settings we actually trade)
        cur = None
        try:
            if self.current_params_fn:
                cur = self.current_params_fn(sym)
        except Exception as e:
            logger.debug(f"gold_evidence current_params skip {sym}: {e}")

        # (a) GoldShark optimiser BT/FT robust cluster for this symbol
        try:
            opt = self._optimiser_cluster(sym)
            if opt:
                ev["optimiser"] = opt
        except Exception as e:
            logger.debug(f"gold_evidence optimiser skip {sym}: {e}")

        # compare + write a finding + an ACTIONABLE verdict, and persist to the store
        try:
            live_review = self.review_symbol(base_symbol)
            ev["live"] = {"expectancy": live_review.get("expectancy"),
                          "win_rate": live_review.get("win_rate"), "n": live_review.get("n")}
            ev["verdict"] = self._evidence_verdict(sym, cur, ev["optimiser"], ev["live"])
            ev["finding"] = self._evidence_finding(sym, cur, ev["optimiser"])
            if ev["finding"] and self.ks is not None:
                self.ks.remember(key=f"gold_evidence_{sym}", kind="finding",
                                 topic=f"evidence {sym}", source="continual_researcher",
                                 text=(ev["finding"] + " VERDICT: " + (ev["verdict"] or "insufficient evidence")),
                                 accumulate=True)
        except Exception as e:
            logger.debug(f"gold_evidence finding skip {sym}: {e}")

        self._evidence_cache[sym] = ev
        self._save_evidence(sym, ev)
        return ev

    def _evidence_verdict(self, sym, cur, opt, live) -> Optional[str]:
        """Turn the comparison into something USEFUL: a concrete verdict the bot/optimizer
        can act on. Flags when live under-performs the evidence and points at the lever."""
        if not opt:
            return None
        flags = []
        # live expectancy negative while optimiser cluster is strongly positive
        if live and live.get("expectancy") is not None and live.get("n", 0) >= 10:
            if live["expectancy"] < 0 and opt and opt.get("median_bt_pf", 0) >= 1.3:
                flags.append(
                    f"live expectancy {live['expectancy']} NEGATIVE vs optimiser median PF {opt['median_bt_pf']} "
                    f"— likely EXIT capture (proven entry, leaking exits); test GS_PROVEN exit tuning")
        # current floors below the optimiser robust cluster (too loose) — check all three
        if cur and opt:
            for key, rng_key in (("osma_min_long", "osma_min_long_range"),
                                 ("bulls_min_long", "bulls_min_long_range"),
                                 ("atr_min", "atr_min_range")):
                rng = opt.get(rng_key)
                cv = cur.get(key)
                if rng and cv is not None:
                    lo, hi = rng
                    if cv < lo:
                        flags.append(f"{key} {cv} BELOW optimiser robust range {lo}-{hi} (too loose)")
                    elif cv > hi:
                        flags.append(f"{key} {cv} ABOVE optimiser robust range {lo}-{hi} (too strict)")
        # MISSING config elements: params the GoldShark evidence uses that live config lacks
        if cur and opt and opt.get("evidence_params"):
            expected = {"osma_min_long", "bulls_min_long", "bears_min_long", "atr_min", "atr_max",
                        "min_ema_slope", "osma_max_short", "hard_sl_points", "trail_points"}
            missing = [k for k in expected if k in opt["evidence_params"] and cur.get(k) in (None, "")]
            if missing:
                flags.append(f"MISSING config elements vs GoldShark evidence: {', '.join(sorted(missing))}")
        return " | ".join(flags) if flags else "live settings consistent with evidence"

    def _optimiser_cluster(self, sym: str) -> Optional[dict]:
        """Parse the GoldShark optimiser BT (+FT if present) reports for this symbol and
        return the robust cluster summary: count, median BT PF, and the range of the key
        indicator floors across the top passes. Cheap streaming parse; skipped if the
        reports dir or parser is unavailable."""
        d = self.optimizer_reports_dir
        if not d or not os.path.isdir(d):
            return None
        try:
            from tools.parse_optimizer_report import parse_report, _f
        except Exception:
            return None
        import glob
        # scan the primary optimiser-reports dir AND the mined MT5-install reports dir; a
        # report is used only if its columns map to our params (so BTC/GER40 pick up any of
        # their own exported optimiser XMLs when present, and gracefully get None otherwise —
        # no hard XAU-only gate).
        # scan the primary optimiser-reports dir AND the mined MT5-install reports dir
        # (exported .opt caches land there) — all evidence, R10.
        dirs = [d, os.path.join(os.path.dirname(d.rstrip("/\\")), "mt5_installs", "reports")]
        bts = []
        for dd in dirs:
            if dd and os.path.isdir(dd):
                bts += [p for p in glob.glob(os.path.join(dd, "*.xml"))
                        if "backtest" in os.path.basename(p).lower()]
        # only use reports that actually pertain to THIS symbol (filename match), so BTC/GER40
        # don't get compared against gold's optimiser cluster. Gold aliases: XAU/GOLD.
        aliases = {"XAUUSD": ("xau", "gold"), "GER40": ("ger40", "de40", "dax", "deuidx"),
                   "BTCUSD": ("btc",)}.get(sym, (sym.lower(),))
        sym_bts = [p for p in bts if any(a in os.path.basename(p).lower() for a in aliases)]
        # gold reports here are unlabeled by symbol historically -> treat unlabeled as gold
        if sym.startswith("XAU") and not sym_bts:
            sym_bts = bts
        bts = sym_bts
        if not bts:
            return None
        # pick the largest backtest report (most passes) for the cluster summary
        bt = max(bts, key=lambda p: os.path.getsize(p))
        try:
            hdr, passes = parse_report(bt)
        except Exception:
            return None
        robust = []
        for r in passes:
            pf = _f(r, "Profit Factor"); tr = _f(r, "Trades"); pnl = _f(r, "Profit")
            if pf >= 1.3 and tr >= 30 and pnl > 0:
                robust.append((pf, r))
        if not robust:
            return None
        robust.sort(key=lambda x: x[0], reverse=True)
        top = robust[:50]
        pfs = sorted(pf for pf, _ in top)
        med_pf = pfs[len(pfs) // 2]
        def _rng(key):
            vals = [_f(r, key) for _, r in top if key in r and r.get(key) not in ("", None)]
            vals = [v for v in vals if v != 0.0]
            return (round(min(vals), 3), round(max(vals), 3)) if vals else None
        from tools.goldshark_columns import GOLDSHARK_COLMAP, col_for
        def _rng_param(param):
            c = col_for(param, hdr)
            return _rng(c) if c else None
        return {
            "report": os.path.basename(bt), "robust_passes": len(robust),
            "median_bt_pf": round(med_pf, 2),
            "osma_min_long_range": _rng_param("osma_min_long"),
            "bulls_min_long_range": _rng_param("bulls_min_long"),
            "atr_min_range": _rng_param("atr_min"),
            # canonical map -> which config elements the evidence uses (so the verdict can
            # flag ones our live config is MISSING). Single source of truth (no drift).
            "evidence_params": {p for p in GOLDSHARK_COLMAP if col_for(p, hdr)},
        }

    def _evidence_finding(self, sym, cur, opt) -> Optional[str]:
        """Compose a short, durable finding comparing live settings to the evidence."""
        if not opt:
            return None
        parts = [f"{sym} indicator-setting evidence check:"]
        if cur:
            parts.append(
                f"live osma_min_long={cur.get('osma_min_long')} bulls_min_long={cur.get('bulls_min_long')} "
                f"atr_min={cur.get('atr_min')} floors_raw={cur.get('floors_raw')}.")
        if opt:
            parts.append(
                f"GoldShark optimiser ({opt['report']}): {opt['robust_passes']} robust passes, "
                f"median BT PF {opt['median_bt_pf']}, osma_min_long range {opt.get('osma_min_long_range')}, "
                f"bulls_min_long range {opt.get('bulls_min_long_range')}, atr_min range {opt.get('atr_min_range')}.")
        return " ".join(parts)

    # ── 2+3. QUERY mql5 + REASON ──
    def _recall_prior_findings(self, base_symbol: str, n: int = 5) -> list:
        """Re-read what the researcher has ALREADY learned about this symbol so each
        cycle BUILDS on prior findings instead of regenerating them from scratch (the
        'single pass then forgotten' fix). Returns recent prior finding texts."""
        if self.ks is None:
            return []
        try:
            hits = self.ks.recall(f"research findings hypotheses {base_symbol} expectancy exits",
                                   n_results=n)
            return [h.get("text", "") for h in (hits or []) if h.get("text")]
        except Exception as e:
            logger.debug(f"recall prior findings skip {base_symbol}: {e}")
            return []

    def research_symbol(self, base_symbol: str) -> dict:
        """Review + query mql5 RAG for a better technique; produce a hypothesis.
        BUILDS ON PRIOR FINDINGS: recalls what was already learned about this symbol and
        feeds it into the reasoning so the loop compounds knowledge rather than repeating."""
        review = self.review_symbol(base_symbol)
        # RE-READ prior findings at the START of the cycle so we build on them.
        prior = self._recall_prior_findings(base_symbol)
        # Measure our CURRENT live indicator settings against the RICH historic evidence
        # (GoldShark optimiser BT/FT + Dukascopy backtest). Non-fatal; writes a finding.
        evidence = self.gold_evidence(base_symbol)
        hypothesis = None
        knowledge = []
        if self.mql5 is not None and review.get("n", 0) >= 10:
            # ground the search in the symbol's actual weakness + what we already tried
            prior_note = f" Prior findings: {prior[0][:120]}" if prior else ""
            q = (f"improve {base_symbol} trading: win rate {review.get('win_rate')}% "
                 f"expectancy {review.get('expectancy')}, losers exit via "
                 f"{review.get('dominant_loss_exit')}; better indicator or parameter?{prior_note}")
            try:
                knowledge = self.mql5.research(q, n_results=3)
            except Exception as e:
                logger.debug(f"mql5 research skip {base_symbol}: {e}")
            if knowledge:
                top = knowledge[0]
                hypothesis = (f"{base_symbol}: expectancy {review.get('expectancy')} with "
                              f"losers exiting via {review.get('dominant_loss_exit')}. mql5 "
                              f"knowledge suggests: {top['text'][:160]} "
                              f"(src {top['metadata'].get('title')}). Test via edge sweep + optimizer."
                              + (f" [builds on {len(prior)} prior findings]" if prior else ""))
        result = {"review": review, "knowledge": knowledge, "hypothesis": hypothesis,
                  "evidence": evidence, "prior_findings": prior}
        if hypothesis and self.ks is not None:
            try:
                # ACCUMULATE (don't overwrite) so the trail of findings is preserved.
                self.ks.remember(key=f"research_hypothesis_{base_symbol.upper()}",
                                 kind="note", topic=f"research {base_symbol.upper()}",
                                 source="continual_researcher", text=hypothesis,
                                 accumulate=True)
            except Exception:
                pass
        return result

    # ── AUTO-FILE GITHUB ISSUES ──
    def _gh_available(self) -> bool:
        return shutil.which("gh") is not None

    def _existing_issue_titles(self) -> list[str]:
        if not self._gh_available():
            return []
        try:
            out = subprocess.run(
                ["gh", "issue", "list", "-R", self.repo, "--state", "open",
                 "--limit", "200", "--json", "title"],
                capture_output=True, text=True, timeout=30)
            if out.returncode == 0:
                return [i["title"].lower() for i in json.loads(out.stdout or "[]")]
        except Exception as e:
            logger.debug(f"gh issue list skip: {e}")
        return []

    def file_issue(self, title: str, body: str, labels: list[str] = None) -> Optional[str]:
        """Open a deduped GitHub issue for a development-worthy discovery."""
        if not self._gh_available():
            logger.info(f"[RESEARCHER] gh not available; would file issue: {title}")
            return None
        # dedupe: skip if a very similar title already exists
        existing = self._existing_issue_titles()
        tl = title.lower()
        if any(tl[:40] in e or e[:40] in tl for e in existing):
            logger.info(f"[RESEARCHER] issue already exists (skip): {title}")
            return None
        cmd = ["gh", "issue", "create", "-R", self.repo, "--title", title, "--body", body]
        for lb in (labels or ["research"]):
            cmd += ["--label", lb]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if out.returncode == 0:
                url = (out.stdout or "").strip()
                logger.info(f"[RESEARCHER] filed issue: {url}")
                if self.ks is not None:
                    try:
                        self.ks.remember(key=f"auto_issue_{abs(hash(title)) % 10**8}",
                                         kind="note", topic="auto-filed issue",
                                         source="continual_researcher",
                                         text=f"Filed GitHub issue: {title} -> {url}")
                    except Exception:
                        pass
                return url
            logger.warning(f"[RESEARCHER] gh issue create failed: {out.stderr[:200]}")
        except Exception as e:
            logger.debug(f"gh issue create skip: {e}")
        return None

    # ── daily orchestration ──
    def joint_optimise(self, base_symbol: str, resolved: str = None) -> dict:
        """JOINT evolutionary parameter search over the full space, seeded from the
        GoldShark passes. Slow cadence.
        Applies the winner only if it BEATS the incumbent (walk-forward validated) via
        the injected apply_tuned_fn. Non-fatal; returns {improved, ...}."""
        return {"improved": False, "reason": "dukascopy removed"}

    def daily_cycle(self, symbols: list[str], force: bool = False) -> dict:
        """
        Run the once-per-day ReAct research pass across symbols. Returns a summary.
        Idempotent per UTC day unless force=True.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not force and self._last_run_day == today:
            return {"skipped": True, "reason": "already ran today"}
        self._last_run_day = today
        summary = {"day": today, "symbols": {}, "issues_filed": []}
        # AUTO-INGEST: absorb any NEW/changed files dropped into the datastore into the
        # researcher's knowledge BEFORE reasoning, so every nugget is known + remembered.
        try:
            if not hasattr(self, "_ingestor"):
                from src.learning.auto_ingest import DatastoreIngestor
                self._ingestor = DatastoreIngestor(knowledge_store=self.ks, experience_db=self.db)
            summary["ingest"] = self._ingestor.scan_and_ingest()
        except Exception as e:
            logger.debug(f"auto-ingest skip: {e}")
        # WINNING-CLUSTER awareness: analyse ALL winning combinations (GoldShark profitable
        # passes + checkpointer bests + winning baseline) for the cluster of settings that
        # consistently win, so the researcher KNOWS the winning region and the optimiser
        # builds on it. Remembered to the RAG for continuity.
        try:
            from src.learning.winning_clusters import WinningClusters
            wc = WinningClusters().analyse()
            if wc:
                summary["winning_cluster"] = wc["winning_cluster"]
                if self.ks is not None:
                    c = wc["winning_cluster"]
                    self.ks.remember(
                        key="winning_cluster", kind="finding", topic="winning combinations cluster",
                        source="continual_researcher", accumulate=True,
                        text=(f"WINNING CLUSTER from {wc['n_winning']} winning configs "
                              f"({wc['dominant_cluster_size']} in dominant cluster): "
                              f"osma_min_long~{c.get('osma_min_long')} bulls_min_long~{c.get('bulls_min_long')} "
                              f"atr_min~{c.get('atr_min')} sl_atr~{c.get('sl_atr')} tp_rr~{c.get('tp_rr')}. "
                              f"The optimiser seeds candidates from this winning region; build here "
                              f"if the current model is failing."))
        except Exception as e:
            logger.debug(f"winning-cluster analysis skip: {e}")
        for sym in symbols:
            r = self.research_symbol(sym)
            # per-symbol indicator-scale profiling (calibrate thresholds per symbol)
            scale = self.profile_indicator_scale(sym)
            # #40: discover + lock in the MACD-leads-OsMA pattern's best exits
            pat = self.lock_in_pattern(sym)
            # #41: measure per-symbol OsMA-cycle excursion (calibrate exits to movement)
            exc = self.measure_excursion(sym)
            # #44: full-confluence random-window robust optimisation (mql5 ranges);
            # applies the winning config live if it passes a majority of windows.
            rob = self.robust_optimise(sym)
            # JOINT evolutionary search over the FULL param space, seeded from the
            # GoldShark passes — finds winning COMBINATIONS the greedy tuner cannot.
            # Slow cadence (every Nth day) since it runs many backtests. Non-fatal.
            joint = self.joint_optimise(sym)
            summary["symbols"][sym.upper()] = {
                "expectancy": r["review"].get("expectancy"),
                "hypothesis": bool(r["hypothesis"]),
                "knowledge_hits": len(r["knowledge"]),
                "atr_pct_of_price": scale.get("atr_pct_of_price"),
                "pattern_locked": pat.get("found", False),
                "excursion_peak_pts": (exc.get("median_peak_pts") if exc.get("found") else None),
                "robust_applied": rob.get("found", False),
                "joint_improved": joint.get("improved", False),
            }
            # If a symbol persistently has no edge, propose a development issue
            rv = r["review"]
            if rv.get("n", 0) >= 30 and (rv.get("expectancy") or 0) < 0:
                url = self.file_issue(
                    title=f"[researcher] {sym.upper()} negative expectancy over {rv['n']} trades — investigate technique",
                    body=(f"The continual researcher (#32) found {sym.upper()} at expectancy "
                          f"{rv.get('expectancy')} / WR {rv.get('win_rate')}% over {rv['n']} recent "
                          f"trades; losers dominated by exit '{rv.get('dominant_loss_exit')}', worst "
                          f"strategy '{rv.get('worst_strategy')}'. mql5-grounded hypothesis: "
                          f"{r['hypothesis']}\n\nProposed: run the edge-discovery sweep (#31) + "
                          f"optimizer for this symbol; if no pocket validates, consider a new "
                          f"indicator/technique or ONNX model. Auto-filed; needs review."),
                    labels=["research", "learning"])
                if url:
                    summary["issues_filed"].append(url)
        # kick a validated re-sweep (gate-enforced) if edge discovery is wired
        if self.edge_discovery is not None:
            try:
                self.edge_discovery.sweep_all(symbols, persist=True)
                summary["edge_sweep"] = "ran"
            except Exception as e:
                logger.debug(f"researcher edge sweep skip: {e}")
        return summary
