"""
Compare evaluation results across baseline, single_review, and adversarial modes.
Aggregates custom_runner and static_analysis results into a unified report.
"""

from __future__ import annotations

import asyncio
import json
import logging

from eval.custom_runner import run_evaluation
from eval.static_analysis import compare_static_analysis

logger = logging.getLogger(__name__)


async def run_full_comparison(task_ids: list[str] | None = None) -> dict:
    """Run complete three-mode comparison and return unified report."""
    custom_results = await run_evaluation(task_ids=task_ids)
    return format_report(custom_results)


def format_report(metrics: dict) -> dict:
    report = {"comparison": {}}

    for mode in ["baseline", "single_review", "adversarial"]:
        m = metrics.get(mode, {})
        if "error" in m:
            report["comparison"][mode] = {"error": m["error"]}
            continue

        report["comparison"][mode] = {
            "tasks_evaluated": m.get("task_count", 0),
            "defect_detection_rate": f"{m.get('defect_detection_rate', 0) * 100:.1f}%",
            "detected_out_of_known": f"{m.get('total_detected', 0)}/{m.get('total_known', 0)}",
            "avg_tokens": m.get("avg_tokens", 0),
            "avg_latency_ms": m.get("avg_latency_ms", 0),
            "avg_rounds": m.get("avg_rounds", 1),
            "estimated_cost_usd": m.get("total_cost_usd", 0),
        }

    baseline = metrics.get("baseline", {})
    adversarial = metrics.get("adversarial", {})
    b_rate = baseline.get("defect_detection_rate", 0)
    a_rate = adversarial.get("defect_detection_rate", 0)

    if b_rate > 0:
        improvement = ((a_rate - b_rate) / b_rate) * 100
    else:
        improvement = 0

    report["summary"] = {
        "detection_rate_improvement": f"+{improvement:.1f}%",
        "cost_multiplier": (
            f"{adversarial.get('avg_tokens', 1) / max(baseline.get('avg_tokens', 1), 1):.1f}x"
        ),
        "latency_multiplier": (
            f"{adversarial.get('avg_latency_ms', 1) / max(baseline.get('avg_latency_ms', 1), 1):.1f}x"
        ),
    }

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = asyncio.run(run_full_comparison())
    print(json.dumps(report, indent=2, ensure_ascii=False))
