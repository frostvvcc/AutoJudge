from __future__ import annotations

import logging

from app.engine.context import DebateContext
from app.engine.budget import BudgetManager
from app.llm.client import call_agent
from app.config import settings

logger = logging.getLogger(__name__)

JUDGE_SUBMIT_TOOL = {
    "name": "submit_judgment",
    "description": "提交代码质量报告",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "辩论过程的综合总结",
            },
            "star_rating": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "星级评级（1-5）：5=优秀 4=良好 3=合格 2=待改进 1=需人工介入",
            },
            "star_comment": {
                "type": "string",
                "description": "一句话评语（如：代码通过全部验证，所有问题已修复）",
            },
            "resolved_issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "已解决的问题列表，每条一句话",
            },
            "unresolved_issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue": {"type": "string", "description": "问题描述"},
                        "current_status": {"type": "string", "description": "当前状态"},
                        "impact": {"type": "string", "description": "影响"},
                        "suggestion": {"type": "string", "description": "建议怎么手动修（具体到代码位置）"},
                    },
                    "required": ["issue", "current_status", "impact", "suggestion"],
                },
                "description": "未完全解决的问题列表",
            },
            "total_issues_raised": {
                "type": "integer",
                "description": "总共提出的问题数",
            },
            "accepted_and_fixed": {
                "type": "integer",
                "description": "被接受并修复的问题数",
            },
            "rejected_by_coder": {
                "type": "integer",
                "description": "被 Coder 反驳的问题数",
            },
            "suggestions_noted": {
                "type": "integer",
                "description": "被记录但非必须修复的建议数",
            },
            "key_improvements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关键改进点列表",
            },
            "score_security": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "安全性评分（0-100）",
            },
            "score_performance": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "性能评分（0-100）",
            },
            "score_correctness": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "正确性评分（0-100）",
            },
            "risk_security": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low", "none"],
                "description": "安全风险等级",
            },
            "risk_performance": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low", "none"],
                "description": "性能风险等级",
            },
            "risk_correctness": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low", "none"],
                "description": "正确性风险等级",
            },
            "usage_advice": {
                "type": "string",
                "description": "使用建议：这段代码能不能直接用？需要先做什么？",
            },
            "confidence": {
                "type": "number",
                "description": "对最终代码质量的信心评分（0-1）",
            },
        },
        "required": [
            "summary",
            "star_rating",
            "star_comment",
            "resolved_issues",
            "unresolved_issues",
            "total_issues_raised",
            "accepted_and_fixed",
            "rejected_by_coder",
            "suggestions_noted",
            "key_improvements",
            "score_security",
            "score_performance",
            "score_correctness",
            "risk_security",
            "risk_performance",
            "risk_correctness",
            "usage_advice",
            "confidence",
        ],
    },
}


class JudgeAgent:
    name = "judge"

    async def summarize(
        self, context: DebateContext, budget: BudgetManager
    ) -> dict:
        transcript = "\n\n".join(
            f"[Round {m.round}][{m.agent.upper()}] {m.content}"
            for m in context.messages
        )

        system_prompt = """你是 AutoJudge 的报告撰写者。你的读者不是程序员，是普通用户。

你的职责是综合整个对话记录，输出一份用户看得懂的代码质量报告。

请分析并输出：
1. 星级评级（1-5星）和一句话评语
2. 已解决的问题列表（每条一句话）
3. 未完全解决的问题列表（如果有），每条说清楚：当前状态、影响、建议怎么手动修
4. 安全/性能/正确性的百分比评分（0-100）
5. 使用建议：这段代码能不能直接用？还是需要先做什么？
6. 信心评分（0-1）

原则：
- 不说"建议优化"这种空话，说"在第 XX 行加上 YYY"
- 如果代码是凑合出来的，不假装完美——诚实说清楚哪里凑合了
- 用户看完你的报告应该知道：能不能用？不能用的话哪里需要动？怎么动？"""

        messages = [
            {
                "role": "user",
                "content": (
                    f"编码需求：{context.requirement}\n\n"
                    f"最终代码：\n```\n{context.current_code}\n```\n\n"
                    f"完整对话记录：\n{transcript}"
                ),
            }
        ]

        response = await call_agent(
            agent="judge",
            system_prompt=system_prompt,
            messages=messages,
            tools=[JUDGE_SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "submit_judgment"},
            max_tokens=budget.get_max_tokens("judge"),
        )

        budget.record("judge", response.tokens_used)
        budget.record_latency(response.latency_ms)

        return response.structured or {}
