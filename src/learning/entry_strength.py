"""
Entry-quality learner (#entry-signal) — mines the per-symbol ENTRY-QUALITY recipe
that maximises ENTRY-DIRECTION success (the ~95% edge the GoldShark / EMA_OSMA_ATR
EAs achieved: the trade went into meaningful profit, i.e. direction was right).

EVIDENCE (full EA telemetry): OsMA/Bulls/Bears STRENGTH magnitude does NOT separate
winners. What DOES lift entry-direction success is a COMBINATION of freshness +
not-over-extended + runway:
  accel_min      OsMA acceleration |osma-osma_prev|/ATR (fresh momentum)
  max_stretch_atr  |close-EMA|/ATR ceiling (not over-extended)
  dom_min        dominant power (Bulls long / Bears short)/ATR
  runway_min     |OsMA| / recent-avg|OsMA| (FinalMultiplier proxy)

The learner greedily selects the gate set that raises entry-success on THIS symbol's
own closed trades, applied ONLY when it beats the base rate on a meaningful sample.
Scale-free (all ATR-normalized) so gold and BTC self-calibrate.
"""
from __future__ import annotations
import json
import os
import sqlite3
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("entry_quality")

# candidate gates: (cfg_key, field, op, value)
_CANDIDATES = [
    ("accel_min", "accel", ">=", 0.02), ("accel_min", "accel", ">=", 0.05), ("accel_min", "accel", ">=", 0.10),
    ("dom_min", "dom", ">=", 0.5), ("dom_min", "dom", ">=", 1.0), ("dom_min", "dom", ">=", 1.5),
    ("max_stretch_atr", "stretch", "<=", 2.0), ("max_stretch_atr", "stretch", "<=", 1.0), ("max_stretch_atr", "stretch", "<=", 0.7),
    ("runway_min", "runway", ">=", 2.0), ("runway_min", "runway", ">=", 3.0),
]


class EntryStrengthLearner:  # name kept for wiring compatibility
    def __init__(self, experience_db, min_sample: int = 40, green_atr: float = 0.3,
                 min_keep_frac: float = 0.15, max_gates: int = 3,
                 min_trades_per_day: float = 4.0, relax_path: str = None):
        self.db = experience_db
        self.min_sample = min_sample
        self.green_atr = green_atr
        self.min_keep_frac = min_keep_frac
        self.max_gates = max_gates
        # NEVER choke: the tuned strength recipe must still leave at least this many
        # entries/day for the symbol, else we keep it looser. This is the balance
        # between entry SUCCESS and stopping trading altogether.
        self.min_trades_per_day = min_trades_per_day
        # STARVATION RELAX: live cap on how high dom_min/runway_min may go per symbol. The
        # engine's live frequency guard lowers this when the bot stops trading, and the
        # per-cycle re-learn must respect it — so the learner cannot re-raise floors above
        # a level that keeps the bot trading. This is the missing downward pressure that
        # lets the bot LEARN to keep itself trading. {symbol: {"dom_min":x,"runway_min":y}}
        # PERSISTED so a restart can't wipe it and let the learner re-raise floors that
        # already starved the bot.
        try:
            from src import config
            self._relax_path = relax_path or os.path.join(config.DATA_DIR, "entry_relax_caps.json")
        except Exception:
            self._relax_path = relax_path or os.path.join("data", "entry_relax_caps.json")
        self._relax_cap = self._load_relax()

    def _load_relax(self) -> dict:
        try:
            if os.path.exists(self._relax_path):
                with open(self._relax_path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_relax(self):
        try:
            tmp = self._relax_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._relax_cap, f)
            os.replace(tmp, self._relax_path)
        except Exception:
            pass

    def relax_for_starvation(self, symbol_prefix: str, step: float = 0.5) -> dict:
        """Called when a symbol's LIVE fire-rate collapses: lower its dom_min/runway_min
        floor cap by one step so entries resume. Returns the new caps. Persisted; the next
        learn_symbol clamps its recipe to these caps. NOT a one-way ratchet — see
        relax_recover(), which raises the cap back when the symbol trades healthily again."""
        key = symbol_prefix.upper().split("-")[0]
        cur = self._relax_cap.get(key, {"dom_min": 1.5, "runway_min": 2.0})
        cur = {"dom_min": max(0.0, round(cur["dom_min"] - step, 2)),
               "runway_min": max(0.0, round(cur["runway_min"] - step, 2))}
        self._relax_cap[key] = cur
        self._save_relax()
        logger.warning(f"[ENTRY-QUALITY] {key}: STARVED -> relaxing floor cap to "
                       f"dom<={cur['dom_min']} runway<={cur['runway_min']} (learning to keep trading)")
        return cur

    def relax_recover(self, symbol_prefix: str, step: float = 0.25,
                      ceiling: dict = None) -> Optional[dict]:
        """Re-tighten path (self-healing): when a symbol is trading healthily again, step the
        relax cap back UP toward the ceiling so the learner may re-raise evidence-backed
        floors it was forced to drop during starvation. Clears the cap once fully recovered
        (no permanent floor deletion). Returns the new cap, or None if nothing to recover."""
        key = symbol_prefix.upper().split("-")[0]
        cur = self._relax_cap.get(key)
        if not cur:
            return None
        ceil = ceiling or {"dom_min": 1.5, "runway_min": 2.0}
        nxt = {"dom_min": round(min(ceil["dom_min"], cur["dom_min"] + step), 2),
               "runway_min": round(min(ceil["runway_min"], cur["runway_min"] + step), 2)}
        if nxt["dom_min"] >= ceil["dom_min"] and nxt["runway_min"] >= ceil["runway_min"]:
            self._relax_cap.pop(key, None)   # fully recovered -> no cap (learner free again)
            self._save_relax()
            logger.warning(f"[ENTRY-QUALITY] {key}: healthy again -> relax cap CLEARED (floors free)")
            return {}
        self._relax_cap[key] = nxt
        self._save_relax()
        logger.info(f"[ENTRY-QUALITY] {key}: recovering -> cap raised to dom<={nxt['dom_min']} runway<={nxt['runway_min']}")
        return nxt

    def _apply_relax_cap(self, symbol_prefix: str, recipe: dict) -> dict:
        """Clamp a learned recipe to the symbol's starvation relax cap (if any)."""
        key = symbol_prefix.upper().split("-")[0]
        cap = self._relax_cap.get(key)
        if cap and recipe:
            if "dom_min" in recipe:
                recipe["dom_min"] = min(recipe["dom_min"], cap["dom_min"])
                if recipe["dom_min"] <= 0:
                    recipe.pop("dom_min", None)
            if "runway_min" in recipe:
                recipe["runway_min"] = min(recipe["runway_min"], cap["runway_min"])
                if recipe["runway_min"] <= 0:
                    recipe.pop("runway_min", None)
        return recipe

    def _samples(self, symbol_prefix: str):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        lw, lp = self.db.learning_window_clause()   # exclude pre-fix era + recency
        rows = [dict(r) for r in conn.execute(
            "SELECT action, mfe_points, atr_value, indicators_snapshot FROM trades "
            "WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
            "AND indicators_snapshot IS NOT NULL" + lw + " ORDER BY id DESC LIMIT 1500",
            tuple([symbol_prefix + "%"] + lp)).fetchall()]
        conn.close()
        out = []
        for r in rows:
            try:
                s = json.loads(r["indicators_snapshot"]) if r["indicators_snapshot"] else {}
            except Exception:
                continue
            atr = float(r["atr_value"] or s.get("atr") or 0)
            mfe = r["mfe_points"]
            if atr <= 0 or mfe is None:
                continue
            close = float(s.get("close") or 0); ema = float(s.get("ema_fast") or s.get("ema") or 0)
            osma = float(s.get("osma") or 0); osma_prev = float(s.get("osma_prev") or 0)
            recent = s.get("osma_recent") or []
            mags = [abs(float(x)) for x in recent if x is not None]
            runway = (abs(osma) / (sum(mags) / len(mags))) if mags else float("nan")
            dom = (float(s.get("bulls_power") or 0) if r["action"] == "buy"
                   else -float(s.get("bears_power") or 0)) / atr
            out.append({
                "green": 1 if mfe >= self.green_atr * atr else 0,
                "accel": abs(osma - osma_prev) / atr,
                "stretch": abs(close - ema) / atr if (close > 0 and ema > 0) else float("nan"),
                "dom": dom, "runway": runway,
                # RAW signed indicator magnitudes at entry (for data-driven floor discovery
                # across ALL separating indicators, not just the 4 above). Side-aware.
                "action": r["action"],
                "osma_raw": osma,
                "macd_raw": float(s.get("macd_line") or 0),
                "bulls_raw": float(s.get("bulls_power") or 0),
                "bears_raw": float(s.get("bears_power") or 0),
            })
        return out

    def discover_indicator_floors(self, samples) -> dict:
        """DATA-DRIVEN: for each entry indicator (osma/macd/bulls/bears), find the strength
        floor that best SEPARATES winners from losers on THIS symbol's own trades, and emit
        the confluence-gate keys (osma_min_long/macd_min_long/bulls_min_long/bears_min_long
        for longs; *_max_short for shorts). This is what lets the learner discover e.g. 'BTC
        winners need MACD>=55' — the gate already consumes these floors. Only emits a floor
        when it MEANINGFULLY lifts green-rate on an adequate kept sample.

        Returns a recipe dict of gate keys (long-side floors; short side mirrors sign)."""
        longs = [s for s in samples if s.get("action") == "buy"]
        shorts = [s for s in samples if s.get("action") == "sell"]
        recipe = {}
        # (raw field, long gate key, short gate key)
        specs = [("osma_raw", "osma_min_long", "osma_max_short"),
                 ("macd_raw", "macd_min_long", "macd_max_short"),
                 ("bulls_raw", "bulls_min_long", "bulls_max_short"),
                 ("bears_raw", "bears_min_long", "bears_max_short")]
        for field, long_key, short_key in specs:
            fl = self._best_floor(longs, field, ">=")
            if fl is not None:
                recipe[long_key] = fl
            fs = self._best_floor(shorts, field, "<=")
            if fs is not None:
                recipe[short_key] = fs
        return recipe

    def _best_floor(self, side_samples, field, op, min_keep_frac: float = 0.25) -> Optional[float]:
        """Find the threshold on `field` (>= for longs, <= for shorts) that maximises
        green-rate while keeping >= min_keep_frac of trades; returns None if no threshold
        beats the base green-rate by >2%. Candidates are the winners' distribution
        percentiles so the floor sits where winners actually are."""
        vals = [(s[field], s["green"]) for s in side_samples if s.get(field) is not None and s[field] == s[field]]
        if len(vals) < self.min_sample:
            return None
        base = sum(g for _, g in vals) / len(vals)
        min_keep = max(20, int(len(vals) * min_keep_frac))
        wins = sorted(v for v, g in vals if g == 1)
        if len(wins) < 20:
            return None
        # candidate thresholds = winner percentiles (25/40/50/60/75)
        cands = sorted({wins[min(len(wins) - 1, int(p * len(wins)))] for p in (0.25, 0.4, 0.5, 0.6, 0.75)})
        best = None
        for thr in cands:
            if op == ">=":
                kept = [(v, g) for v, g in vals if v >= thr]
            else:
                kept = [(v, g) for v, g in vals if v <= thr]
            if len(kept) < min_keep:
                continue
            gr = sum(g for _, g in kept) / len(kept)
            if gr > base + 0.02 and (best is None or gr > best[1]):
                best = (thr, gr)
        return round(best[0], 3) if best else None

    @staticmethod
    def _passes(rec, gate):
        _, field, op, val = gate
        x = rec.get(field)
        if x is None or x != x:   # nan/missing -> permissive
            return True
        return x >= val if op == ">=" else x <= val

    def _rate(self, samples, gates):
        kept = [s for s in samples if all(self._passes(s, g) for g in gates)]
        if not kept:
            return 0.0, 0
        return sum(s["green"] for s in kept) / len(kept), len(kept)

    def learn_symbol(self, symbol_prefix: str) -> Optional[dict]:
        """Learn the per-symbol strength recipe that MAXIMISES entry-direction success
        WITHOUT choking trading below min_trades_per_day. Uses the frequency-vs-quality
        analyzer (which sweeps osma/dom/runway and enforces the trades/day floor) as the
        primary source; falls back to the greedy gate search on older/other data."""
        # Primary: frequency-aware, no-choke recommendation from clean live data.
        try:
            from src.learning.entry_frequency import EntryFrequencyAnalyzer
            fa = EntryFrequencyAnalyzer(self.db, green_atr=self.green_atr)
            a = fa.analyze(symbol_prefix, days=7, min_trades_per_day=self.min_trades_per_day)
            rec = a.get("recommended")
            if rec and a.get("n", 0) >= 20:
                recipe = {}
                if rec["osma_min"] > 0:
                    recipe["osma_strength_min"] = rec["osma_min"]   # legacy key still honored? no-op if unused
                # map to the confluence gate keys
                recipe = {}
                if rec["dom_min"] > 0:
                    recipe["dom_min"] = rec["dom_min"]
                if rec["runway_min"] > 0:
                    recipe["runway_min"] = rec["runway_min"]
                # osma strength alone doesn't gate (proven not to separate); we only
                # carry dom/runway (+ stretch from the greedy pass below if it helps)
                improves = rec["success"] > a["base_success"] + 0.02
                recipe = recipe if improves else {}
                # DATA-DRIVEN multi-indicator floors: discover which of osma/MACD/bulls/bears
                # actually separate winners from losers on THIS symbol and add those gate
                # floors (e.g. BTC's MACD separation). Merged on top of dom/runway.
                try:
                    S = self._samples(symbol_prefix)
                    ind_floors = self.discover_indicator_floors(S)
                    if ind_floors:
                        recipe = {**recipe, **ind_floors}
                except Exception as _e:
                    logger.debug(f"indicator-floor discovery skip {symbol_prefix}: {_e}")
                final_recipe = self._apply_relax_cap(symbol_prefix, recipe)
                return {"recipe": final_recipe,
                        "n": a["n"], "base_success": a["base_success"],
                        "gated_success": rec["success"], "kept": rec["n"],
                        "per_day": rec["per_day"], "improves": bool(improves or ind_floors),
                        "gates": [f"dom>={rec['dom_min']}" if rec["dom_min"] else "",
                                  f"runway>={rec['runway_min']}" if rec["runway_min"] else ""]
                                 + [f"{k}={v}" for k, v in (ind_floors or {}).items()],
                        "source": "frequency_analyzer+indicator_floors"}
        except Exception as e:
            logger.debug(f"frequency analyzer fallback for {symbol_prefix}: {e}")

        # Fallback: greedy gate search over the symbol's own trades.
        S = self._samples(symbol_prefix)
        if len(S) < self.min_sample:
            return None
        base, n = self._rate(S, [])
        min_keep = max(20, int(n * self.min_keep_frac))
        chosen, cur = [], base
        while len(chosen) < self.max_gates:
            best = None
            for g in _CANDIDATES:
                # don't stack two gates on the same key
                if any(c[0] == g[0] for c in chosen):
                    continue
                sr, kept = self._rate(S, chosen + [g])
                if kept >= min_keep and sr > cur + 0.005 and (best is None or sr > best[1]):
                    best = (g, sr, kept)
            if not best:
                break
            chosen.append(best[0]); cur = best[1]
        kept = self._rate(S, chosen)[1]
        improves = bool(chosen) and cur > base + 0.02
        recipe = {}
        if improves:
            for key, _f, _op, val in chosen:
                recipe[key] = val
        recipe = self._apply_relax_cap(symbol_prefix, recipe)
        return {"recipe": recipe, "n": n, "base_success": round(base, 3),
                "gated_success": round(cur, 3), "kept": kept, "improves": improves,
                "gates": [f"{g[1]}{g[2]}{g[3]}" for g in chosen]}

    def learn_all(self, symbol_prefixes) -> dict:
        out = {}
        for s in symbol_prefixes:
            try:
                r = self.learn_symbol(s)
                if r:
                    out[s] = r
                    pd = r.get("per_day")
                    pd_str = f", {pd}/day" if pd is not None else ""
                    logger.info(f"[ENTRY-QUALITY] {s}: {[g for g in r['gates'] if g] or '(base best)'} -> "
                                f"entry-success {r['base_success']*100:.0f}%->{r['gated_success']*100:.0f}% "
                                f"(kept {r['kept']}/{r['n']}{pd_str}, improves={r['improves']})")
            except Exception as e:
                logger.debug(f"entry-quality learn skip {s}: {e}")
        return out
