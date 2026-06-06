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
import operator
import time
import uuid
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.types import interrupt, Command
from langgraph.errors import GraphInterrupt

from app.config import settings


def _merge_messages(left: list[dict], right: list[dict]) -> list[dict]:
    """Reducer: append new messages to existing list (handles parallel fan-in)."""
    return left + right


def _max_int(left: int, right: int) -> int:
    """Reducer: take the higher budget_spent value from parallel nodes."""
    return max(left, right)

from app.llm.client import set_stream_callback
from app.agents.coder import CoderAgent
from app.agents.security_attacker import SecurityAttacker
from app.agents.performance_attacker import PerformanceAttacker
from app.agents.correctness_attacker import CorrectnessAttacker
from app.agents.judge import JudgeAgent
from app.agents.arbitrator import ArbitratorAgent
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
    QualityReport,
)

logger = logging.getLogger(__name__)

# ─── Progress callback registry (concurrent-safe via contextvars) ─

import contextvars

_progress_callback: contextvars.ContextVar[callable | None] = contextvars.ContextVar(
    '_progress_callback', default=None
)


async def _notify(event: dict):
    cb = _progress_callback.get(None)
    if cb:
        try:
            await cb(event)
        except Exception:
            pass


def _make_stream_cb(agent_name: str):
    """Create a streaming callback that sends text deltas to the frontend."""
    async def _on_stream(delta: str):
        await _notify({"type": "stream", "agent": agent_name, "delta": delta})
    return _on_stream


# ─── State ──────────────────────────────────────────────────────────────────

class DebateState(TypedDict):
    requirement: str
    language: str
    framework: str
    mode: str
    current_code: str
    round: int
    max_rounds: int
    messages: Annotated[list[dict], _merge_messages]
    consensus: dict
    skip_list: list[str]
    extra_context: str
    converged: bool
    budget_spent: Annotated[int, _max_int]
    budget_total: int
    judge_report: dict
    arbitration_result: dict
    must_fix_items: list[dict]
    convergence_reason: str
    selected_plan: str
    config: dict
    enable_interrupt: bool
    retry_count: int
    user_decision: str


# ─── Shared agent instances ─────────────────────────────────────────────────

coder_agent = CoderAgent()
security_agent = SecurityAttacker()
performance_agent = PerformanceAttacker()
correctness_agent = CorrectnessAttacker()
judge_agent = JudgeAgent()
arbitrator_agent = ArbitratorAgent()
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

PLAN_PHASE_PROMPT = """根据以下需求，设计 2 个不同方向的实现方案。

要求：
1. 两个方案必须有明确的差异（不是微调，是不同的技术路线）
2. 每个方案说明：技术选型、核心流程、安全考虑、不包含什么
3. 给每个方案一个简短标签（如"轻量级""生产级""安全优先"）
4. 不写代码，只说方案

需求：{requirement}
{extra_context}"""


async def plan_node(state: DebateState) -> dict:
    """Plan Phase: Coder outputs 2 solution proposals for user to choose."""
    ctx, budget = _build_context(state)

    await _notify({"type": "phase_change", "phase": "plan"})
    await _notify({"type": "status", "content": "Coder 正在设计方案..."})
    await _notify({"type": "agent_start", "agent": "coder"})

    extra = state.get("extra_context", "")
    prompt = PLAN_PHASE_PROMPT.format(
        requirement=state["requirement"],
        extra_context=f"补充信息：{extra}" if extra else "",
    )

    from app.llm.model_router import get_model_for_agent
    from app.llm.client import call_agent

    start = time.monotonic()
    system = (
        "你是方案设计师。根据用户需求设计 2 个不同方向的实现方案。"
        "不写代码，只说方案。每个方案说明技术选型、核心流程、安全考虑、不包含什么。"
    )
    messages = [{"role": "user", "content": prompt}]
    response = await call_agent(
        agent="planner",
        system_prompt=system,
        messages=messages,
        model=get_model_for_agent("planner"),
        max_tokens=budget.get_max_tokens("coder"),
    )
    budget.record("coder", response.tokens_used)
    record_agent_call("coder", response.tokens_used, time.monotonic() - start)

    plans_content = response.content

    await _notify({
        "type": "plan_proposal",
        "content": plans_content,
    })

    selected_plan = plans_content

    # HITL: pause for user to select/adjust plan (WebSocket mode only)
    if state.get("enable_interrupt"):
        conversation_round = 0
        max_plan_rounds = 7

        while conversation_round < max_plan_rounds:
            hint = ""
            if conversation_round == 3:
                hint = "\n\n💡 已调整 3 轮方案。建议先选一个开始——后续辩论阶段还可以继续优化。"
            elif conversation_round == 5:
                hint = "\n\n⚠️ 方案讨论已进行 5 轮。建议尽快选择一个方案开始。"

            user_input = interrupt({
                "type": "plan_review",
                "content": plans_content + hint,
                "round": conversation_round,
                "max_rounds": max_plan_rounds,
            })

            if not user_input or not isinstance(user_input, dict):
                break

            action = user_input.get("action", "")

            if action == "select":
                selected_plan = user_input.get("plan_content", plans_content)
                break

            elif action == "auto_select":
                break

            elif action == "chat":
                user_message = user_input.get("message", "")
                conversation_round += 1

                adjust_prompt = (
                    f"用户对方案有调整意见：\n{user_message}\n\n"
                    f"请根据用户的反馈重新设计 2 个方案。"
                    f"之前的方案：\n{plans_content}"
                )

                await _notify({"type": "agent_start", "agent": "coder"})
                start = time.monotonic()
                response = await coder_agent.speak(ctx, adjust_prompt, budget)
                record_agent_call("coder", response.tokens_used, time.monotonic() - start)

                plans_content = response.content
                selected_plan = plans_content

                await _notify({
                    "type": "plan_proposal",
                    "content": plans_content,
                })
            else:
                break

    plan_msg = {
        "agent": "coder",
        "content": f"[方案设计] {plans_content}",
        "round": 0,
    }
    await _notify({"type": "message", **plan_msg})

    return {
        "selected_plan": selected_plan,
        "messages": [plan_msg],
        "budget_spent": budget.spent,
    }



async def coder_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)
    ctx.round = state["round"] + 1

    await _notify({"type": "round_start", "round": ctx.round})
    await _notify({"type": "agent_start", "agent": "coder"})

    if ctx.round == 1:
        selected_plan = state.get("selected_plan", "")
        if selected_plan:
            prompt = (
                f"根据以下需求和确认的方案生成代码：\n{ctx.requirement}\n\n"
                f"确认的方案：\n{selected_plan}\n\n"
                "请严格按照方案实现。提交前用 run_code_snippet 自测。"
            )
        else:
            prompt = (
                f"根据以下需求生成代码，并简要说明你的设计思路：\n{ctx.requirement}\n\n"
                "提交前请用 run_code_snippet 自测代码能否正常运行。"
            )
        if ctx.extra_context:
            prompt += f"\n\n补充需求：{ctx.extra_context}"
    else:
        prompt = (
            "请回应上一轮各 Attacker 的意见。"
            "对每个攻击：如果合理，承认并修复；如果不合理，调用工具验证后给出反驳证据。"
            "如果有修复，贴出完整的新版代码。"
            "提交前请用 run_code_snippet 自测修复后的代码。"
        )

    start = time.monotonic()
    set_stream_callback(_make_stream_cb("coder"))
    response = await coder_agent.speak(ctx, prompt, budget)
    set_stream_callback(None)
    record_agent_call("coder", response.tokens_used, time.monotonic() - start)

    await _notify({"type": "stream_end", "agent": "coder"})
    new_msg = {
        "agent": "coder",
        "content": response.content,
        "round": ctx.round,
        "code": response.code,
        "structured": response.structured,
    }
    await _notify({"type": "message", **new_msg})

    return {
        "round": ctx.round,
        "current_code": response.code or state.get("current_code", ""),
        "messages": [new_msg],
        "budget_spent": budget.spent,
    }


async def _attacker_node(
    state: DebateState, agent_instance, agent_name: str
) -> dict:
    if agent_name in state.get("skip_list", []):
        return {}

    await _notify({"type": "agent_start", "agent": agent_name})
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
        set_stream_callback(_make_stream_cb(agent_name))
        response = await agent_instance.speak(ctx, prompt, budget)
        set_stream_callback(None)
        record_agent_call(agent_name, response.tokens_used, time.monotonic() - start)
        await _notify({"type": "stream_end", "agent": agent_name})
        new_msg = {
            "agent": agent_name,
            "content": response.content,
            "round": state["round"],
            "structured": response.structured,
        }
        await _notify({"type": "message", **new_msg})
        return {
            "messages": [new_msg],
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


def _build_structured_findings_summary(round_msgs: list[dict], exclude_agent: str) -> str:
    """
    Layer 3: Structured Summary Injection
    从其他攻击者的结构化输出中提取 findings，
    以 [SEVERITY] category: description 格式注入，不传完整自然语言。
    """
    lines = []
    for m in round_msgs:
        if m["agent"] == exclude_agent:
            continue
        structured = m.get("structured")
        if not structured or not isinstance(structured, dict):
            if m.get("content"):
                lines.append(f"[{m['agent'].upper()}] {m['content'][:200]}")
            continue
        findings = structured.get("findings", [])
        stance = structured.get("stance", "unknown")
        if findings:
            for f in findings:
                sev = f.get("severity", "unknown").upper()
                cat = f.get("category", "")
                desc = f.get("description", "")
                lines.append(f"[{m['agent'].upper()}] [{sev}] {cat}: {desc}")
        elif stance == "attacking":
            msg_text = structured.get("message", "有顾虑但未提供具体 findings")
            lines.append(f"[{m['agent'].upper()}] [MEDIUM] {msg_text[:200]}")
        else:
            lines.append(f"[{m['agent'].upper()}] stance={stance}，无新发现")
    return "\n".join(lines)


async def cross_review_node(state: DebateState) -> dict:
    """
    Layer 3 实现：交叉审阅时注入结构化 findings 摘要，
    而不是其他攻击者的完整自然语言发言。
    """
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

    agents = {
        "security": security_agent,
        "performance": performance_agent,
        "correctness": correctness_agent,
    }

    new_cross_msgs = []

    active = [
        (name, agent) for name, agent in agents.items()
        if name not in state.get("skip_list", [])
    ]

    async def safe_cross(name, agent):
        try:
            others_findings = _build_structured_findings_summary(round_msgs, exclude_agent=name)
            cross_prompt = (
                f"以下是其他 Attacker 本轮的结构化发现：\n{others_findings}\n\n"
                "请补充你认为重要但对方遗漏的观点，或对对方的发现表示支持/质疑。"
                "如果没有补充，直接确认。"
            )
            return name, await agent.speak(ctx, cross_prompt, budget)
        except Exception as e:
            logger.warning("cross_review_%s_failed error=%s", name, e)
            return name, None

    cross_results = await asyncio.gather(
        *[safe_cross(n, a) for n, a in active]
    )

    for name, response in cross_results:
        if response and response.content.strip():
            new_cross_msgs.append({
                "agent": name,
                "content": f"[交叉审阅] {response.content}",
                "round": current_round,
                "structured": response.structured,
            })

    updated_state = {**state, "messages": new_cross_msgs}

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

    consensus_msgs = round_msgs + new_cross_msgs
    return _check_and_return_consensus(updated_state, consensus_msgs)


def _check_and_return_consensus(
    state: dict, round_msgs: list[dict]
) -> dict:
    seen_agents: set[str] = set()
    latest_per_agent: dict[str, dict] = {}
    for m in round_msgs:
        if m["agent"] in ("security", "performance", "correctness"):
            latest_per_agent[m["agent"]] = m

    debate_msgs = [
        DebateMessage(
            agent=m["agent"],
            content=m["content"],
            round=m.get("round", 0),
            structured=m.get("structured"),
        )
        for m in latest_per_agent.values()
    ]

    skip_list = set(state.get("skip_list", []))
    active_attackers = {"security", "performance", "correctness"} - skip_list
    result = consensus_detector.check_consensus(debate_msgs, active_attackers)

    update = {
        "consensus": result,
        "converged": result.get("converged", False),
        "budget_spent": state.get("budget_spent", 0),
    }
    if state.get("messages"):
        update["messages"] = state["messages"]
    if "skip_list" in state:
        update["skip_list"] = state["skip_list"]
    if "extra_context" in state:
        update["extra_context"] = state["extra_context"]
    return update


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



def _extract_unresolved_disputes(state: DebateState) -> list[dict]:
    """Extract unresolved disputes from debate messages."""
    disputes = []
    last_round = state.get("round", 0)

    for msg in state.get("messages", []):
        if msg.get("round", 0) < last_round:
            continue
        if msg["agent"] in ("security", "performance", "correctness"):
            structured = msg.get("structured")
            if not structured or not isinstance(structured, dict):
                continue
            if structured.get("stance") != "attacking":
                continue
            findings = structured.get("findings", [])
            if findings:
                for finding in findings:
                    disputes.append({
                        "attacker": msg["agent"],
                        "finding": finding.get("description", ""),
                        "severity": finding.get("severity", "unknown"),
                        "test_input": finding.get("test_input"),
                        "coder_response": _find_coder_response(state, finding),
                    })
            else:
                disputes.append({
                    "attacker": msg["agent"],
                    "finding": structured.get("message", "Attacker 表示仍有顾虑但未提供具体 findings"),
                    "severity": "medium",
                    "test_input": None,
                    "coder_response": "未回应",
                })
    return disputes


SECURITY_REDLINE_CATEGORIES = {
    "sql_injection", "rce", "command_injection",
    "auth_bypass", "path_traversal", "xss",
    "sql injection", "remote code execution",
}


def _security_redline_allows(ruling: dict, new_verdict: str) -> bool:
    """Critical security issues cannot be downgraded by user override."""
    if ruling.get("re_assessed_severity") != "critical":
        return True
    dispute_id = ruling.get("dispute_id", "").lower()
    reasoning = ruling.get("reasoning", "").lower()
    is_security_redline = any(
        cat in dispute_id or cat in reasoning
        for cat in SECURITY_REDLINE_CATEGORIES
    )
    if is_security_redline and new_verdict in ("dismissed", "acknowledged", "deferred"):
        return False
    return True


def _needs_human_review(state: dict) -> bool:
    """Check if the final result requires human review."""
    arb = state.get("arbitration_result")
    if not arb or not isinstance(arb, dict):
        return False
    rulings = arb.get("rulings", [])
    needs_human_count = sum(1 for r in rulings if r.get("verdict") == "needs_human")
    must_fix_count = sum(1 for r in rulings if r.get("verdict") == "must_fix")
    has_unfixed_critical = any(
        r.get("re_assessed_severity") == "critical" and r.get("verdict") == "must_fix"
        for r in rulings
    )
    return needs_human_count > 0 or must_fix_count > 3 or has_unfixed_critical


def _find_coder_response(state: DebateState, finding: dict) -> str:
    """Find Coder's response to a specific finding."""
    for msg in reversed(state.get("messages", [])):
        if msg["agent"] == "coder" and msg.get("structured"):
            structured = msg["structured"]
            if isinstance(structured, dict):
                for resp in structured.get("responses", []):
                    if finding.get("description", "") in resp.get("explanation", ""):
                        action = resp.get("action", "?")
                        explanation = resp.get("explanation", "")
                        return f"[{action}] {explanation}"
    return "未回应"


async def arbitration_node(state: DebateState) -> dict:
    """Arbitrator intervenes when debate fails to converge."""
    ctx, budget = _build_context(state)

    disputes = _extract_unresolved_disputes(state)

    if not disputes:
        return {
            "converged": True,
            "convergence_reason": "仲裁判定：无实质未解决争议，等效收敛",
            "arbitration_result": {},
            "must_fix_items": [],
        }

    await _notify({"type": "phase_change", "phase": "arbitration"})
    await _notify({
        "type": "status",
        "content": f"辩论未收敛，Arbitrator 正在仲裁 {len(disputes)} 条争议...",
    })

    arbitration_result = await arbitrator_agent.arbitrate(ctx, budget, disputes)

    await _notify({
        "type": "arbitration_complete",
        "disputes_count": len(disputes),
        "overall_verdict": arbitration_result.get("overall_verdict"),
        "summary": arbitration_result.get("summary", ""),
    })

    # HITL: let user review arbitration ruling
    if state.get("enable_interrupt"):
        user_feedback = interrupt({
            "type": "arbitration_review",
            "rulings": arbitration_result.get("rulings", []),
            "overall_verdict": arbitration_result.get("overall_verdict"),
            "summary": arbitration_result.get("summary", ""),
        })
        if user_feedback and isinstance(user_feedback, dict):
            overrides = user_feedback.get("overrides", {})
            for ruling in arbitration_result.get("rulings", []):
                did = ruling.get("dispute_id", "")
                override = overrides.get(did)
                if override and override.get("action") in ("upgrade", "downgrade", "dismiss"):
                    new_verdict = override.get("new_verdict", ruling["verdict"])
                    if not _security_redline_allows(ruling, new_verdict):
                        ruling["reasoning"] += "\n[安全红线] 用户尝试降级被拒绝"
                        continue
                    ruling["verdict"] = new_verdict
                    ruling["reasoning"] += f"\n[用户调整] → {new_verdict}"

    overall = arbitration_result.get("overall_verdict", "not_deliverable")
    rulings = arbitration_result.get("rulings", [])
    must_fix = [r for r in rulings if r.get("verdict") == "must_fix"]

    if overall == "deliverable" or not must_fix:
        return {
            "converged": True,
            "convergence_reason": f"仲裁裁决：代码可交付（{len(disputes)} 条争议已裁决）",
            "arbitration_result": arbitration_result,
            "must_fix_items": [],
        }

    if overall == "fix_then_deliver" and len(must_fix) <= 3:
        has_critical = any(
            r.get("re_assessed_severity") == "critical" for r in must_fix
        )
        if not has_critical:
            return {
                "converged": False,
                "convergence_reason": "仲裁裁决：需修复后交付",
                "arbitration_result": arbitration_result,
                "must_fix_items": must_fix,
            }

    return {
        "converged": True,
        "convergence_reason": "仲裁裁决：建议人工审查",
        "arbitration_result": arbitration_result,
        "must_fix_items": [],
    }


def _arbitration_edge(state: DebateState) -> str:
    must_fix = state.get("must_fix_items", [])
    if must_fix:
        return "fix"
    return "deliver"


async def final_fix_node(state: DebateState) -> dict:
    """Coder fixes must_fix items after arbitration."""
    ctx, budget = _build_context(state)
    must_fix_items = state.get("must_fix_items", [])

    if not must_fix_items:
        return {"converged": True, "convergence_reason": "无需修复"}

    fix_list = "\n".join(
        f"{i+1}. [{item.get('re_assessed_severity', '?')}] {item.get('reasoning', '')}"
        for i, item in enumerate(must_fix_items)
    )

    fix_prompt = (
        f"仲裁裁决要求你修复以下 {len(must_fix_items)} 个问题。\n"
        f"只修复这些具体问题，不要做其他改动。\n"
        f"提交前请用 run_code_snippet 自测修复后的代码。\n\n"
        f"{fix_list}"
    )

    STRATEGY_ANGLES = [
        "换一种数据结构或算法来实现同样功能",
        "换一个实现层级（如从函数级改为模块级或路由级）",
        "换一种依赖库来解决问题",
        "简化需求范围，只修核心部分",
    ]
    strategy_idx = 0
    new_code = state.get("current_code", "")
    all_fix_msgs: list[dict] = []

    for attempt in range(3):
        current_prompt = fix_prompt if attempt == 0 else (
            f"前一次修复失败了。请从不同角度考虑：\n"
            f"策略：{STRATEGY_ANGLES[strategy_idx % len(STRATEGY_ANGLES)]}\n\n"
            f"原始问题：\n{fix_list}\n\n"
            f"提交前请用 run_code_snippet 自测修复后的代码。"
        )

        if attempt > 0 and state.get("enable_interrupt"):
            user_response = interrupt({
                "type": "strategy_review",
                "attempt": attempt + 1,
                "strategy": STRATEGY_ANGLES[strategy_idx % len(STRATEGY_ANGLES)],
                "original_issues": fix_list,
            })
            if user_response and isinstance(user_response, dict):
                if user_response.get("action") == "user_strategy":
                    current_prompt = (
                        f"用户建议的修复思路：{user_response.get('message', '')}\n\n"
                        f"原始问题：\n{fix_list}\n\n"
                        f"请按用户思路修复，提交前用 run_code_snippet 自测。"
                    )

        await _notify({"type": "agent_start", "agent": "coder"})
        await _notify({"type": "fix_progress", "attempt": attempt + 1, "max_attempts": 3})

        start = time.monotonic()
        response = await coder_agent.speak(ctx, current_prompt, budget)
        record_agent_call("coder", response.tokens_used, time.monotonic() - start)

        if response.code:
            new_code = response.code
            ctx.current_code = new_code

        fix_msg = {
            "agent": "coder",
            "content": f"[修复 attempt {attempt+1}] {response.content}",
            "round": state["round"] + 1,
            "code": response.code,
            "structured": response.structured,
        }
        await _notify({"type": "message", **fix_msg})
        all_fix_msgs.append(fix_msg)

        if response.code:
            break

        strategy_idx += 1

    # Arbitrator reviews the fix
    await _notify({
        "type": "status",
        "content": "Arbitrator 正在复核修复结果...",
    })

    ctx.current_code = new_code
    reviews = await arbitrator_agent.review_fixes(ctx, budget, must_fix_items)

    not_fixed = [r for r in reviews if r.get("status") != "fixed"]

    if not_fixed:
        await _notify({
            "type": "status",
            "content": f"复核发现 {len(not_fixed)} 项未完全修复，Coder 正在补修...",
        })

        not_fixed_desc = "\n".join(
            f"- {r.get('dispute_id', '?')}: {r.get('review_comment', '')}"
            for r in not_fixed
        )
        refix_prompt = (
            f"Arbitrator 复核发现以下 {len(not_fixed)} 项未正确修复：\n"
            f"{not_fixed_desc}\n"
            f"请针对性修复，提交前用 run_code_snippet 自测。"
        )

        start = time.monotonic()
        refix_response = await coder_agent.speak(ctx, refix_prompt, budget)
        record_agent_call("coder", refix_response.tokens_used, time.monotonic() - start)

        if refix_response.code:
            new_code = refix_response.code

        refix_msg = {
            "agent": "coder",
            "content": f"[补修] {refix_response.content}",
            "round": state["round"] + 1,
            "code": refix_response.code,
            "structured": refix_response.structured,
        }
        await _notify({"type": "message", **refix_msg})

        return {
            "current_code": new_code,
            "messages": all_fix_msgs + [refix_msg],
            "budget_spent": budget.spent,
            "converged": True,
            "convergence_reason": "仲裁后修复完成（含补修）",
        }

    return {
        "current_code": new_code,
        "messages": all_fix_msgs,
        "budget_spent": budget.spent,
        "converged": True,
        "convergence_reason": "仲裁后修复完成",
    }


async def judge_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)

    await _notify({"type": "phase_change", "phase": "judging"})
    await _notify({"type": "agent_start", "agent": "judge"})

    set_stream_callback(_make_stream_cb("judge"))
    report = await judge_agent.summarize(ctx, budget)
    set_stream_callback(None)
    await _notify({"type": "stream_end", "agent": "judge"})
    return {
        "judge_report": report,
        "budget_spent": budget.spent,
    }


# ─── Resolution loop nodes ────────────────────────────────────────────────

MAX_RESOLUTION_RETRIES = 2
RETRY_BUDGET_RESERVE = 0.15


async def resolution_check_node(state: DebateState) -> dict:
    """Check if Judge found unresolved issues. Route to retry, user decision, or done."""
    judge_report = state.get("judge_report", {})
    unresolved = judge_report.get("unresolved_issues", [])
    retry_count = state.get("retry_count", 0)

    if not unresolved:
        await _notify({
            "type": "status",
            "content": "所有问题已解决，交付完成代码。",
        })
        return {"user_decision": "all_resolved"}

    budget_total = state.get("budget_total", 100_000)
    budget_spent = state.get("budget_spent", 0)
    budget_remaining_ratio = (budget_total - budget_spent) / max(budget_total, 1)
    has_budget = budget_remaining_ratio > RETRY_BUDGET_RESERVE
    can_retry = retry_count < MAX_RESOLUTION_RETRIES and has_budget

    if can_retry:
        await _notify({
            "type": "status",
            "content": (
                f"Judge 发现 {len(unresolved)} 个未解决问题，"
                f"自动进入聚焦修复（第 {retry_count + 1}/{MAX_RESOLUTION_RETRIES} 次）..."
            ),
        })
        return {"user_decision": "auto_retry"}

    await _notify({
        "type": "status",
        "content": (
            f"仍有 {len(unresolved)} 个未解决问题，"
            f"{'重试次数已用完' if retry_count >= MAX_RESOLUTION_RETRIES else '预算不足'}。"
        ),
    })
    return {"user_decision": "needs_user_decision"}


def _resolution_check_edge(state: DebateState) -> str:
    decision = state.get("user_decision", "all_resolved")
    if decision == "all_resolved":
        return "done"
    if decision == "auto_retry":
        return "focused_retry"
    return "user_decision"


async def focused_retry_node(state: DebateState) -> dict:
    """Targeted fix for unresolved issues — only relevant attackers verify."""
    ctx, budget = _build_context(state)
    judge_report = state.get("judge_report", {})
    unresolved = judge_report.get("unresolved_issues", [])
    retry_count = state.get("retry_count", 0)

    await _notify({"type": "phase_change", "phase": "fixing"})

    # Build focused fix prompt from unresolved issues
    issue_list = "\n".join(
        f"{i+1}. {item.get('issue', '')} — 当前状态: {item.get('current_status', '?')} "
        f"(影响: {item.get('impact', '?')})"
        for i, item in enumerate(unresolved)
    )

    fix_prompt = (
        f"Judge 评审发现以下 {len(unresolved)} 个问题仍未解决。\n"
        f"请只针对这些问题修复，不要改动其他部分。\n"
        f"提交前用 run_code_snippet 自测。\n\n"
        f"{issue_list}"
    )

    await _notify({"type": "agent_start", "agent": "coder"})
    start = time.monotonic()
    response = await coder_agent.speak(ctx, fix_prompt, budget)
    record_agent_call("coder", response.tokens_used, time.monotonic() - start)

    new_code = response.code or state.get("current_code", "")
    fix_msg = {
        "agent": "coder",
        "content": f"[聚焦修复 retry {retry_count + 1}] {response.content}",
        "round": state["round"] + 1,
        "code": response.code,
        "structured": response.structured,
    }
    await _notify({"type": "message", **fix_msg})

    # Determine which attackers need to verify (based on unresolved issue categories)
    categories_needed = set()
    for item in unresolved:
        issue_text = (item.get("issue", "") + item.get("suggestion", "")).lower()
        if any(kw in issue_text for kw in ("安全", "注入", "xss", "认证", "密码", "加密", "security")):
            categories_needed.add("security")
        if any(kw in issue_text for kw in ("性能", "复杂度", "内存", "缓存", "performance", "o(n")):
            categories_needed.add("performance")
        if any(kw in issue_text for kw in ("边界", "空", "null", "并发", "逻辑", "correctness")):
            categories_needed.add("correctness")

    if not categories_needed:
        categories_needed = {"correctness"}

    # Run only relevant attackers for verification
    verify_state = {**state, "current_code": new_code, "round": state["round"] + 1}
    agents_map = {
        "security": (security_agent, "security"),
        "performance": (performance_agent, "performance"),
        "correctness": (correctness_agent, "correctness"),
    }

    verify_msgs = [fix_msg]

    async def verify_with_attacker(name, agent_instance):
        verify_prompt = (
            f"Coder 刚刚修复了以下问题，请验证修复是否有效：\n{issue_list}\n\n"
            f"如果问题已解决，stance 设为 satisfied。如果仍有问题，指出。"
        )
        try:
            await _notify({"type": "agent_start", "agent": name})
            s = time.monotonic()
            resp = await agent_instance.speak(ctx, verify_prompt, budget)
            record_agent_call(name, resp.tokens_used, time.monotonic() - s)
            return {
                "agent": name,
                "content": f"[聚焦验证] {resp.content}",
                "round": state["round"] + 1,
                "structured": resp.structured,
            }
        except Exception as e:
            logger.warning("focused_verify_%s_failed error=%s", name, e)
            return None

    verify_results = await asyncio.gather(*[
        verify_with_attacker(name, agents_map[name][0])
        for name in categories_needed
        if name in agents_map
    ])

    for msg in verify_results:
        if msg:
            verify_msgs.append(msg)
            await _notify({"type": "message", **msg})

    return {
        "current_code": new_code,
        "messages": verify_msgs,
        "budget_spent": budget.spent,
        "retry_count": retry_count + 1,
        "judge_report": {},
    }


async def user_decision_node(state: DebateState) -> dict:
    """When retries exhausted, let user decide: accept, retry with context, or stop."""
    judge_report = state.get("judge_report", {})
    unresolved = judge_report.get("unresolved_issues", [])

    await _notify({"type": "phase_change", "phase": "user_decision"})

    if state.get("enable_interrupt"):
        user_input = interrupt({
            "type": "resolution_decision",
            "unresolved_issues": unresolved,
            "retry_count": state.get("retry_count", 0),
            "options": [
                {"action": "accept", "label": "接受当前结果"},
                {"action": "retry_with_context", "label": "补充上下文后重试"},
                {"action": "stop", "label": "停止，手动修复"},
            ],
        })

        if user_input and isinstance(user_input, dict):
            action = user_input.get("action", "accept")

            if action == "retry_with_context":
                extra = user_input.get("context", "")
                return {
                    "extra_context": extra,
                    "user_decision": "auto_retry",
                    "retry_count": state.get("retry_count", 0),
                }

            if action == "stop":
                return {"user_decision": "user_stopped"}

    return {"user_decision": "user_accepted"}


def _user_decision_edge(state: DebateState) -> str:
    decision = state.get("user_decision", "user_accepted")
    if decision == "auto_retry":
        return "focused_retry"
    return "done"


# ─── Flash mode nodes ──────────────────────────────────────────────────────

def _mode_router_edge(state: DebateState) -> str:
    if state.get("mode") == "flash":
        return "flash"
    return "pro"


async def flash_generate_node(state: DebateState) -> dict:
    """Flash mode: Coder generates code with self-check, no debate."""
    ctx, budget = _build_context(state)
    ctx.round = 1

    await _notify({"type": "phase_change", "phase": "coding"})
    await _notify({"type": "status", "content": "Flash 模式 — 快速生成中..."})
    await _notify({"type": "agent_start", "agent": "coder"})

    extra = state.get("extra_context", "")
    prompt = (
        f"根据以下需求生成代码：\n{ctx.requirement}\n\n"
        "要求：\n"
        "1. 代码必须完整、可直接运行\n"
        "2. 包含必要的输入验证和错误处理\n"
        "3. 提交前用 run_code_snippet 自测代码能否正常运行\n"
        "4. 如果自测发现问题，立即修复后再提交\n"
    )
    if extra:
        prompt += f"\n补充需求：{extra}"

    start = time.monotonic()
    set_stream_callback(_make_stream_cb("coder"))
    response = await coder_agent.speak(ctx, prompt, budget)
    set_stream_callback(None)
    record_agent_call("coder", response.tokens_used, time.monotonic() - start)

    await _notify({"type": "stream_end", "agent": "coder"})

    code = response.code or ""
    msg = {
        "agent": "coder",
        "content": response.content,
        "round": 1,
        "code": code,
        "structured": response.structured,
    }
    await _notify({"type": "message", **msg})

    flash_report = {
        "star_rating": 3,
        "star_comment": "Flash 模式快速生成，未经多维度深度审查",
        "resolved_issues": [],
        "unresolved_issues": [],
        "score_security": 0,
        "score_performance": 0,
        "score_correctness": 0,
        "usage_advice": "此代码由 Flash 模式生成，已通过基本自检。如需安全/性能/正确性深度审查，请使用 Pro 模式。",
        "confidence": 0.6,
    }

    return {
        "round": 1,
        "current_code": code,
        "messages": [msg],
        "budget_spent": budget.spent,
        "converged": True,
        "convergence_reason": "Flash 模式 — 快速生成完成",
        "judge_report": flash_report,
    }


# ─── Graph builder ──────────────────────────────────────────────────────────

_compiled_graph = None


def build_debate_graph():
    graph = StateGraph(DebateState)

    # Mode router (entry point)
    graph.add_node("mode_router", lambda state: {})
    # Flash path
    graph.add_node("flash_generate", flash_generate_node)
    # Pro path (full debate)
    graph.add_node("plan", plan_node)
    graph.add_node("coder", coder_node)
    graph.add_node("security", security_node)
    graph.add_node("performance", performance_node)
    graph.add_node("correctness", correctness_node)
    graph.add_node("cross_review", cross_review_node)
    graph.add_node("arbitration", arbitration_node)
    graph.add_node("final_fix", final_fix_node)
    graph.add_node("judge", judge_node)
    graph.add_node("resolution_check", resolution_check_node)
    graph.add_node("focused_retry", focused_retry_node)
    graph.add_node("user_decision", user_decision_node)

    graph.set_entry_point("mode_router")

    graph.add_conditional_edges(
        "mode_router",
        _mode_router_edge,
        {
            "flash": "flash_generate",
            "pro": "plan",
        },
    )

    # Flash path → END
    graph.add_edge("flash_generate", END)

    # Pro path (existing flow)
    graph.add_edge("plan", "coder")

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
            "budget_exceeded": "arbitration",
        },
    )

    graph.add_conditional_edges(
        "arbitration",
        _arbitration_edge,
        {
            "deliver": "judge",
            "fix": "final_fix",
        },
    )

    graph.add_edge("final_fix", "judge")

    # Resolution loop: judge → resolution_check → (retry → judge | user_decision | done)
    graph.add_edge("judge", "resolution_check")

    graph.add_conditional_edges(
        "resolution_check",
        _resolution_check_edge,
        {
            "done": END,
            "focused_retry": "focused_retry",
            "user_decision": "user_decision",
        },
    )

    graph.add_edge("focused_retry", "judge")

    graph.add_conditional_edges(
        "user_decision",
        _user_decision_edge,
        {
            "focused_retry": "focused_retry",
            "done": END,
        },
    )

    return graph


_uncompiled_graph = None


def _get_uncompiled_graph():
    global _uncompiled_graph
    if _uncompiled_graph is None:
        _uncompiled_graph = build_debate_graph()
    return _uncompiled_graph


# ─── Full pipeline: pre-processing → graph → post-processing ───────────────

async def run_debate_with_graph(
    requirement: str,
    language: str = "python",
    framework: str | None = None,
    config: DebateConfig | None = None,
    api_key: str | None = None,
    on_progress: callable = None,
    interrupt_handler: callable = None,
) -> DebateResult:
    """Run a full debate through LangGraph with Memory/TestRunner/ComplexityRouter."""
    _progress_callback.set(on_progress)

    config = config or DebateConfig()
    start_time = time.monotonic()

    is_flash = config.mode == "flash"

    if is_flash:
        await _notify({"type": "status", "content": "Flash 模式启动..."})
    else:
        await _notify({"type": "status", "content": "正在理解需求..."})

    # --- Pre-processing: requirement parsing + complexity routing ---
    parsed_req = await parse_requirement(requirement, language, framework)

    if not is_flash:
        complexity = route_complexity(requirement, parsed_req)
        complexity_config = get_debate_config(complexity)
        if config.max_rounds == DebateConfig().max_rounds:
            config.max_rounds = complexity_config["max_rounds"]
        if config.attackers == DebateConfig().attackers:
            config.attackers = complexity_config["attackers"]
        if complexity_config.get("skip_cross_review"):
            config.skip_cross_review = True

    # --- Memory retrieval ---
    from app.db.redis import get_redis
    attack_kb = AttackKnowledgeBase()
    user_prefs = UserPreferenceStore(redis_client=get_redis())
    fix_patterns = FixPatternStore()

    experience_prompt = ""
    if not is_flash:
        experiences = await attack_kb.retrieve_relevant(requirement)
        if experiences:
            experience_prompt = attack_kb.build_experience_prompt(experiences)

    preference_prompt = ""
    if api_key:
        prefs = await user_prefs.get_preferences(api_key)
        if prefs:
            preference_prompt = user_prefs.build_preference_prompt(prefs)

    # --- Build initial graph state ---
    # Attackers not in config.attackers get skip-listed so graph nodes skip them
    all_attackers = {"security", "performance", "correctness"}
    skip_list = sorted(all_attackers - set(config.attackers)) if not is_flash else list(all_attackers)

    initial_state: DebateState = {
        "requirement": requirement,
        "language": language,
        "framework": framework or "",
        "mode": config.mode,
        "current_code": "",
        "round": 0,
        "max_rounds": config.max_rounds,
        "messages": [],
        "consensus": {},
        "skip_list": skip_list,
        "extra_context": "",
        "converged": False,
        "budget_spent": 0,
        "budget_total": config.max_tokens,
        "judge_report": {},
        "arbitration_result": {},
        "must_fix_items": [],
        "convergence_reason": "",
        "selected_plan": "",
        "config": {
            "mode": config.mode,
            "max_rounds": config.max_rounds,
            "attackers": config.attackers,
            "model": config.model,
            "max_tokens": config.max_tokens,
            "skip_cross_review": config.skip_cross_review,
        },
        "enable_interrupt": interrupt_handler is not None,
        "retry_count": 0,
        "user_decision": "",
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
    mysql_url = (
        f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )
    async with AIOMySQLSaver.from_conn_string(mysql_url) as checkpointer:
        await checkpointer.setup()
        graph = _get_uncompiled_graph()
        compiled = graph.compile(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())
        graph_config = {"configurable": {"thread_id": thread_id}}
        # Interrupt-aware execution loop (LangGraph 1.x compatible).
        # In LangGraph >=1.0, ainvoke() returns normally at interrupt
        # points instead of raising GraphInterrupt. Detect pending
        # interrupts via get_state().next.
        invoke_input = initial_state
        final_state = None
        max_interrupts = 20

        for _interrupt_round in range(max_interrupts):
            final_state = await compiled.ainvoke(invoke_input, graph_config)
            snapshot = await compiled.aget_state(graph_config)
            if not snapshot.next:
                break
            interrupt_payload = {}
            if snapshot.tasks:
                for task in snapshot.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_payload = task.interrupts[0].value
                        break
            if interrupt_handler:
                user_response = await interrupt_handler(interrupt_payload)
            else:
                user_response = None
            invoke_input = Command(resume=user_response)

        if final_state is None:
            snapshot = await compiled.aget_state(graph_config)
            final_state = snapshot.values if hasattr(snapshot, "values") else {}

    # --- Post-processing: TestRunner (skip in flash mode) ---
    final_code = final_state.get("current_code", "")
    if final_code and not is_flash:
        try:
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
        except Exception as e:
            logger.warning("graph_test_runner_error error=%s", e)

    # --- Post-processing: Memory write-back (skip in flash mode) ---
    if not is_flash:
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

    # --- Notify convergence ---
    final_round = final_state.get("round", 0)
    is_converged = final_state.get("converged", False)
    if is_converged:
        await _notify({"type": "converged", "round": final_round, "reason": "各方达成共识"})

    # --- Metrics ---
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

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

    result = DebateResult(
        code=final_code,
        language=language,
        confidence=judge_report.get("confidence", 0.0),
        debate={
            "total_rounds": final_round,
            "converged": is_converged,
            "consensus_reason": final_state.get(
                "convergence_reason",
                "各方达成共识" if is_converged else "达到最大轮次或预算上限",
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
        converged=is_converged,
        convergence_reason=final_state.get(
            "convergence_reason",
            "各方达成共识" if is_converged else "达到最大轮次或预算上限",
        ),
        metadata={
            "engine": "langgraph",
            "mode": config.mode,
            "thread_id": thread_id,
            "arbitration": final_state.get("arbitration_result") or None,
            "requires_human_review": _needs_human_review(final_state) if not is_flash else False,
        },
    )

    await _notify({"type": "done"})
    _progress_callback.set(None)
    return result
