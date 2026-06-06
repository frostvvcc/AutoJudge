"""
LangSmith-powered ablation experiments for AutoJudge.

Replaces the broken ablation_eval.py / humaneval_runner.py / custom_runner.py
with LangSmith's experiment tracking infrastructure.

Each configuration runs debate via run_debate_with_graph(), and results are
scored by custom evaluators and recorded in the LangSmith dashboard.

Usage:
    python -m eval.langsmith_experiments                     # all configs
    python -m eval.langsmith_experiments --configs full_system no_debate
    python -m eval.langsmith_experiments --max-tasks 3       # quick test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from langsmith import Client

from app.engine.graph import run_debate_with_graph
from app.engine.context import DebateConfig
from eval.langsmith_evaluators import ALL_EVALUATORS

logger = logging.getLogger(__name__)

DATASET_NAME = "autojudge-eval-tasks"

ABLATION_CONFIGS: dict[str, dict] = {
    "full_system": {
        "label": "Full System (baseline)",
        "config": {
            "max_rounds": 5,
            "attackers": ["security", "performance", "correctness"],
            "skip_cross_review": False,
        },
    },
    "no_cross_review": {
        "label": "No Cross-Review",
        "config": {
            "max_rounds": 5,
            "attackers": ["security", "performance", "correctness"],
            "skip_cross_review": True,
        },
    },
    "single_attacker": {
        "label": "Single Attacker (correctness only)",
        "config": {
            "max_rounds": 5,
            "attackers": ["correctness"],
            "skip_cross_review": True,
        },
    },
    "no_debate": {
        "label": "No Debate (single-shot generation)",
        "config": {
            "max_rounds": 1,
            "attackers": [],
            "skip_cross_review": True,
        },
    },
}


async def _run_debate_for_experiment(
    inputs: dict,
    config_dict: dict,
) -> dict:
    """Run a single debate and return outputs for LangSmith."""
    debate_config = DebateConfig(
        max_rounds=config_dict["max_rounds"],
        attackers=config_dict["attackers"],
        skip_cross_review=config_dict.get("skip_cross_review", False),
    )

    start = time.monotonic()
    try:
        result = await run_debate_with_graph(
            requirement=inputs["task"],
            language=inputs.get("language", "python"),
            framework=inputs.get("framework"),
            config=debate_config,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        return {
            "code": result.code or "",
            "metadata": {
                "converged": result.converged,
                "total_rounds": result.metrics.total_rounds if result.metrics else 0,
                "total_tokens": result.metrics.total_tokens if result.metrics else 0,
                "latency_ms": elapsed_ms,
                "confidence": result.confidence or 0.0,
                "cost_usd": result.metrics.cost_usd if result.metrics else 0.0,
            },
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error("Debate failed for task: %s", e)
        return {
            "code": "",
            "metadata": {"error": str(e), "latency_ms": elapsed_ms},
        }


async def run_experiment(
    config_name: str,
    max_tasks: int | None = None,
) -> dict:
    """Run an ablation experiment with LangSmith tracking.

    1. Load dataset from LangSmith (or fall back to local JSON)
    2. Run debate for each example
    3. Score with custom evaluators
    4. Record results in LangSmith
    """
    client = Client()
    ablation = ABLATION_CONFIGS[config_name]
    config_dict = ablation["config"]
    experiment_prefix = f"autojudge-{config_name}"

    datasets = list(client.list_datasets(dataset_name=DATASET_NAME))
    if datasets:
        dataset_name = DATASET_NAME
        logger.info("Using LangSmith dataset: %s", dataset_name)
    else:
        logger.warning(
            "LangSmith dataset '%s' not found. Run `python -m eval.langsmith_datasets upload` first. "
            "Falling back to local tasks.json.",
            DATASET_NAME,
        )
        return await _run_experiment_local(config_name, config_dict, max_tasks)

    async def target(inputs: dict) -> dict:
        return await _run_debate_for_experiment(inputs, config_dict)

    def sync_target(inputs: dict) -> dict:
        return asyncio.run(_run_debate_for_experiment(inputs, config_dict))

    results = client.evaluate(
        sync_target,
        data=dataset_name,
        evaluators=ALL_EVALUATORS,
        experiment_prefix=experiment_prefix,
        max_concurrency=2,
    )

    summary = {
        "config": config_name,
        "label": ablation["label"],
        "experiment_prefix": experiment_prefix,
        "results_url": f"https://smith.langchain.com (search: {experiment_prefix})",
    }

    logger.info("Experiment '%s' completed. View in LangSmith.", experiment_prefix)
    return summary


async def _run_experiment_local(
    config_name: str,
    config_dict: dict,
    max_tasks: int | None = None,
) -> dict:
    """Fallback: run experiment locally without LangSmith dataset."""
    tasks_path = Path(__file__).parent / "datasets" / "tasks.json"
    with open(tasks_path) as f:
        tasks = json.load(f)

    if max_tasks:
        tasks = tasks[:max_tasks]

    from eval.langsmith_evaluators import _check_known_issues

    results = []
    for i, task in enumerate(tasks):
        logger.info("[%s] Task %d/%d: %s", config_name, i + 1, len(tasks), task["id"])
        output = await _run_debate_for_experiment(
            {"task": task["task"], "language": task.get("language", "python"),
             "framework": task.get("framework")},
            config_dict,
        )
        detected = _check_known_issues(output["code"], task.get("known_issues", []))
        detected_count = sum(1 for d in detected if d["detected"])
        total_issues = len(task.get("known_issues", []))

        results.append({
            "task_id": task["id"],
            "detection_rate": round(detected_count / max(total_issues, 1), 4),
            **output.get("metadata", {}),
        })

    valid = [r for r in results if "error" not in r.get("metadata", r)]
    avg_detection = sum(r["detection_rate"] for r in valid) / max(len(valid), 1)
    avg_tokens = sum(r.get("total_tokens", 0) for r in valid) / max(len(valid), 1)
    avg_latency = sum(r.get("latency_ms", 0) for r in valid) / max(len(valid), 1)

    return {
        "config": config_name,
        "label": ABLATION_CONFIGS[config_name]["label"],
        "mode": "local_fallback",
        "tasks_evaluated": len(valid),
        "avg_defect_detection_rate": round(avg_detection, 4),
        "avg_tokens": round(avg_tokens),
        "avg_latency_ms": round(avg_latency),
        "per_task": results,
    }


async def run_all_experiments(
    configs: list[str] | None = None,
    max_tasks: int | None = None,
) -> dict:
    """Run ablation study across multiple configurations."""
    configs = configs or list(ABLATION_CONFIGS.keys())

    logger.info("Starting ablation experiments: configs=%s", configs)
    comparison = {}
    for config_name in configs:
        logger.info("--- Running: %s ---", config_name)
        result = await run_experiment(config_name, max_tasks)
        comparison[config_name] = result

    return {"comparison": comparison}


async def main():
    parser = argparse.ArgumentParser(description="AutoJudge LangSmith Experiments")
    parser.add_argument(
        "--max-tasks", type=int, default=None,
        help="Max tasks per config (default: all)",
    )
    parser.add_argument(
        "--configs", nargs="+",
        choices=list(ABLATION_CONFIGS.keys()), default=None,
        help="Specific configs to run (default: all)",
    )
    args = parser.parse_args()

    report = await run_all_experiments(configs=args.configs, max_tasks=args.max_tasks)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main())
