from __future__ import annotations


class BudgetManager:
    """
    Token budget management with per-agent limits.
    Prevents any single agent from consuming the majority of the budget.
    """

    def __init__(self, total: int):
        self.total = total
        self.spent = 0
        self.by_agent: dict[str, int] = {}
        self.agent_limits = {
            "coder": 4000,
            "security": 2000,
            "performance": 2000,
            "correctness": 2000,
            "cross_review": 1000,
            "judge": 3000,
        }
        self.cache_stats = {"read": 0, "creation": 0}
        self._latency_ms = 0

    def can_continue(self, reserve: float = 0.15) -> bool:
        return self.spent < self.total * (1 - reserve)

    def get_max_tokens(self, agent: str) -> int:
        agent_limit = self.agent_limits.get(agent, 2000)
        remaining = self.total - self.spent
        return min(agent_limit, max(500, int(remaining * 0.4)))

    def record(self, agent: str, tokens: int):
        self.spent += tokens
        self.by_agent[agent] = self.by_agent.get(agent, 0) + tokens

    def record_cache(self, agent: str, cache_read: int, cache_creation: int):
        self.cache_stats["read"] += cache_read
        self.cache_stats["creation"] += cache_creation

    def record_latency(self, ms: int):
        self._latency_ms += ms

    def remaining(self) -> int:
        return max(0, self.total - self.spent)

    def get_metrics(self) -> dict:
        sonnet_input_rate = 3.0 / 1_000_000
        sonnet_output_rate = 15.0 / 1_000_000
        estimated_cost = self.spent * (sonnet_input_rate + sonnet_output_rate) / 2

        return {
            "total_tokens": self.spent,
            "total_latency_ms": self._latency_ms,
            "cost_usd": round(estimated_cost, 4),
            "tokens_by_agent": dict(self.by_agent),
            "cache_stats": dict(self.cache_stats),
        }
