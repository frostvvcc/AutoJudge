from __future__ import annotations

import logging

from app.engine.context import DebateContext
from app.engine.budget import BudgetManager
from app.llm.client import call_agent
from app.config import settings

logger = logging.getLogger(__name__)

JUDGE_SUBMIT_TOOL = {
    "name": "submit_judgment",
    "description": "提交最终评审报告",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "辩论过程的综合总结",
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
            "confidence": {
                "type": "number",
                "description": "对最终代码质量的信心评分（0-1）",
            },
        },
        "required": [
            "summary",
            "total_issues_raised",
            "accepted_and_fixed",
            "rejected_by_coder",
            "key_improvements",
            "risk_security",
            "risk_performance",
            "risk_correctness",
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

        system_prompt = """你是 AutoJudge 的裁判。你的职责是综合整个对话记录，输出结构化的评审报告。

请分析：
1. 对话中发现了多少个问题
2. 哪些被 Coder 接受并修复了
3. 哪些被 Coder 合理反驳了
4. 最终代码的安全/性能/正确性风险各是什么级别
5. 关键改进点是什么
6. 给出你对最终代码的信心评分（0-1）"""

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
