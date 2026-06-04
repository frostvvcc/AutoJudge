from __future__ import annotations

import asyncio
import logging
import time

from app.agents.coder import CoderAgent
from app.agents.security_attacker import SecurityAttacker
from app.agents.performance_attacker import PerformanceAttacker
from app.agents.correctness_attacker import CorrectnessAttacker
from app.agents.judge import JudgeAgent
from app.engine.context import DebateContext, DebateConfig
from app.engine.budget import BudgetManager
from app.engine.consensus import ConsensusDetector
from app.engine.requirement_parser import parse_requirement
from app.api.models.response import (
    DebateResult,
    DebateSummary,
    RiskAssessment,
    DebateMetrics,
)

logger = logging.getLogger(__name__)


ATTACKER_REGISTRY = {
    "security": SecurityAttacker(),
    "performance": PerformanceAttacker(),
    "correctness": CorrectnessAttacker(),
}


class DebateOrchestrator:
    """
    The debate orchestrator — AutoJudge's heart.
    Not a pipeline scheduler, but a debate moderator.
    """

    def __init__(self):
        self.coder = CoderAgent()
        self.judge = JudgeAgent()
        self.consensus_detector = ConsensusDetector()

    async def run(
        self,
        requirement: str,
        language: str = "python",
        framework: str | None = None,
        config: DebateConfig | None = None,
        on_progress: callable = None,
    ) -> DebateResult:
        config = config or DebateConfig()
        context = DebateContext(requirement, config)
        budget = BudgetManager(config.max_tokens)
        start_time = time.monotonic()

        await self._notify(on_progress, {
            "type": "status", "content": "正在理解需求..."
        })

        parsed_req = await parse_requirement(requirement, language, framework)
        context.set_requirement_context(parsed_req)

        await self._notify(on_progress, {
            "type": "status", "content": "需求分析完成，开始对抗..."
        })

        convergence_result = {"converged": False, "status": {}}

        for round_num in range(config.max_rounds):
            context.round = round_num + 1

            if not budget.can_continue(reserve=0.15):
                convergence_result = {
                    "converged": False,
                    "status": {},
                    "reason": "token 预算不足，强制收敛",
                }
                break

            await self._notify(on_progress, {
                "type": "round_start", "round": context.round
            })

            round_messages = await self._execute_round(
                context, budget, on_progress
            )

            await context.compress_early_rounds()

            convergence_result = self.consensus_detector.check_consensus(
                round_messages
            )
            if convergence_result["converged"]:
                await self._notify(on_progress, {
                    "type": "converged",
                    "round": context.round,
                    "reason": "各方达成共识",
                })
                break

        await self._notify(on_progress, {
            "type": "status", "content": "对抗结束，Judge 正在总结..."
        })

        judge_report = await self.judge.summarize(context, budget)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        budget.record_latency(0)

        metrics_raw = budget.get_metrics()

        result = DebateResult(
            code=context.current_code,
            language=language,
            confidence=judge_report.get("confidence", 0.0),
            debate={
                "total_rounds": context.round,
                "converged": convergence_result.get("converged", False),
                "consensus_reason": convergence_result.get(
                    "reason", "各方达成共识" if convergence_result.get("converged") else "达到最大轮次"
                ),
                "transcript": context.get_transcript(),
            },
            summary=DebateSummary(
                total_issues_raised=judge_report.get("total_issues_raised", 0),
                accepted_and_fixed=judge_report.get("accepted_and_fixed", 0),
                rejected_by_coder=judge_report.get("rejected_by_coder", 0),
                suggestions_noted=judge_report.get("suggestions_noted", 0),
                key_improvements=judge_report.get("key_improvements", []),
            ),
            risk_assessment=RiskAssessment(
                security=judge_report.get("risk_security", "unknown"),
                performance=judge_report.get("risk_performance", "unknown"),
                correctness=judge_report.get("risk_correctness", "unknown"),
            ),
            metrics=DebateMetrics(
                total_rounds=context.round,
                total_tokens=metrics_raw["total_tokens"],
                total_latency_ms=elapsed_ms,
                cost_usd=metrics_raw["cost_usd"],
                cache_stats=metrics_raw["cache_stats"],
                tokens_by_agent=metrics_raw["tokens_by_agent"],
            ),
            converged=convergence_result.get("converged", False),
            convergence_reason=convergence_result.get(
                "reason", "各方达成共识" if convergence_result.get("converged") else "达到最大轮次"
            ),
        )

        await self._notify(on_progress, {"type": "done"})

        return result

    async def _execute_round(
        self,
        context: DebateContext,
        budget: BudgetManager,
        on_progress: callable = None,
    ) -> list:
        """
        One round has three stages:
        Stage 1: Coder speaks (respond to attacks + tool-backed rebuttal + fix)
        Stage 2: Attackers attack in parallel
        Stage 3: Cross-review (attackers see each other's findings, supplement/deduplicate)
        """
        round_messages = []

        # Stage 1: Coder speaks
        if context.round == 1:
            coder_prompt = (
                f"根据以下需求生成代码，并简要说明你的设计思路：\n{context.requirement}"
            )
            if context.extra_context:
                coder_prompt += f"\n\n补充需求：{context.extra_context}"
        else:
            coder_prompt = (
                "请回应上一轮各 Attacker 的意见。"
                "对每个攻击：如果合理，承认并修复；如果不合理，给出反驳证据。"
                "如果有修复，贴出完整的新版代码。"
            )

        await self._notify(on_progress, {
            "type": "agent_start", "agent": "coder"
        })

        coder_response = await self.coder.speak(context, coder_prompt, budget)
        context.add_message(
            "coder",
            coder_response.content,
            code=coder_response.code,
            structured=coder_response.structured,
        )
        round_messages.append(context.messages[-1])

        await self._notify(on_progress, {
            "type": "message",
            "agent": "coder",
            "content": coder_response.content,
            "code": coder_response.code,
        })

        # Stage 2: Attackers attack in parallel
        active_attackers = [
            name
            for name in context.config.attackers
            if name not in context.skip_list and name in ATTACKER_REGISTRY
        ]

        if not active_attackers:
            return round_messages

        if context.round == 1:
            attacker_prompt = "审查 Coder 提交的代码，从你的专业角度找出问题。"
        else:
            attacker_prompt = (
                "审查 Coder 的最新修复。如果之前的问题已修复，确认。"
                "如果有新问题，指出。如果没有新问题了，stance 设为 satisfied。"
            )

        async def safe_call_attacker(name: str):
            try:
                await self._notify(on_progress, {
                    "type": "agent_start", "agent": name
                })
                agent = ATTACKER_REGISTRY[name]
                return await agent.speak(context, attacker_prompt, budget)
            except Exception as e:
                logger.warning(
                    "attacker_failed", agent=name, error=str(e)
                )
                return e

        attacker_results = await asyncio.gather(
            *[safe_call_attacker(name) for name in active_attackers]
        )

        succeeded = []
        failed = []
        for result in attacker_results:
            if isinstance(result, Exception):
                failed.append(result)
            else:
                context.add_message(
                    result.agent,
                    result.content,
                    structured=result.structured,
                )
                round_messages.append(context.messages[-1])
                succeeded.append(result)

                await self._notify(on_progress, {
                    "type": "message",
                    "agent": result.agent,
                    "content": result.content,
                })

        if failed:
            fail_note = (
                f"注意：本轮 {len(failed)} 个 Attacker 不可用，"
                f"仅有 {len(succeeded)} 个审查结果。"
            )
            context.add_message("system", fail_note)

        # Stage 3: Cross-review
        if (
            len(succeeded) >= 2
            and not context.config.skip_cross_review
        ):
            findings_summary = self._format_findings(succeeded)

            cross_prompt = (
                f"以下是其他 Attacker 本轮的发现：\n{findings_summary}\n"
                "请补充你认为重要但对方遗漏的观点，或对对方的发现表示支持/质疑。"
                "如果没有补充，直接确认。"
            )

            cross_tasks = []
            for name in active_attackers:
                if name in [r.agent for r in succeeded]:
                    agent = ATTACKER_REGISTRY[name]
                    cross_tasks.append(
                        agent.speak(context, cross_prompt, budget)
                    )

            cross_results = await asyncio.gather(
                *cross_tasks, return_exceptions=True
            )

            for result in cross_results:
                if isinstance(result, Exception):
                    continue
                if result.content.strip():
                    context.add_message(
                        result.agent,
                        f"[交叉审阅] {result.content}",
                        structured=result.structured,
                    )
                    round_messages.append(context.messages[-1])

        return round_messages

    def _format_findings(self, responses) -> str:
        parts = []
        for resp in responses:
            findings_text = resp.content
            if resp.structured and resp.structured.get("findings"):
                findings = resp.structured["findings"]
                items = []
                for f in findings:
                    items.append(
                        f"  - [{f.get('severity', '?')}] {f.get('description', '?')}"
                    )
                findings_text += "\n" + "\n".join(items)
            parts.append(f"[{resp.agent.upper()}]\n{findings_text}")
        return "\n\n".join(parts)

    async def _notify(self, callback, event: dict):
        if callback:
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
