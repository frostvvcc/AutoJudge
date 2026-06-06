"""
Custom LangSmith evaluators for AutoJudge debate quality.

These evaluators are used by langsmith_experiments.py to score debate
outputs across three dimensions: defect detection, security, and
code quality.

Replaces the hand-rolled keyword-matching in the old custom_runner.py
with structured, reproducible evaluation via LangSmith's evaluator API.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import logging
from typing import Any

from langsmith.schemas import Example, Run

logger = logging.getLogger(__name__)

ISSUE_PATTERNS: dict[str, list[str]] = {
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


def _check_known_issues(code: str, known_issues: list[dict]) -> list[dict]:
    """Check how many known issues are addressed in the generated code."""
    code_lower = code.lower()
    detected = []

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


def defect_detection_evaluator(run: Run, example: Example) -> dict:
    """Evaluate what fraction of known issues the generated code addresses.

    Returns a score between 0.0 and 1.0.
    """
    code = (run.outputs or {}).get("code", "")
    known_issues = (example.outputs or {}).get("known_issues", [])

    if not known_issues:
        return {"key": "defect_detection_rate", "score": 1.0}

    detected = _check_known_issues(code, known_issues)
    detected_count = sum(1 for d in detected if d["detected"])
    rate = detected_count / len(known_issues)

    return {
        "key": "defect_detection_rate",
        "score": round(rate, 4),
        "comment": f"{detected_count}/{len(known_issues)} known issues addressed",
    }


def security_score_evaluator(run: Run, example: Example) -> dict:
    """Run bandit on generated code and score by severity-weighted warnings.

    Lower warning count = higher score. Max score 1.0 (zero warnings).
    """
    code = (run.outputs or {}).get("code", "")
    if not code:
        return {"key": "security_score", "score": 0.0}

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                ["bandit", "-r", f.name, "-f", "json", "-q"],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout.strip():
                report = json.loads(result.stdout)
                results = report.get("results", [])
                weighted = sum(
                    3 if r.get("issue_severity") == "HIGH"
                    else 2 if r.get("issue_severity") == "MEDIUM"
                    else 1
                    for r in results
                )
                score = max(0.0, 1.0 - weighted * 0.1)
                return {
                    "key": "security_score",
                    "score": round(score, 4),
                    "comment": f"{len(results)} warnings (weighted: {weighted})",
                }
            return {"key": "security_score", "score": 1.0, "comment": "No warnings"}
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            return {
                "key": "security_score",
                "score": None,
                "comment": f"bandit unavailable: {e}",
            }


def code_quality_evaluator(run: Run, example: Example) -> dict:
    """Evaluate code quality via debate metadata: convergence, rounds, confidence."""
    metadata = (run.outputs or {}).get("metadata", {})
    converged = metadata.get("converged", False)
    rounds = metadata.get("total_rounds", 0)
    confidence = metadata.get("confidence", 0.0)

    score = 0.0
    if converged:
        score += 0.4
    if rounds > 0:
        score += min(0.3, 0.3 * (1.0 / rounds))
    score += confidence * 0.3

    return {
        "key": "code_quality",
        "score": round(min(score, 1.0), 4),
        "comment": (
            f"converged={converged}, rounds={rounds}, confidence={confidence}"
        ),
    }


ALL_EVALUATORS = [
    defect_detection_evaluator,
    security_score_evaluator,
    code_quality_evaluator,
]
