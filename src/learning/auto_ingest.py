"""
Auto-ingest: the researcher's "know every file in the datastore" capability.

On each daily research cycle (and startup) this scans data/reprodata/ (and any configured
evidence dirs), detects NEW or CHANGED files against a persisted manifest, reads each one,
and ingests it into the knowledge store / evidence path automatically — so dropping a file
into the datastore makes it part of the researcher's memory with no manual step.

Robust + non-fatal: any single file failing is logged and skipped; the manifest records
what has been seen (path -> mtime+size) so we never re-ingest unchanged files.

Routing by type:
  .csv (goldshark lifecycle telemetry) -> GoldSharkImporter.ingest (trades + signatures)
  .xml (optimiser BT/FT reports)        -> summarized via parse_optimizer_report -> RAG
  .set / .mq5 / .txt / .md              -> text summary -> KnowledgeStore (accumulate)
  .pdf                                  -> filename + location noted in RAG (not parsed)
"""
from __future__ import annotations
import os, json, glob, time, hashlib
from datetime import datetime, timezone

from src.utils.logger import get_logger

logger = get_logger("auto_ingest")

_TEXT_EXT = (".set", ".mq5", ".txt", ".md")
_MAX_TEXT_CHARS = 4000


class DatastoreIngestor:
    def __init__(self, knowledge_store=None, experience_db=None, roots=None):
        self.ks = knowledge_store
        self.db = experience_db
        try:
            from src import config
            data_dir = config.DATA_DIR
        except Exception:
            data_dir = os.path.join(os.getcwd(), "data")
        self.roots = roots or [os.path.join(data_dir, "reprodata")]
        self.manifest_path = os.path.join(data_dir, "reprodata_manifest.json")

    def _load_manifest(self) -> dict:
        try:
            if os.path.exists(self.manifest_path):
                with open(self.manifest_path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_manifest(self, m: dict):
        try:
            tmp = self.manifest_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(m, f)
            os.replace(tmp, self.manifest_path)
        except Exception as e:
            logger.debug(f"manifest save skip: {e}")

    def _sig(self, path: str) -> str:
        try:
            st = os.stat(path)
            return f"{int(st.st_mtime)}:{st.st_size}"
        except Exception:
            return "0:0"

    def scan_and_ingest(self, max_files: int = 200) -> dict:
        """Detect new/changed files and ingest them. Returns a summary. Non-fatal."""
        manifest = self._load_manifest()
        seen = manifest.get("files", {})
        # CHEAP SHORT-CIRCUIT: if the top-level dir mtimes are unchanged since last scan,
        # skip the full recursive walk of the (large) corpus entirely.
        try:
            dir_sig = []
            for root in self.roots:
                for dp, _dn, _fn in os.walk(root):
                    dir_sig.append((dp, int(os.path.getmtime(dp))))
            dir_sig = tuple(sorted(dir_sig))
            if manifest.get("dir_sig") == list(map(list, dir_sig)) and seen:
                return {"new": 0, "ingested": 0, "by_type": {}, "errors": 0, "unchanged": True}
        except Exception:
            dir_sig = None
        new_files = []
        for root in self.roots:
            if not root or not os.path.isdir(root):
                continue
            for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
                if not os.path.isfile(path):
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext not in (".csv", ".xml") + _TEXT_EXT + (".pdf",):
                    continue
                sig = self._sig(path)
                if seen.get(path) == sig:
                    continue  # unchanged
                new_files.append((path, ext, sig))
        summary = {"new": len(new_files), "ingested": 0, "by_type": {}, "errors": 0}
        for path, ext, sig in new_files[:max_files]:
            try:
                self._ingest_one(path, ext)
                seen[path] = sig
                summary["ingested"] += 1
                summary["by_type"][ext] = summary["by_type"].get(ext, 0) + 1
            except Exception as e:
                summary["errors"] += 1
                logger.debug(f"ingest skip {os.path.basename(path)}: {e}")
        manifest["files"] = seen
        manifest["updated"] = datetime.now(timezone.utc).isoformat()
        if dir_sig is not None:
            manifest["dir_sig"] = list(map(list, dir_sig))
        self._save_manifest(manifest)
        if summary["ingested"]:
            logger.warning(f"[AUTO-INGEST] absorbed {summary['ingested']} new/changed datastore "
                           f"files into knowledge: {summary['by_type']}")
        return summary

    def _ingest_one(self, path: str, ext: str):
        name = os.path.basename(path)
        if ext == ".csv":
            self._ingest_csv(path, name)
        elif ext == ".xml":
            self._ingest_xml(path, name)
        elif ext == ".pdf":
            self._remember(f"GoldShark/EA report PDF available at {path} (not text-parsed). "
                           f"Export/convert if its contents are needed.", "note", f"pdf {name}", name)
        else:  # text-like
            self._ingest_text(path, name)

    def _ingest_csv(self, path, name):
        # GoldShark lifecycle telemetry -> trades + signatures (tagged non-live source).
        # The manifest guarantees a given file is only ingested once (unchanged files are
        # skipped), so we don't double-insert across scans.
        try:
            from src.learning.goldshark_import import GoldSharkImporter
            if self.db is not None and ("lifecycle" in name.lower() or "unified" in name.lower()
                                        or "tradelog" in name.lower()):
                imp = GoldSharkImporter(self.db)
                res = imp.ingest_csv(path)
                n = res.get("inserted") if isinstance(res, dict) else res
                if n:
                    self._remember(f"Ingested GoldShark telemetry CSV {name} ({n} rows) into trades "
                                   f"(tagged non-live).", "note", f"telemetry {name}", name)
                return
        except Exception as e:
            logger.debug(f"csv telemetry ingest skip {name}: {e}")
        self._remember(f"Datastore CSV {name} at {path} (not telemetry-shaped; catalogued).",
                       "note", f"csv {name}", name)

    def _ingest_xml(self, path, name):
        # optimiser report -> robust-cluster summary into the RAG
        try:
            from tools.parse_optimizer_report import parse_report, _f
            hdr, passes = parse_report(path)
            robust = [r for r in passes if _f(r, "Profit Factor") >= 1.3
                      and _f(r, "Trades") >= 30 and _f(r, "Profit") > 0]
            pf = sorted(_f(r, "Profit Factor") for r in robust)
            med = pf[len(pf) // 2] if pf else 0
            txt = (f"Optimiser report {name}: {len(passes)} passes, {len(robust)} robust "
                   f"(PF>=1.3,trades>=30,profit>0), median robust PF {med:.2f}. Columns "
                   f"include {sum(1 for c in hdr if str(c).startswith('Inp'))} Inp* params.")
            self._remember(txt, "finding", f"optimiser {name}", name)
        except Exception as e:
            self._remember(f"Optimiser XML {name} at {path} (parse failed: {str(e)[:60]}).",
                           "note", f"xml {name}", name)

    def _ingest_text(self, path, name):
        try:
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                body = f.read(_MAX_TEXT_CHARS)
        except Exception:
            body = ""
        kind = "decision" if name.lower().endswith(".set") else "note"
        self._remember(f"Datastore file {name}: {body[:600]}", kind, f"file {name}", name)

    def _remember(self, text, kind, topic, name):
        if self.ks is None:
            return
        try:
            self.ks.remember(text=text, kind=kind, topic=topic, source="auto_ingest",
                             key=f"datastore_{hashlib.md5(name.encode()).hexdigest()[:12]}",
                             accumulate=False)
        except Exception as e:
            logger.debug(f"remember skip {name}: {e}")
