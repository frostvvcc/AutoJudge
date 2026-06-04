"""
LangGraph state graph definition for AutoJudge debate flow.

Uses three key LangGraph capabilities:
1. Parallel branches (three Attackers run concurrently then join)
2. Checkpoint (resume from any step after disconnect)
3. Interrupt (user intervention between rounds — POST auto-skips)

Entry point: run_debate_with_graph() wraps the graph with Memory/TestRunner/
ComplexityRouter pre/post-processing, then runs the compiled graph.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from app.agents.coder import CoderAgent
from app.agents.security_attacker import SecurityAttacker
from app.agents.performance_attacker import PerformanceAttacker
from app.agents.correctness_attacker import CorrectnessAttacker
from app.agents.judge import JudgeAgent
from app.engine.context import DebateContext, DebateConfig, DebateMessage
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
)

logger = logging.getLogger(__name__)


# ─── State ──────────────────────────────────────────────────────────────────

class DebateState(TypedDict):
    requirement: str
    language: str
    framework: str
    current_code: str
    round: int
    max_rounds: int
    messages: list[dict]
    consensus: dict
    skip_list: list[str]
    extra_context: str
    converged: bool
    budget_spent: int
    budget_total: int
    judge_report: dict
    config: dict
    enable_interrupt: bool


# ─── Shared agent instances ─────────────────────────────────────────────────

coder_agent = CoderAgent()
security_agent = SecurityAttacker()
performance_agent = PerformanceAttacker()
correctness_agent = CorrectnessAttacker()
judge_agent = JudgeAgent()
consensus_detector = ConsensusDetector()


# ─── Helpers ────────────────────────────────────────────────────────────────

def _build_context(state: DebateState) -> tuple[DebateContext, BudgetManager]:
    config = DebateConfig(**state.get("config", {}))
    ctx = DebateContext(state["requirement"], config)
    ctx.round = state["round"]
    ctx.current_code = state.get("current_code", "")
    ctx.skip_list = state.get("skip_list", [])
    ctx.extra_context = state.get("extra_context", "")

    for msg_dict in state.get("messages", []):
        ctx.messages.append(
            DebateMessage(
                agent=msg_dict["agent"],
                content=msg_dict["content"],
                round=msg_dict.get("round", 0),
                code=msg_dict.get("code"),
                structured=msg_dict.get("structured"),
            )
        )

    budget = BudgetManager(state.get("budget_total", 100_000))
    budget.spent = state.get("budget_spent", 0)

    return ctx, budget


# ─── Graph nodes ────────────────────────────────────────────────────────────

async def coder_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)
    ctx.round = state["round"] + 1

    if ctx.round == 1:
        prompt = f"根据以下需求生成代码，并简要说明你的设计思路：\n{ctx.requirement}"
        if ctx.extra_context:
            prompt += f"\n\n补充需求：{ctx.extra_context}"
    else:
        prompt = (
            "请回应上一轮各 Attacker 的意见。"
            "对每个攻击：如果合理，承认并修复；如果不合理，调用工具验证后给出反驳证据。"
            "如果有修复，贴出完整的新版代码。"
        )

    start = time.monotonic()
    response = await coder_agent.speak(ctx, prompt, budget)
    record_agent_call("coder", response.tokens_used, time.monotonic() - start)

    new_msg = {
        "agent": "coder",
        "content": response.content,
        "round": ctx.round,
        "code": response.code,
        "structured": response.structured,
    }

    return {
        "round": ctx.round,
        "current_code": response.code or state.get("current_code", ""),
        "messages": state.get("messages", []) + [new_msg],
        "budget_spent": budget.spent,
    }


async def _attacker_node(
    state: DebateState, agent_instance, agent_name: str
) -> dict:
    if agent_name in state.get("skip_list", []):
        return {}

    ctx, budget = _build_context(state)

    if state["round"] <= 1:
        prompt = "审查 Coder 提交的代码，从你的专业角度找出问题。"
    else:
        prompt = (
            "审查 Coder 的最新修复。如果之前的问题已修复，确认。"
            "如果有新问题，指出。如果没有新问题了，stance 设为 satisfied。"
        )

    try:
        start = time.monotonic()
        response = await agent_instance.speak(ctx, prompt, budget)
        record_agent_call(agent_name, response.tokens_used, time.monotonic() - start)
        new_msg = {
            "agent": agent_name,
            "content": response.content,
            "round": state["round"],
            "structured": response.structured,
        }
        return {
            "messages": state.get("messages", []) + [new_msg],
            "budget_spent": budget.spent,
        }
    except Exception as e:
        logger.warning("graph_%s_failed error=%s", agent_name, e)
        return {}


async def security_node(state: DebateState) -> dict:
    return await _attacker_node(state, security_agent, "security")


async def performance_node(state: DebateState) -> dict:
    return await _attacker_node(state, performance_agent, "performance")


async def correctness_node(state: DebateState) -> dict:
    return await _attacker_node(state, correctness_agent, "correctness")


async def cross_review_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)
    current_round = state["round"]

    round_msgs = [
        m
        for m in state.get("messages", [])
        if m.get("round") == current_round
        and m["agent"] in ("security", "performance", "correctness")
    ]

    if len(round_msgs) < 2:
        return _check_and_return_consensus(state, round_msgs)

    findings_summary = "\n\n".join(
        f"[{m['agent'].upper()}] {m['content']}" for m in round_msgs
    )

    cross_prompt = (
        f"以下是其他 Attacker 本轮的发现：\n{findings_summary}\n"
        "请补充你认为重要但对方遗漏的观点，或对对方的发现表示支持/质疑。"
        "如果没有补充，直接确认。"
    )

    agents = {
        "security": security_agent,
        "performance": performance_agent,
        "correctness": correctness_agent,
    }

    new_messages = list(state.get("messages", []))

    active = [
        (name, agent) for name, agent in agents.items()
        if name not in state.get("skip_list", [])
    ]

    async def safe_cross(name, agent):
        try:
            return name, await agent.speak(ctx, cross_prompt, budget)
        except Exception as e:
            logger.warning("cross_review_%s_failed error=%s", name, e)
            return name, None

    cross_results = await asyncio.gather(
        *[safe_cross(n, a) for n, a in active]
    )

    for name, response in cross_results:
        if response and response.content.strip():
            new_messages.append({
                "agent": name,
                "content": f"[交叉审阅] {response.content}",
                "round": current_round,
                "structured": response.structured,
            })

    updated_state = {**state, "messages": new_messages}

    # Interrupt: only pause if enable_interrupt is set (WebSocket mode)
    if state.get("enable_interrupt"):
        user_input = interrupt({
            "type": "round_complete",
            "round": current_round,
            "can_skip": ["security", "performance", "correctness"],
        })
        if user_input and isinstance(user_input, dict):
            if user_input.get("type") == "skip_attacker":
                skip_list = list(state.get("skip_list", []))
                skip_list.append(user_input["attacker"])
                updated_state["skip_list"] = skip_list
            elif user_input.get("type") == "add_context":
                updated_state["extra_context"] = user_input.get("content", "")

    return _check_and_return_consensus(updated_state, round_msgs)


def _check_and_return_consensus(
    state: dict, round_msgs: list[dict]
) -> dict:
    debate_msgs = [
        DebateMessage(
            agent=m["agent"],
            content=m["content"],
            round=m.get("round", 0),
            structured=m.get("structured"),
        )
        for m in round_msgs
    ]

    result = consensus_detector.check_consensus(debate_msgs)

    return {
        "messages": state.get("messages", []),
        "consensus": result,
        "converged": result.get("converged", False),
        "budget_spent": state.get("budget_spent", 0),
    }


def check_consensus_edge(state: DebateState) -> str:
    if state.get("converged"):
        return "converged"

    budget_total = state.get("budget_total", 100_000)
    budget_spent = state.get("budget_spent", 0)
    if budget_spent >= budget_total * 0.85:
        return "budget_exceeded"

    max_rounds = state.get("max_rounds", 5)
    if state.get("round", 0) >= max_rounds:
        return "budget_exceeded"

    return "continue"


async def judge_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)
    report = await judge_agent.summarize(ctx, budget)
    return {
        "judge_report": report,
        "budget_spent": budget.spent,
    }


# ─── Graph builder ──────────────────────────────────────────────────────────

_compiled_graph = None


def build_debate_graph():
    graph = StateGraph(DebateState)

    graph.add_node("coder", coder_node)
    graph.add_node("security", security_node)
    graph.add_node("performance", performance_node)
    graph.add_node("correctness", correctness_node)
    graph.add_node("cross_review", cross_review_node)
    graph.add_node("judge", judge_node)

    graph.set_entry_point("coder")

    graph.add_edge("coder", "security")
    graph.add_edge("coder", "performance")
    graph.add_edge("coder", "correctness")

    graph.add_edge("security", "cross_review")
    graph.add_edge("performance", "cross_review")
    graph.add_edge("correctness", "cross_review")

    graph.add_conditional_edges(
        "cross_review",
        check_consensus_edge,
        {
            "continue": "coder",
            "converged": "judge",
            "budget_exceeded": "judge",
        },
    )
    graph.add_edge("judge", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def get_debate_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_debate_graph()
    return _compiled_graph


# ─── Full pipeline: pre-processing → graph → post-processing ───────────────

async def run_debate_with_graph(
    requirement: str,
    language: str = "python",
    framework: str | None = None,
    config: DebateConfig | None = None,
    api_key: str | None = None,
) -> DebateResult:
    """Run a full debate through LangGraph with Memory/TestRunner/ComplexityRouter."""
    config = config or DebateConfig()
    start_time = time.monotonic()

    # --- Pre-processing: requirement parsing + complexity routing ---
    parsed_req = await parse_requirement(requirement, language, framework)

    complexity = route_complexity(requirement, parsed_req)
    complexity_config = get_debate_config(complexity)
    if config.max_rounds == DebateConfig().max_rounds:
        config.max_rounds = complexity_config["max_rounds"]
    if config.attackers == DebateConfig().attackers:
        config.attackers = complexity_config["attackers"]
    if complexity_config.get("skip_cross_review"):
        config.skip_cross_review = True

    # --- Memory retrieval ---
    attack_kb = AttackKnowledgeBase()
    user_prefs = UserPreferenceStore()
    fix_patterns = FixPatternStore()

    experience_prompt = ""
    experiences = await attack_kb.retrieve_relevant(requirement)
    if experiences:
        experience_prompt = attack_kb.build_experience_prompt(experiences)

    preference_prompt = ""
    if api_key:
        prefs = await user_prefs.get_preferences(api_key)
        if prefs:
            preference_prompt = user_prefs.build_preference_prompt(prefs)

    # --- Build initial graph state ---
    initial_state: DebateState = {
        "requirement": requirement,
        "language": language,
        "framework": framework or "",
        "current_code": "",
        "round": 0,
        "max_rounds": config.max_rounds,
        "messages": [],
        "consensus": {},
        "skip_list": [],
        "extra_context": "",
        "converged": False,
        "budget_spent": 0,
        "budget_total": config.max_tokens,
        "judge_report": {},
        "config": {
            "max_rounds": config.max_rounds,
            "attackers": config.attackers,
            "model": config.model,
            "max_tokens": config.max_tokens,
            "skip_cross_review": config.skip_cross_review,
        },
        "enable_interrupt": False,
    }

    # Inject Memory context into agent instances (via shared context patterns)
    # The agents read experience_context from DebateContext, which is rebuilt
    # inside each node via _build_context. We inject it into the extra_context
    # field so it flows through the graph state.
    context_parts = []
    if experience_prompt:
        context_parts.append(experience_prompt)
    if preference_prompt:
        context_parts.append(preference_prompt)
    if context_parts:
        initial_state["extra_context"] = "\n\n".join(context_parts)

    # --- Run the LangGraph graph ---
    graph = get_debate_graph()
    thread_id = str(uuid.uuid4())
    graph_config = {"configurable": {"thread_id": thread_id}}

    final_state = await graph.ainvoke(initial_state, graph_config)

    # --- Post-processing: TestRunner ---
    final_code = final_state.get("current_code", "")
    if final_code:
        test_runner = TestRunner()
        ctx_for_test = DebateContext(requirement, config)
        for msg_dict in final_state.get("messages", []):
            ctx_for_test.messages.append(
                DebateMessage(
                    agent=msg_dict["agent"],
                    content=msg_dict["content"],
                    round=msg_dict.get("round", 0),
                    structured=msg_dict.get("structured"),
                )
            )
        verify_result = await test_runner.verify(
            final_code, requirement,
            llm_client=None,
            debate_context=ctx_for_test,
            language=language,
        )
        if not verify_result.passed:
            logger.info("graph_test_verification_failed stderr=%s", verify_result.stderr[:200])

    # --- Post-processing: Memory write-back ---
    accepted_findings = []
    for msg in final_state.get("messages", []):
        if msg["agent"] in ("security", "performance", "correctness"):
            structured = msg.get("structured")
            if structured and isinstance(structured, dict):
                for f in structured.get("findings", []):
                    accepted_findings.append({
                        **f,
                        "was_accepted": True,
                        "attacker": msg["agent"],
                    })
    if accepted_findings:
        await attack_kb.store_findings(requirement, language, accepted_findings)

    for msg in final_state.get("messages", []):
        if msg["agent"] == "coder" and msg.get("code") and msg.get("structured"):
            for resp in msg["structured"].get("responses", []):
                if resp.get("action") == "accept_and_fix":
                    await fix_patterns.store_fix(
                        finding_description=resp.get("explanation", ""),
                        category=resp.get("finding_ref", "unknown"),
                        severity="medium",
                        fix_code=msg["code"],
                    )

    if api_key:
        await user_prefs.update_from_request(api_key, {"language": language})

    # --- Metrics ---
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    final_round = final_state.get("round", 0)
    is_converged = final_state.get("converged", False)

    record_debate_complete(
        language=language,
        complexity=complexity.value,
        rounds=final_round,
        converged=is_converged,
        duration_s=elapsed_ms / 1000,
    )

    # --- Build DebateResult ---
    judge_report = final_state.get("judge_report", {})
    budget_spent = final_state.get("budget_spent", 0)
    sonnet_rate = (3.0 + 15.0) / 2 / 1_000_000
    cost_usd = round(budget_spent * sonnet_rate, 4)

    transcript_rounds: dict[int, list[dict]] = {}
    for msg in final_state.get("messages", []):
        r = msg.get("round", 0)
        transcript_rounds.setdefault(r, []).append({
            "agent": msg["agent"],
            "content": msg["content"],
            "code": msg.get("code"),
        })
    transcript = [
        {"round": r, "messages": msgs}
        for r, msgs in sorted(transcript_rounds.items())
    ]

    return DebateResult(
        code=final_code,
        language=language,
        confidence=judge_report.get("confidence", 0.0),
        debate={
            "total_rounds": final_round,
            "converged": is_converged,
            "consensus_reason": (
                "各方达成共识" if is_converged else "达到最大轮次或预算上限"
            ),
            "transcript": transcript,
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
            total_rounds=final_round,
            total_tokens=budget_spent,
            total_latency_ms=elapsed_ms,
            cost_usd=cost_usd,
        ),
        converged=is_converged,
        convergence_reason=(
            "各方达成共识" if is_converged else "达到最大轮次或预算上限"
        ),
        metadata={"engine": "langgraph", "thread_id": thread_id},
    )
