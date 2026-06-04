from __future__ import annotations

from enum import Enum


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    HARD = "hard"


COMPLEXITY_SIGNALS = {
    "hard": [
        "并发", "concurrent", "锁", "lock", "事务", "transaction",
        "认证", "auth", "密码", "password", "加密", "encrypt",
        "支付", "payment", "金融", "financial",
        "中间件", "middleware", "限流", "rate limit",
        "websocket", "队列", "queue", "分布式", "distributed",
    ],
    "simple": [
        "排序", "sort", "字符串", "string", "转换", "convert",
        "格式化", "format", "计算", "calculate", "工具函数", "utility",
        "hello", "fibonacci", "palindrome",
    ],
}


def route_complexity(requirement: str, parsed_req: dict) -> TaskComplexity:
    text = requirement.lower()

    hard_hits = sum(1 for kw in COMPLEXITY_SIGNALS["hard"] if kw in text)
    simple_hits = sum(1 for kw in COMPLEXITY_SIGNALS["simple"] if kw in text)

    implicit_count = len(parsed_req.get("implicit", []))
    edge_case_count = len(parsed_req.get("edge_cases", []))

    if hard_hits >= 2 or implicit_count >= 3:
        return TaskComplexity.HARD
    if simple_hits >= 2 and hard_hits == 0 and edge_case_count <= 1:
        return TaskComplexity.SIMPLE
    return TaskComplexity.MEDIUM


def get_debate_config(complexity: TaskComplexity) -> dict:
    configs = {
        TaskComplexity.SIMPLE: {
            "max_rounds": 1,
            "attackers": [],
            "skip_cross_review": True,
        },
        TaskComplexity.MEDIUM: {
            "max_rounds": 3,
            "attackers": ["correctness"],
            "skip_cross_review": True,
        },
        TaskComplexity.HARD: {
            "max_rounds": 7,
            "attackers": ["security", "performance", "correctness"],
            "skip_cross_review": False,
        },
    }
    return configs[complexity]
