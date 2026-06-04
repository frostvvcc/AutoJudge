from __future__ import annotations

import asyncio
import time
import logging

from app.engine.context import DebateConfig
from app.api.models.response import DebateResult

logger = logging.getLogger(__name__)


class CircuitBreaker:

    def __init__(
        self, failure_threshold: int = 3, recovery_timeout: int = 60
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._state = "closed"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self._state = "open"

    def record_success(self):
        self.failure_count = 0
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open":
            if (
                time.monotonic() - self.last_failure_time
                > self.recovery_timeout
            ):
                return "half-open"
        return self._state


class DegradationManager:

    def __init__(self):
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3, recovery_timeout=60
        )

    async def execute_with_degradation(
        self,
        requirement: str,
        language: str,
        framework: str | None,
        config: DebateConfig,
        on_progress: callable = None,
        api_key: str | None = None,
    ) -> DebateResult:
        # L0: Full adversarial debate via LangGraph
        if self.circuit_breaker.state in ("closed", "half-open"):
            try:
                from app.engine.graph import run_debate_with_graph

                result = await asyncio.wait_for(
                    run_debate_with_graph(
                        requirement=requirement,
                        language=language,
                        framework=framework,
                        config=config,
                        api_key=api_key,
                    ),
                    timeout=120,
                )
                self.circuit_breaker.record_success()
                return result
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("l0_langgraph_failed error=%s", e)
                self.circuit_breaker.record_failure()

        # L1: Reduced attackers via orchestrator (lighter, no graph overhead)
        try:
            from app.engine.orchestrator import DebateOrchestrator
            orchestrator = DebateOrchestrator()

            reduced_config = DebateConfig(
                max_rounds=2,
                attackers=["correctness"],
                model=config.model,
                max_tokens=config.max_tokens,
                skip_cross_review=True,
            )
            result = await asyncio.wait_for(
                orchestrator.run(
                    requirement=requirement,
                    language=language,
                    framework=framework,
                    config=reduced_config,
                    on_progress=on_progress,
                    api_key=api_key,
                ),
                timeout=60,
            )
            result.metadata["degradation_level"] = "L1_PARTIAL"
            return result
        except Exception as e:
            logger.warning("l1_failed error=%s", e)

        # L2: Single agent generation, no debate
        try:
            from app.engine.orchestrator import DebateOrchestrator
            orchestrator = DebateOrchestrator()

            no_debate_config = DebateConfig(
                max_rounds=1,
                attackers=[],
                model=config.model,
                max_tokens=config.max_tokens,
                skip_cross_review=True,
            )
            result = await orchestrator.run(
                requirement=requirement,
                language=language,
                framework=framework,
                config=no_debate_config,
                on_progress=on_progress,
                api_key=api_key,
            )
            result.metadata["degradation_level"] = "L2_SINGLE_AGENT"
            return result
        except Exception as e:
            logger.error("l2_failed error=%s", e)

        # L3: All means exhausted
        return DebateResult(
            code="",
            language=language,
            metadata={"degradation_level": "L3_UNAVAILABLE"},
            convergence_reason="所有降级手段都失败了",
        )
