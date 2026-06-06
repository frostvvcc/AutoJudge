"""
Unified evaluation comparison: aggregates LangSmith experiment results
with static analysis and debate effectiveness metrics.

Usage:
    python -m eval.compare
"""

from __future__ import annotations

import asyncio
import json
import logging

from eval.debate_effectiveness_eval import run_debate_effectiveness_eval
from eval.static_analysis import compare_static_analysis

logger = logging.getLogger(__name__)


async def run_full_comparison() -> dict:
    """Run debate effectiveness evaluation and return unified report."""
    debate_metrics = await run_debate_effectiveness_eval()

    report = {
        "debate_effectiveness": debate_metrics.get("metrics", {}),
        "total_sessions_evaluated": debate_metrics.get("total_sessions", 0),
        "note": (
            "For ablation study and defect detection comparisons, "
            "run: python -m eval.langsmith_experiments"
        ),
    }

    return report


def format_report(report: dict) -> str:
    """Format report for human-readable output."""
    lines = ["=" * 60, "AutoJudge Evaluation Report", "=" * 60, ""]

    metrics = report.get("debate_effectiveness", {})
    if metrics:
        lines.append("Debate Effectiveness Metrics:")
        for key, val in metrics.items():
            if isinstance(val, dict):
                value = val.get("value", "N/A")
                ideal = val.get("ideal_range", "")
                desc = val.get("description", key)
                lines.append(f"  {key}: {value}  (ideal: {ideal})  — {desc}")
            else:
                lines.append(f"  {key}: {val}")
    else:
        lines.append("  No completed debate sessions found.")

    lines.append("")
    lines.append(f"Total sessions evaluated: {report.get('total_sessions_evaluated', 0)}")
    lines.append("")
    lines.append(report.get("note", ""))

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_full_comparison())
    print(format_report(result))
    print("\nRaw JSON:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
