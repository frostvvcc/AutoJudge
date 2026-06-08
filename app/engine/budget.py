from __future__ import annotations

import asyncio


AGENTS_PER_PHASE = {
    "plan": 1,
    "code_gen": 1,
    "debate": 4,
    "arbitration": 1,
    "judge": 1,
    "reserve": 1,
}


class BudgetManager:
    """
    Token budget management with per-phase allocation and concurrency safety.

    Phase-based budgeting ensures each stage gets a fair share.
    asyncio.Lock prevents parallel Attackers from over-allocating.
    """

    PHASE_BUDGETS = {
        "plan": 0.05,
        "code_gen": 0.20,
        "debate": 0.45,
        "arbitration": 0.15,
        "judge": 0.10,
        "reserve": 0.05,
    }

    def __init__(self, total: int):
        self.total = total
        self.spent = 0
        self.by_agent: dict[str, int] = {}
        self.by_phase: dict[str, int] = {}
        self.agent_limits = {
            "coder": 64000,
            "security": 32000,
            "performance": 32000,
            "correctness": 32000,
            "cross_review": 16000,
            "judge": 32000,
            "arbitrator": 32000,
            "planner": 16000,
            "compressor": 4000,
        }
        self.cache_stats = {"read": 0, "creation": 0}
        self._latency_ms = 0
        self._lock = asyncio.Lock()

    def can_continue(self, reserve: float = 0.15) -> bool:
        return self.spent < self.total * (1 - reserve)

    async def get_max_tokens(self, agent: str, phase: str | None = None) -> int:
        async with self._lock:
            agent_limit = self.agent_limits.get(agent, 4000)
            remaining = self.total - self.spent

            if phase and phase in self.PHASE_BUDGETS:
                phase_total = int(self.total * self.PHASE_BUDGETS[phase])
                phase_spent = self.by_phase.get(phase, 0)
                phase_remaining = max(0, phase_total - phase_spent)
                agents_in_phase = AGENTS_PER_PHASE.get(phase, 1)
                fair_share = max(500, phase_remaining // agents_in_phase)
                return min(agent_limit, fair_share)

            return min(agent_limit, max(500, int(remaining * 0.3)))

    async def record(self, agent: str, tokens: int, phase: str | None = None):
        async with self._lock:
            self.spent += tokens
            self.by_agent[agent] = self.by_agent.get(agent, 0) + tokens
            if phase:
                self.by_phase[phase] = self.by_phase.get(phase, 0) + tokens

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
            "tokens_by_phase": dict(self.by_phase),
            "cache_stats": dict(self.cache_stats),
        }
