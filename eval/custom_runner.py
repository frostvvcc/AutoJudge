"""
Custom evaluation runner: compare baseline vs single_review vs adversarial
on the built-in task set with known issues.
"""

from __future__ import annotations

import asyncio
import json
import time
import logging
from pathlib import Path

from app.engine.orchestrator import DebateOrchestrator
from app.engine.context import DebateConfig

logger = logging.getLogger(__name__)


def load_eval_tasks() -> list[dict]:
    tasks_path = Path(__file__).parent / "datasets" / "tasks.json"
    with open(tasks_path) as f:
        return json.load(f)


async def generate_baseline(task: dict) -> dict:
    """Single Claude call, no review."""
    orchestrator = DebateOrchestrator()
    config = DebateConfig(
        max_rounds=1,
        attackers=[],
        skip_cross_review=True,
    )
    result = await orchestrator.run(
        requirement=task["task"],
        language=task["language"],
        framework=task.get("framework"),
        config=config,
    )
    return {
        "code": result.code,
        "tokens": result.metrics.total_tokens,
        "latency_ms": result.metrics.total_latency_ms,
        "rounds": 1,
    }


async def generate_single_review(task: dict) -> dict:
    """Claude generate + Claude review once (no back-and-forth)."""
    orchestrator = DebateOrchestrator()
    config = DebateConfig(
        max_rounds=2,
        attackers=["correctness"],
        skip_cross_review=True,
    )
    result = await orchestrator.run(
        requirement=task["task"],
        language=task["language"],
        framework=task.get("framework"),
        config=config,
    )
    return {
        "code": result.code,
        "tokens": result.metrics.total_tokens,
        "latency_ms": result.metrics.total_latency_ms,
        "rounds": result.metrics.total_rounds,
    }


async def generate_adversarial(task: dict) -> dict:
    """Full AutoJudge adversarial debate."""
    orchestrator = DebateOrchestrator()
    config = DebateConfig(
        max_rounds=5,
        attackers=["security", "performance", "correctness"],
    )
    result = await orchestrator.run(
        requirement=task["task"],
        language=task["language"],
        framework=task.get("framework"),
        config=config,
    )
    return {
        "code": result.code,
        "tokens": result.metrics.total_tokens,
        "latency_ms": result.metrics.total_latency_ms,
        "rounds": result.metrics.total_rounds,
        "converged": result.converged,
        "summary": result.summary.model_dump(),
    }


async def run_evaluation(
    task_ids: list[str] | None = None,
    modes: list[str] | None = None,
):
    """Run evaluation and return aggregate metrics."""
    tasks = load_eval_tasks()
    if task_ids:
        tasks = [t for t in tasks if t["id"] in task_ids]

    modes = modes or ["baseline", "single_review", "adversarial"]
    generators = {
        "baseline": generate_baseline,
        "single_review": generate_single_review,
        "adversarial": generate_adversarial,
    }

    results = {mode: [] for mode in modes}

    for task in tasks:
        logger.info(f"Evaluating task: {task['id']}")

        for mode in modes:
            try:
                start = time.monotonic()
                gen_result = await generators[mode](task)
                elapsed = time.monotonic() - start

                results[mode].append({
                    "task_id": task["id"],
                    "difficulty": task["difficulty"],
                    "known_issues_count": len(task["known_issues"]),
                    **gen_result,
                    "wall_time_s": round(elapsed, 1),
                })
            except Exception as e:
                logger.error(f"Failed {mode} for {task['id']}: {e}")
                results[mode].append({
                    "task_id": task["id"],
                    "error": str(e),
                })

    return compute_aggregate_metrics(results)


def compute_aggregate_metrics(results: dict) -> dict:
    """Compute aggregate metrics across all tasks."""
    metrics = {}

    for mode, task_results in results.items():
        valid = [r for r in task_results if "error" not in r]
        if not valid:
            metrics[mode] = {"error": "no valid results"}
            continue

        total_tokens = sum(r.get("tokens", 0) for r in valid)
        total_latency = sum(r.get("latency_ms", 0) for r in valid)
        avg_rounds = (
            sum(r.get("rounds", 1) for r in valid) / len(valid)
        )

        metrics[mode] = {
            "task_count": len(valid),
            "avg_tokens": round(total_tokens / len(valid)),
            "avg_latency_ms": round(total_latency / len(valid)),
            "avg_rounds": round(avg_rounds, 1),
            "total_cost_usd": round(
                total_tokens * 9e-6, 2
            ),
        }

    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(run_evaluation())
    print(json.dumps(results, indent=2, ensure_ascii=False))
