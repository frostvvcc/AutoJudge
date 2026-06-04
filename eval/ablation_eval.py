"""
Ablation study: compare pass@1 across different system configurations
to measure the contribution of each component.

Configurations:
  1. Full system (baseline)
  2. No cross-review (skip_cross_review=True)
  3. Single attacker (attackers=["correctness"])
  4. No Coder self-test (conceptual - skip test_runner)
  5. No debate (max_rounds=1, attackers=[])

Uses eval/datasets/tasks.json as the test set. Calculates pass@1 with
bootstrap 95% confidence intervals.

Usage:
    python -m eval.ablation_eval
    python -m eval.ablation_eval --max-tasks 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import random
import time
from pathlib import Path

from app.engine.orchestrator import DebateOrchestrator
from app.engine.context import DebateConfig
from eval.custom_runner import check_known_issues

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ablation configurations
# ---------------------------------------------------------------------------

ABLATION_CONFIGS: dict[str, dict] = {
    "full_system": {
        "label": "Full System (baseline)",
        "config": DebateConfig(
            max_rounds=5,
            attackers=["security", "performance", "correctness"],
            skip_cross_review=False,
        ),
        "skip_test_runner": False,
    },
    "no_cross_review": {
        "label": "No Cross-Review",
        "config": DebateConfig(
            max_rounds=5,
            attackers=["security", "performance", "correctness"],
            skip_cross_review=True,
        ),
        "skip_test_runner": False,
    },
    "single_attacker": {
        "label": "Single Attacker (correctness only)",
        "config": DebateConfig(
            max_rounds=5,
            attackers=["correctness"],
            skip_cross_review=True,
        ),
        "skip_test_runner": False,
    },
    "no_self_test": {
        "label": "No Coder Self-Test",
        "config": DebateConfig(
            max_rounds=5,
            attackers=["security", "performance", "correctness"],
            skip_cross_review=False,
        ),
        "skip_test_runner": True,
    },
    "no_debate": {
        "label": "No Debate (single-shot generation)",
        "config": DebateConfig(
            max_rounds=1,
            attackers=[],
            skip_cross_review=True,
        ),
        "skip_test_runner": False,
    },
}


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_eval_tasks(max_tasks: int | None = None) -> list[dict]:
    """Load evaluation tasks from datasets/tasks.json."""
    tasks_path = Path(__file__).parent / "datasets" / "tasks.json"
    with open(tasks_path) as f:
        tasks = json.load(f)
    if max_tasks:
        tasks = tasks[:max_tasks]
    return tasks


# ---------------------------------------------------------------------------
# Single task execution
# ---------------------------------------------------------------------------

async def run_task_with_config(
    task: dict,
    config_name: str,
    ablation: dict,
) -> dict:
    """Run a single task with a given ablation config and return pass/fail."""
    config: DebateConfig = ablation["config"]
    orchestrator = DebateOrchestrator()

    # For "no_self_test" ablation, we monkey-patch the test_runner to skip
    if ablation.get("skip_test_runner"):
        orchestrator.test_runner = _NoOpTestRunner()

    try:
        start = time.monotonic()
        result = await orchestrator.run(
            requirement=task["task"],
            language=task.get("language", "python"),
            framework=task.get("framework"),
            config=config,
        )
        elapsed = time.monotonic() - start

        # Evaluate pass/fail based on known issue detection
        detected = check_known_issues(
            result.code or "",
            task.get("known_issues", []),
        )
        detected_count = sum(1 for d in detected if d["detected"])
        total_issues = len(task.get("known_issues", []))

        # pass@1: code must address at least 50% of known issues
        detection_rate = detected_count / max(total_issues, 1)
        passed = detection_rate >= 0.5

        return {
            "task_id": task["id"],
            "config": config_name,
            "passed": passed,
            "detection_rate": round(detection_rate, 4),
            "detected_count": detected_count,
            "total_issues": total_issues,
            "rounds": result.metrics.total_rounds,
            "tokens": result.metrics.total_tokens,
            "latency_ms": int(elapsed * 1000),
            "converged": result.converged,
        }
    except Exception as e:
        logger.error(
            "Task %s with config %s failed: %s",
            task["id"], config_name, e,
        )
        return {
            "task_id": task["id"],
            "config": config_name,
            "passed": False,
            "error": str(e),
        }


class _NoOpTestRunner:
    """Stub test runner that always returns a passing result."""

    async def verify(self, *args, **kwargs):
        from app.engine.test_runner import VerifyResult
        return VerifyResult(passed=True, reason="Skipped (ablation)")


# ---------------------------------------------------------------------------
# Bootstrap confidence interval
# ---------------------------------------------------------------------------

def bootstrap_ci(
    pass_fail: list[bool],
    n_bootstrap: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> dict:
    """
    Compute pass@1 with bootstrap 95% confidence interval.

    Args:
        pass_fail: list of True/False for each task
        n_bootstrap: number of bootstrap samples
        ci: confidence level (default 0.95)
        seed: random seed for reproducibility

    Returns:
        dict with pass_at_1, ci_lower, ci_upper, n_tasks
    """
    n = len(pass_fail)
    if n == 0:
        return {
            "pass_at_1": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "n_tasks": 0,
        }

    point_estimate = sum(pass_fail) / n

    rng = random.Random(seed)
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = rng.choices(pass_fail, k=n)
        bootstrap_means.append(sum(sample) / n)

    bootstrap_means.sort()
    alpha = 1 - ci
    lower_idx = max(0, int(math.floor(alpha / 2 * n_bootstrap)))
    upper_idx = min(n_bootstrap - 1, int(math.ceil((1 - alpha / 2) * n_bootstrap)))

    return {
        "pass_at_1": round(point_estimate, 4),
        "ci_lower": round(bootstrap_means[lower_idx], 4),
        "ci_upper": round(bootstrap_means[upper_idx], 4),
        "n_tasks": n,
    }


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

async def run_ablation_eval(
    max_tasks: int | None = None,
    configs: list[str] | None = None,
) -> dict:
    """
    Run ablation study and return comparison table as JSON.

    Args:
        max_tasks: limit number of tasks (useful for quick testing)
        configs: list of config names to run (default: all)
    """
    tasks = load_eval_tasks(max_tasks)
    configs = configs or list(ABLATION_CONFIGS.keys())

    logger.info(
        "Starting ablation eval: %d tasks x %d configs = %d runs",
        len(tasks), len(configs), len(tasks) * len(configs),
    )

    all_results: dict[str, list[dict]] = {c: [] for c in configs}

    for config_name in configs:
        ablation = ABLATION_CONFIGS[config_name]
        logger.info(
            "Running config: %s (%s)", config_name, ablation["label"],
        )

        for i, task in enumerate(tasks):
            logger.info(
                "  [%s] Task %d/%d: %s",
                config_name, i + 1, len(tasks), task["id"],
            )
            result = await run_task_with_config(task, config_name, ablation)
            all_results[config_name].append(result)

    # Compute aggregate metrics with confidence intervals
    comparison = {}
    for config_name in configs:
        results = all_results[config_name]
        valid = [r for r in results if "error" not in r]
        pass_fail = [r["passed"] for r in valid]

        ci_result = bootstrap_ci(pass_fail)

        total_tokens = sum(r.get("tokens", 0) for r in valid)
        total_latency = sum(r.get("latency_ms", 0) for r in valid)
        avg_rounds = (
            sum(r.get("rounds", 1) for r in valid) / max(len(valid), 1)
        )
        converged_count = sum(1 for r in valid if r.get("converged", False))

        comparison[config_name] = {
            "label": ABLATION_CONFIGS[config_name]["label"],
            **ci_result,
            "avg_detection_rate": round(
                sum(r.get("detection_rate", 0) for r in valid) / max(len(valid), 1),
                4,
            ),
            "avg_tokens": round(total_tokens / max(len(valid), 1)),
            "avg_latency_ms": round(total_latency / max(len(valid), 1)),
            "avg_rounds": round(avg_rounds, 2),
            "convergence_rate": round(
                converged_count / max(len(valid), 1), 4
            ),
            "errors": len(results) - len(valid),
        }

    # Compute deltas relative to full_system
    if "full_system" in comparison:
        baseline_pass = comparison["full_system"]["pass_at_1"]
        for config_name, metrics in comparison.items():
            if config_name == "full_system":
                metrics["delta_pass_at_1"] = 0.0
            else:
                delta = metrics["pass_at_1"] - baseline_pass
                metrics["delta_pass_at_1"] = round(delta, 4)

    return {
        "total_tasks": len(tasks),
        "configs_evaluated": configs,
        "comparison": comparison,
        "per_task_results": all_results,
    }


async def main():
    """Entry point for running the ablation study."""
    parser = argparse.ArgumentParser(description="AutoJudge Ablation Study")
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to evaluate (default: all)",
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        choices=list(ABLATION_CONFIGS.keys()),
        default=None,
        help="Specific configs to run (default: all)",
    )
    args = parser.parse_args()

    report = await run_ablation_eval(
        max_tasks=args.max_tasks,
        configs=args.configs,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main())
