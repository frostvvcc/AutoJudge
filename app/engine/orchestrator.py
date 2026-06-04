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
from app.engine.complexity_router import route_complexity, get_debate_config
from app.engine.test_runner import TestRunner
from app.memory.attack_knowledge import AttackKnowledgeBase
from app.memory.user_preferences import UserPreferenceStore
from app.memory.fix_patterns import FixPatternStore
from app.tracing.metrics import record_debate_complete, record_agent_call
from app.api.models.response import (
    DebateResult,
    DebateSummary,
    RiskAssessment,
    DebateMetrics,
    QualityReport,
)

logger = logging.getLogger(__name__)


ATTACKER_REGISTRY = {
    "security": SecurityAttacker(),
    "performance": PerformanceAttacker(),
    "correctness": CorrectnessAttacker(),
}


class DebateOrchestrator:

    def __init__(self, redis_client=None):
        from app.db.redis import get_redis
        resolved_redis = redis_client or get_redis()
        self.coder = CoderAgent()
        self.judge = JudgeAgent()
        self.consensus_detector = ConsensusDetector()
        self.test_runner = TestRunner()
        self.attack_kb = AttackKnowledgeBase()
        self.user_prefs = UserPreferenceStore(resolved_redis)
        self.fix_patterns = FixPatternStore()
        self._live_extra_context: str | None = None

    async def run(
        self,
        requirement: str,
        language: str = "python",
        framework: str | None = None,
        config: DebateConfig | None = None,
        on_progress: callable = None,
        api_key: str | None = None,
    ) -> DebateResult:
        config = config or DebateConfig()
        start_time = time.monotonic()

        await self._notify(on_progress, {
            "type": "status", "content": "正在理解需求..."
        })

        parsed_req = await parse_requirement(requirement, language, framework)

        # --- ComplexityRouter: adjust config based on task complexity ---
        complexity = route_complexity(requirement, parsed_req)
        complexity_config = get_debate_config(complexity)
        if config.max_rounds == DebateConfig().max_rounds:
            config.max_rounds = complexity_config["max_rounds"]
        if config.attackers == DebateConfig().attackers:
            config.attackers = complexity_config["attackers"]
        if complexity_config.get("skip_cross_review"):
            config.skip_cross_review = True

        context = DebateContext(requirement, config)
        budget = BudgetManager(config.max_tokens)
        context.set_requirement_context(parsed_req)

        # --- Memory Layer 1: retrieve attack experiences ---
        experiences = await self.attack_kb.retrieve_relevant(requirement)
        if experiences:
            context.set_experience_context(
                self.attack_kb.build_experience_prompt(experiences)
            )

        # --- Memory Layer 2: load user preferences ---
        if api_key:
            prefs = await self.user_prefs.get_preferences(api_key)
            if prefs:
                context.set_preference_context(
                    self.user_prefs.build_preference_prompt(prefs)
                )

        await self._notify(on_progress, {
            "type": "status",
            "content": f"需求分析完成（复杂度: {complexity.value}），开始对抗...",
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

        # --- TestRunner: verify final code before Judge ---
        if context.current_code and budget.can_continue(reserve=0.10):
            try:
                await self._notify(on_progress, {
                    "type": "status", "content": "代码执行验证中..."
                })
                verify_result = await self.test_runner.verify(
                    context.current_code,
                    requirement,
                    llm_client=None,
                    debate_context=context,
                    language=language,
                )
                if not verify_result.passed and budget.can_continue(reserve=0.10):
                    context.add_message(
                        "system",
                        f"代码执行验证失败：\n{verify_result.stderr}\n请修复后重新提交。",
                    )
                    fix_response = await self.coder.speak(
                        context, "修复测试失败的问题，贴出完整的修复后代码。", budget
                    )
                    context.add_message(
                        "coder", fix_response.content,
                        code=fix_response.code,
                        structured=fix_response.structured,
                    )
            except Exception as e:
                logger.warning("test_runner_error error=%s", e)

        # --- Judge ---
        await self._notify(on_progress, {
            "type": "status", "content": "对抗结束，Judge 正在总结..."
        })

        judge_report = await self.judge.summarize(context, budget)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # --- Memory write-back ---
        await self._store_to_memory(
            requirement, language, context, judge_report, api_key, config
        )

        # --- Metrics ---
        record_debate_complete(
            language=language,
            complexity=complexity.value,
            rounds=context.round,
            converged=convergence_result.get("converged", False),
            duration_s=elapsed_ms / 1000,
        )

        metrics_raw = budget.get_metrics()

        result = DebateResult(
            code=context.current_code,
            language=language,
            confidence=judge_report.get("confidence", 0.0),
            quality_report=QualityReport(
                star_rating=judge_report.get("star_rating", 0),
                star_comment=judge_report.get("star_comment", ""),
                resolved_issues=judge_report.get("resolved_issues", []),
                unresolved_issues=judge_report.get("unresolved_issues", []),
                score_security=judge_report.get("score_security", 0),
                score_performance=judge_report.get("score_performance", 0),
                score_correctness=judge_report.get("score_correctness", 0),
                usage_advice=judge_report.get("usage_advice", ""),
            ),
            debate={
                "total_rounds": context.round,
                "converged": convergence_result.get("converged", False),
                "consensus_reason": convergence_result.get(
                    "reason",
                    "各方达成共识" if convergence_result.get("converged") else "达到最大轮次",
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
                "reason",
                "各方达成共识" if convergence_result.get("converged") else "达到最大轮次",
            ),
        )

        await self._notify(on_progress, {"type": "done"})

        return result

    async def _store_to_memory(
        self, requirement, language, context, judge_report, api_key, config
    ):
        """Store debate results into three-layer Memory system."""
        # Layer 1: store accepted attack findings
        accepted_findings = []
        for msg in context.messages:
            if msg.agent in ("security", "performance", "correctness"):
                if msg.structured and isinstance(msg.structured, dict):
                    for f in msg.structured.get("findings", []):
                        accepted_findings.append({
                            **f,
                            "was_accepted": True,
                            "attacker": msg.agent,
                        })
        if accepted_findings:
            await self.attack_kb.store_findings(
                requirement, language, accepted_findings
            )

        # Layer 3: store fix patterns from Coder responses
        for msg in context.messages:
            if msg.agent == "coder" and msg.structured and msg.code:
                for resp in msg.structured.get("responses", []):
                    if resp.get("action") == "accept_and_fix":
                        await self.fix_patterns.store_fix(
                            finding_description=resp.get("explanation", ""),
                            category=resp.get("finding_ref", "unknown"),
                            severity="medium",
                            fix_code=msg.code,
                        )

        # Layer 2: update user preferences
        if api_key:
            await self.user_prefs.update_from_request(
                api_key, {"language": config.attackers[0] if config.attackers else "python"}
            )

    async def _execute_round(
        self,
        context: DebateContext,
        budget: BudgetManager,
        on_progress: callable = None,
    ) -> list:
        round_messages = []

        # Pick up live extra context from WebSocket user intervention
        if self._live_extra_context:
            context.extra_context = self._live_extra_context
            self._live_extra_context = None

        # Stage 1: Coder speaks
        if context.round == 1:
            coder_prompt = (
                f"根据以下需求生成代码，并简要说明你的设计思路：\n{context.requirement}\n\n"
                "提交前请用 run_code_snippet 自测代码能否正常运行。"
            )
            if context.extra_context:
                coder_prompt += f"\n\n补充需求：{context.extra_context}"
        else:
            coder_prompt = (
                "请回应上一轮各 Attacker 的意见。"
                "对每个攻击：如果合理，承认并修复；如果不合理，调用工具验证后给出反驳证据。"
                "如果有修复，贴出完整的新版代码。"
                "提交前请用 run_code_snippet 自测修复后的代码。"
            )
            # Memory Layer 3: retrieve historical fix patterns for current issues
            last_findings = self._get_latest_findings(context)
            if last_findings:
                fix_hints = []
                for desc in last_findings[:3]:
                    fixes = await self.fix_patterns.retrieve_fixes(desc, top_k=2)
                    fix_hints.extend(fixes)
                if fix_hints:
                    coder_prompt += (
                        "\n\n以下是历史上类似问题的修复方案供参考：\n"
                        + "\n".join(f"  - {h}" for h in fix_hints[:5])
                    )

        await self._notify(on_progress, {
            "type": "agent_start", "agent": "coder"
        })

        coder_start = time.monotonic()
        coder_response = await self.coder.speak(context, coder_prompt, budget)
        record_agent_call(
            "coder", coder_response.tokens_used,
            time.monotonic() - coder_start,
        )

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
                a_start = time.monotonic()
                resp = await agent.speak(context, attacker_prompt, budget)
                record_agent_call(name, resp.tokens_used, time.monotonic() - a_start)
                return resp
            except Exception as e:
                logger.warning("attacker_failed agent=%s error=%s", name, e)
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

    def _get_latest_findings(self, context: DebateContext) -> list[str]:
        """Extract finding descriptions from the most recent attacker messages."""
        descriptions = []
        for msg in reversed(context.messages):
            if msg.agent in ("security", "performance", "correctness"):
                if msg.structured and isinstance(msg.structured, dict):
                    for f in msg.structured.get("findings", []):
                        if f.get("description"):
                            descriptions.append(f["description"])
            if len(descriptions) >= 5:
                break
        return descriptions

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
