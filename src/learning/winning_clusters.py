"""
Winning-combination CLUSTER analysis.

The researcher should SEE every winning parameter combination we have evidence for and
mine them for the CLUSTER(S) of settings that consistently win — then build new candidates
from that winning region instead of from gold-only seeds or the current (maybe failing)
config. This is the pattern-finding across all winning data.

Winning configs are assembled from ALL evidence:
  1. GoldShark optimiser passes that are profitable (PF >= threshold, enough trades)
  2. the config_checkpointer per-symbol best-known configs (positive realised expectancy)
  3. data/winning_baseline.json (the preserved recent winning combo)
Features are OUR param names via the canonical GOLDSHARK_COLMAP, so clusters are expressed
in the same space the optimiser samples. KMeans finds the winning region(s); the largest /
highest-PF cluster centroid is the "winning cluster" the search seeds from.
"""
from __future__ import annotations
import os, json, glob
from typing import Optional

import numpy as np

from src.utils.logger import get_logger

logger = get_logger("winning_clusters")

# module-level cache (keyed by winning-source signature) so the 6-XML parse + KMeans isn't
# repeated per symbol / per cycle (researcher + each evo optimise() call ask for it).
_CLUSTER_CACHE = {"sig": None, "result": None}


def _data_dir() -> str:
    try:
        from src import config
        return config.DATA_DIR
    except Exception:
        return os.path.join(os.getcwd(), "data")


class WinningClusters:
    def __init__(self, reports_dir: str = None):
        self.reports_dir = reports_dir or os.path.join(
            _data_dir(), "..", "data", "reprodata", "goldshark13", "optimiser_reports") \
            if False else os.path.join("data", "reprodata", "goldshark13", "optimiser_reports")

    def _feature_params(self):
        from tools.goldshark_columns import GOLDSHARK_COLMAP
        return list(GOLDSHARK_COLMAP.keys())

    def _winning_rows(self, feats, min_pf=1.3, min_trades=30) -> list[dict]:
        """Assemble winning parameter vectors (as {param:value}) from all evidence."""
        rows = []
        # 1) GoldShark profitable passes
        try:
            from tools.parse_optimizer_report import parse_report, _f
            from tools.goldshark_columns import value_for, col_for
            bts = []
            for d in (self.reports_dir,
                      os.path.join("data", "reprodata", "mt5_installs", "reports")):
                if os.path.isdir(d):
                    bts += glob.glob(os.path.join(d, "*.xml"))
            for path in sorted(bts, key=lambda p: -os.path.getsize(p))[:6]:
                try:
                    hdr, passes = parse_report(path)
                except Exception:
                    continue
                if sum(1 for p in feats if col_for(p, hdr)) < 4:
                    continue
                for r in passes:
                    if _f(r, "Profit Factor") >= min_pf and _f(r, "Trades") >= min_trades and _f(r, "Profit") > 0:
                        rows.append({p: value_for(p, r, _f) for p in feats})
        except Exception as e:
            logger.debug(f"winning rows goldshark skip: {e}")
        # 2) checkpointer bests (positive expectancy) + 3) winning_baseline
        for fname in ("config_checkpoints.json", "winning_baseline.json"):
            path = os.path.join(_data_dir(), fname)
            if not os.path.exists(path):
                continue
            try:
                blob = json.load(open(path))
            except Exception:
                continue
            configs = []
            if fname == "config_checkpoints.json":
                for sym, v in (blob.items() if isinstance(blob, dict) else []):
                    best = (v or {}).get("best") or {}
                    if isinstance(best, dict) and (best.get("expectancy") or 0) > 0 and best.get("config"):
                        configs.append(best["config"])
            else:
                for _sym, c in (blob.get("checkpointer_best") or {}).items():
                    if isinstance(c, dict) and (c.get("expectancy") or 0) > 0 and c.get("config"):
                        configs.append(c["config"])
            for cfg in configs:
                rows.append({p: float(cfg.get(p, 0.0) or 0.0) for p in feats})
        return rows

    def analyse(self, k: int = 3, min_rows: int = 50) -> Optional[dict]:
        """Cluster the winning configs; return the dominant winning cluster centroid (as
        {param:value}) + summary. None if too little winning evidence."""
        # CACHE: skip the 6-XML parse + KMeans if the winning-source files are unchanged.
        sig = self._sources_sig()
        if _CLUSTER_CACHE["sig"] == sig and _CLUSTER_CACHE["result"] is not None:
            return _CLUSTER_CACHE["result"]
        feats = self._feature_params()
        rows = self._winning_rows(feats)
        if len(rows) < min_rows:
            logger.info(f"winning clusters: only {len(rows)} winning configs — skipping")
            _CLUSTER_CACHE.update(sig=sig, result=None)
            return None
        X = np.array([[r[p] for p in feats] for r in rows], dtype=float)
        try:
            from sklearn.cluster import KMeans
            kk = min(k, max(2, len(rows) // 25))
            km = KMeans(n_clusters=kk, n_init=5, random_state=0).fit(X)
        except Exception as e:
            logger.debug(f"winning clusters kmeans skip: {e}")
            return None
        labels = km.labels_
        # dominant cluster = the one with the most winning members
        import collections
        counts = collections.Counter(labels)
        dom = counts.most_common(1)[0][0]
        centroid = km.cluster_centers_[dom]
        cluster = {p: round(float(centroid[i]), 4) for i, p in enumerate(feats)}
        summary = {
            "n_winning": len(rows), "n_clusters": int(kk),
            "dominant_cluster_size": int(counts[dom]),
            "centroids": [
                {"size": int(counts[c]),
                 "params": {p: round(float(km.cluster_centers_[c][i]), 4) for i, p in enumerate(feats)}}
                for c in sorted(counts, key=lambda c: -counts[c])
            ],
            "winning_cluster": cluster,
        }
        logger.warning(f"[CLUSTERS] {len(rows)} winning configs -> {kk} clusters; dominant "
                       f"({counts[dom]} members) centroid: "
                       f"osma_min_long={cluster.get('osma_min_long')} bulls_min_long={cluster.get('bulls_min_long')} "
                       f"atr_min={cluster.get('atr_min')} sl_atr={cluster.get('sl_atr')} tp_rr={cluster.get('tp_rr')}")
        _CLUSTER_CACHE.update(sig=sig, result=summary)
        return summary

    def _sources_sig(self):
        """Cheap signature of the winning-evidence sources (mtimes/sizes) for caching."""
        import glob
        parts = []
        try:
            for d in (self.reports_dir, os.path.join("data", "reprodata", "mt5_installs", "reports")):
                if os.path.isdir(d):
                    for p in glob.glob(os.path.join(d, "*.xml")):
                        parts.append((p, int(os.path.getmtime(p)), os.path.getsize(p)))
            for fn in ("config_checkpoints.json", "winning_baseline.json"):
                p = os.path.join(_data_dir(), fn)
                if os.path.exists(p):
                    parts.append((p, int(os.path.getmtime(p)), os.path.getsize(p)))
        except Exception:
            return None
        return tuple(sorted(parts))
