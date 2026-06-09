from __future__ import annotations

import json
import logging

from app.llm.client import call_agent
from app.llm.model_router import get_model_for_agent
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

    system_prompt = """你是资深需求分析专家。分析用户的编码需求，提取完整的结构化信息。

要求：
- functional（功能点）：列出用户需求中的每一个功能，至少 3-5 条，越详细越好
- constraints（约束条件）：用户明确提到的技术限制或要求
- implicit（隐式需求）：用户没说但生产代码必须有的，至少 5 条，包括：
  · 输入校验（参数类型、长度、格式）
  · 错误处理（异常捕获、错误码、友好提示）
  · 安全防护（注入防护、认证、加密、信息泄露）
  · 日志记录
  · 配置管理（硬编码 → 环境变量）
- edge_cases（边界场景）：至少 5 条，包括：
  · 空值/None/空字符串
  · 超长输入
  · 并发访问/竞态条件
  · 异常中断/超时
  · 恶意输入

每一条用简短的一句话描述，让开发者一看就知道要注意什么。"""

    messages = [{"role": "user", "content": "\n".join(context_parts)}]

    response = await call_agent(
        agent="requirement_parser",
        system_prompt=system_prompt,
        messages=messages,
        tools=[PARSER_TOOL],
        tool_choice={"type": "tool", "name": "submit_analysis"},
        model=get_model_for_agent("requirement_parser"),
        max_tokens=2000,
    )

    return response.structured or {
        "functional": [],
        "constraints": [],
        "implicit": [],
        "edge_cases": [],
    }
