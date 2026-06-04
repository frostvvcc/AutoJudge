from __future__ import annotations

import json
import logging

from app.llm.client import call_agent
from app.config import settings

logger = logging.getLogger(__name__)

PARSER_TOOL = {
    "name": "submit_analysis",
    "description": "提交需求分析结果",
    "input_schema": {
        "type": "object",
        "properties": {
            "functional": {
                "type": "array",
                "items": {"type": "string"},
                "description": "功能点列表",
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "约束条件列表",
            },
            "implicit": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用户没说但应该有的需求：输入校验、错误处理、安全防护",
            },
            "edge_cases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "边界场景：空输入、超长、并发、异常",
            },
        },
        "required": ["functional", "constraints", "implicit", "edge_cases"],
    },
}


async def parse_requirement(
    requirement: str, language: str, framework: str | None = None
) -> dict:
    """Extract structured context from natural language requirement."""
    context_parts = [f"编码需求：{requirement}", f"目标语言：{language}"]
    if framework:
        context_parts.append(f"框架：{framework}")

    system_prompt = """你是需求分析专家。分析用户的编码需求，提取功能点、约束条件、隐式需求和边界场景。
隐式需求是用户没有明确说但生产代码中必须有的（如输入校验、错误处理、安全防护）。
边界场景是可能导致代码出错的极端输入或状态（如空输入、超长字符串、并发访问）。"""

    messages = [{"role": "user", "content": "\n".join(context_parts)}]

    response = await call_agent(
        agent="requirement_parser",
        system_prompt=system_prompt,
        messages=messages,
        tools=[PARSER_TOOL],
        tool_choice={"type": "tool", "name": "submit_analysis"},
        model=settings.haiku_model,
        max_tokens=1000,
    )

    return response.structured or {
        "functional": [],
        "constraints": [],
        "implicit": [],
        "edge_cases": [],
    }
