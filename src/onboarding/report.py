"""Onboarding report generation (markdown, HTML, JSON).

The report uses VectorBT's native ``pf.stats()`` output for every candidate — no
hand-rolled metric table. Each candidate's full native stats Series is rendered
verbatim.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.onboarding.metrics import ScoredResult
from src.onboarding.validate import ValidationResult


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if v == float("inf"):
            return "inf"
        if v == float("-inf"):
            return "-inf"
        return f"{v:.4f}"
    return str(v)


def _scored_to_dict(r: ScoredResult) -> Dict:
    return {
        "indicator": r.indicator,
        "library": r.library,
        "category": r.category,
        "session": r.session,
        "timeframe": r.timeframe,
        "score": round(r.score, 4),
        "stats": r.result.stats,  # VectorBT native pf.stats()
    }


def build_report_data(
    symbol: str,
    discovery: Dict[str, List[ScoredResult]],
    tuned: List[Dict],
    validated: List[ValidationResult],
    best_timeframe_per_session: Dict[str, Dict] = None,
) -> Dict:
    """Assemble a per-symbol onboarding report data structure.

    Each discovery entry carries the candidate's native VectorBT ``pf.stats()``
    dict (``result.stats``) plus its composite score. When
    ``best_timeframe_per_session`` is provided, a per-session best-timeframe view
    is included as the primary structure.
    """
    best = best_timeframe_per_session or {}
    return {
        "symbol": symbol,
        "generated_at": datetime.now().isoformat(),
        "best_timeframe_per_session": {
            session: {
                "timeframe": info["timeframe"],
                "results": [_scored_to_dict(r) for r in info["results"]],
            }
            for session, info in best.items()
        },
        "discovery": {
            key: [_scored_to_dict(r) for r in results]
            for key, results in discovery.items()
        },
        "tuned": tuned,
        "validated": [
            {
                "indicator": v.indicator,
                "library": v.library,
                "session": v.session,
                "timeframe": v.timeframe,
                "passed": v.passed,
                "pf_in_sample": round(v.pf_in_sample, 4),
                "pf_out_sample": round(v.pf_out_sample, 4),
                "degradation_pct": round(v.degradation_pct, 2),
                "trades_out_sample": v.trades_out_sample,
                "reason": v.reason,
            }
            for v in validated
        ],
    }


def _markdown(data: Dict) -> str:
    lines = [f"# {data['symbol']} Onboarding Report", ""]
    lines.append(f"Generated: {data['generated_at']}")
    lines.append("")

    lines.append("## Best Timeframe per Session (top indicators)")
    lines.append("")
    best = data.get("best_timeframe_per_session") or {}
    if best:
        for session, info in best.items():
            lines.append(f"### {session} — best timeframe: {info['timeframe']}")
            lines.append("")
            for r in info["results"]:
                lines.append(f"#### {r['indicator']} ({r['library']}, {r['category']})")
                lines.append(f"Composite score: {r['score']}")
                lines.append("")
                stats = r.get("stats") or {}
                if stats:
                    lines.append("| Metric | Value |")
                    lines.append("|---|---|")
                    for name, value in stats.items():
                        lines.append(f"| {name} | {_fmt(value)} |")
                else:
                    lines.append("_No native stats available._")
                lines.append("")
    else:
        lines.append("_No discovery results._")
        lines.append("")

    lines.append("## Walk-Forward Validation")
    lines.append("")
    validated = data.get("validated") or []
    if validated:
        lines.append("| Indicator | Session | Timeframe | Passed | PF IS | PF OOS | Degradation | OOS Trades |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for v in validated:
            lines.append(
                f"| {v['indicator']} | {v['session']} | {v['timeframe']} | {v['passed']} | "
                f"{_fmt(v['pf_in_sample'])} | {_fmt(v['pf_out_sample'])} | "
                f"{v['degradation_pct']}% | {v['trades_out_sample']} |"
            )
    else:
        lines.append("_Not run (discovery-only stage)._")
    lines.append("")

    return "\n".join(lines)


def _html(data: Dict) -> str:
    md = _markdown(data)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{data['symbol']} Onboarding</title></head><body><pre>{md}</pre></body></html>"
    )


def write_reports(
    data: Dict,
    output_dir: Path,
    date: str,
) -> Dict[str, str]:
    """Write md/html/json reports to output_dir. Returns path map."""
    output_dir.mkdir(parents=True, exist_ok=True)
    symbol = data["symbol"]
    base = output_dir / f"{symbol}_onboarding_{date}"

    md_path = base.with_suffix(".md")
    html_path = base.with_suffix(".html")
    json_path = base.with_suffix(".json")

    md_path.write_text(_markdown(data), encoding="utf-8")
    html_path.write_text(_html(data), encoding="utf-8")
    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    return {
        "markdown": str(md_path),
        "html": str(html_path),
        "json": str(json_path),
    }


__all__ = ["build_report_data", "write_reports"]
