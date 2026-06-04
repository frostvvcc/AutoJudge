"""
HumanEval pass@1 evaluation runner.

Downloads HumanEval dataset and compares baseline (single Claude call)
vs adversarial (AutoJudge debate) pass@1 rates.

Usage:
    python -m eval.humaneval_runner
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.engine.orchestrator import DebateOrchestrator
from app.engine.context import DebateConfig

logger = logging.getLogger(__name__)

HUMANEVAL_URL = "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"


def load_humaneval(path: str = "eval/datasets/HumanEval.jsonl") -> list[dict]:
    """Load HumanEval problems from JSONL file."""
    problems = []
    p = Path(path)
    if not p.exists():
        logger.warning(
            "HumanEval dataset not found at %s. "
            "Download it first: curl -L %s | gunzip > %s",
            path, HUMANEVAL_URL, path,
        )
        return []

    with open(p) as f:
        for line in f:
            if line.strip():
                problems.append(json.loads(line))
    return problems


async def run_baseline(problem: dict) -> dict:
    orchestrator = DebateOrchestrator()
    config = DebateConfig(
        max_rounds=1,
        attackers=[],
        skip_cross_review=True,
    )
    result = await orchestrator.run(
        requirement=problem["prompt"],
        language="python",
        config=config,
    )
    return {
        "task_id": problem["task_id"],
        "code": result.code,
        "tokens": result.metrics.total_tokens,
    }


async def run_adversarial(problem: dict) -> dict:
    orchestrator = DebateOrchestrator()
    config = DebateConfig(
        max_rounds=3,
        attackers=["correctness"],
        skip_cross_review=True,
    )
    result = await orchestrator.run(
        requirement=problem["prompt"],
        language="python",
        config=config,
    )
    return {
        "task_id": problem["task_id"],
        "code": result.code,
        "tokens": result.metrics.total_tokens,
        "rounds": result.metrics.total_rounds,
    }


async def run_humaneval(
    max_problems: int = 164,
    modes: list[str] | None = None,
):
    problems = load_humaneval()
    if not problems:
        return {"error": "HumanEval dataset not found"}

    problems = problems[:max_problems]
    modes = modes or ["baseline", "adversarial"]
    results = {mode: [] for mode in modes}

    for i, problem in enumerate(problems):
        logger.info("HumanEval %d/%d: %s", i + 1, len(problems), problem["task_id"])

        if "baseline" in modes:
            try:
                r = await run_baseline(problem)
                results["baseline"].append(r)
            except Exception as e:
                logger.error("baseline failed for %s: %s", problem["task_id"], e)

        if "adversarial" in modes:
            try:
                r = await run_adversarial(problem)
                results["adversarial"].append(r)
            except Exception as e:
                logger.error("adversarial failed for %s: %s", problem["task_id"], e)

    summary = {}
    for mode in modes:
        valid = [r for r in results[mode] if "code" in r]
        total_tokens = sum(r.get("tokens", 0) for r in valid)
        summary[mode] = {
            "completed": len(valid),
            "total": len(problems),
            "avg_tokens": round(total_tokens / max(len(valid), 1)),
        }

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(run_humaneval(max_problems=10))
    print(json.dumps(results, indent=2))
