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


def check_known_issues(code: str, known_issues: list[dict]) -> list[dict]:
    """Check how many known issues are addressed in the generated code.

    Uses keyword heuristics — checks if the code contains patterns that
    suggest the known issue was handled (e.g., password length validation,
    unique index, error handling).
    """
    ISSUE_PATTERNS = {
        "密码未做最小长度校验": ["len(", "min_length", "password", "长度"],
        "错误信息暴露邮箱是否已注册": ["通用", "generic", "already exists", "注册失败"],
        "邮箱唯一性校验不是原子操作": ["unique", "DuplicateKey", "IntegrityError", "unique_index"],
        "email 字段无索引": ["index", "Index", "create_index", "unique=True"],
        "未处理空列表": ["not ", "if not", "len(", "is None", "empty"],
        "未处理 None 值": ["is None", "is not None", "Optional", "if not"],
        "排序后再过滤": ["filter", "sorted", "先过滤"],
        "SQL 注入": ["parameterized", "%s", "?", "placeholder", "bind"],
        "XSS": ["escape", "sanitize", "html.escape"],
        "JWT secret 硬编码": ["environ", "getenv", "settings", "config"],
        "无登录失败次数限制": ["attempt", "rate_limit", "throttle", "max_attempts"],
        "窗口边界计算 off-by-one": ["<=", ">=", "boundary", "边界"],
        "IP 可被 X-Forwarded-For 伪造": ["real_ip", "trusted_proxies", "X-Real-IP"],
        "非原子操作": ["atomic", "transaction", "lock", "compare_and_swap"],
        "并发": ["Lock", "Semaphore", "asyncio.Lock", "threading"],
        "内存": ["generator", "yield", "stream", "chunk", "batch"],
        "超时": ["timeout", "Timeout", "deadline"],
        "重试": ["retry", "max_retries", "backoff"],
    }

    detected = []
    code_lower = code.lower()

    for issue in known_issues:
        desc = issue["description"]
        found = False
        for pattern_key, keywords in ISSUE_PATTERNS.items():
            if any(kw in desc for kw in pattern_key.split()):
                if any(kw.lower() in code_lower for kw in keywords):
                    found = True
                    break

        if not found:
            for kw in desc.replace("未", "").replace("不", "").split():
                if len(kw) >= 2 and kw.lower() in code_lower:
                    found = True
                    break

        detected.append({**issue, "detected": found})

    return detected


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

                detected = check_known_issues(
                    gen_result.get("code", ""),
                    task.get("known_issues", []),
                )
                detected_count = sum(1 for d in detected if d["detected"])
                total_issues = len(task.get("known_issues", []))

                results[mode].append({
                    "task_id": task["id"],
                    "difficulty": task["difficulty"],
                    "known_issues_count": total_issues,
                    "detected_issues_count": detected_count,
                    "detection_rate": (
                        round(detected_count / total_issues, 2)
                        if total_issues > 0 else 0
                    ),
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
        total_detected = sum(r.get("detected_issues_count", 0) for r in valid)
        total_known = sum(r.get("known_issues_count", 0) for r in valid)

        metrics[mode] = {
            "task_count": len(valid),
            "avg_tokens": round(total_tokens / len(valid)),
            "avg_latency_ms": round(total_latency / len(valid)),
            "avg_rounds": round(avg_rounds, 1),
            "total_cost_usd": round(total_tokens * 9e-6, 2),
            "defect_detection_rate": (
                round(total_detected / total_known, 3) if total_known > 0 else 0
            ),
            "total_detected": total_detected,
            "total_known": total_known,
        }

    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(run_evaluation())
    print(json.dumps(results, indent=2, ensure_ascii=False))
