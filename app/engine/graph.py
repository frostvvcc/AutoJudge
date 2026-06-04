"""
LangGraph state graph definition for AutoJudge debate flow.

Uses three key LangGraph capabilities:
1. Parallel branches (three Attackers run concurrently then join)
2. Checkpoint (resume from any step after disconnect)
3. Interrupt (user intervention between rounds)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TypedDict, Annotated

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

logger = logging.getLogger(__name__)


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


coder_agent = CoderAgent()
security_agent = SecurityAttacker()
performance_agent = PerformanceAttacker()
correctness_agent = CorrectnessAttacker()
judge_agent = JudgeAgent()
consensus_detector = ConsensusDetector()


def _build_context(state: DebateState) -> tuple[DebateContext, BudgetManager]:
    """Reconstruct DebateContext and BudgetManager from graph state."""
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


def _msg_to_dict(msg: DebateMessage) -> dict:
    return {
        "agent": msg.agent,
        "content": msg.content,
        "round": msg.round,
        "code": msg.code,
        "structured": msg.structured,
    }


async def coder_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)
    ctx.round = state["round"] + 1

    if ctx.round == 1:
        prompt = f"根据以下需求生成代码，并简要说明你的设计思路：\n{ctx.requirement}"
    else:
        prompt = (
            "请回应上一轮各 Attacker 的意见。"
            "对每个攻击：如果合理，承认并修复；如果不合理，给出反驳证据。"
            "如果有修复，贴出完整的新版代码。"
        )

    response = await coder_agent.speak(ctx, prompt, budget)

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
        response = await agent_instance.speak(ctx, prompt, budget)
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
        logger.warning(f"{agent_name}_failed", error=str(e))
        return {}


async def security_node(state: DebateState) -> dict:
    return await _attacker_node(state, security_agent, "security")


async def performance_node(state: DebateState) -> dict:
    return await _attacker_node(state, performance_agent, "performance")


async def correctness_node(state: DebateState) -> dict:
    return await _attacker_node(state, correctness_agent, "correctness")


async def cross_review_node(state: DebateState) -> dict:
    """Cross-review: attackers see each other's findings and can supplement/challenge."""
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

    # Parallel cross-review (asyncio.gather instead of serial for loop)
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
            new_messages.append(
                {
                    "agent": name,
                    "content": f"[交叉审阅] {response.content}",
                    "round": current_round,
                    "structured": response.structured,
                }
            )

    # LangGraph interrupt: pause for optional user intervention
    user_input = interrupt({
        "type": "round_complete",
        "round": current_round,
        "can_skip": ["security", "performance", "correctness"],
    })

    updated_state = {**state, "messages": new_messages}

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


def build_debate_graph():
    """Build the LangGraph state graph for debate flow."""
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
