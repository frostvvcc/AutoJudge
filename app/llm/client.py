from __future__ import annotations

import asyncio
import json
import time
import logging
import re

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Structured Output Schemas (shared by both backends) ─────────────────────

ATTACKER_JSON_SCHEMA = {
    "message": "(string) 你的完整发言内容",
    "has_new_issues": "(boolean) 本轮是否发现了新问题",
    "stance": "(string: attacking | satisfied) attacking=仍有问题要提，satisfied=没有新问题了",
    "findings": [
        {
            "category": "(string) 问题类别",
            "severity": "(string: critical | high | medium | low)",
            "description": "(string) 问题描述",
            "test_input": "(string, optional) 能触发此问题的具体测试输入",
        }
    ],
}

CODER_JSON_SCHEMA = {
    "message": "(string) 你的完整回应内容",
    "responses": [
        {
            "finding_ref": "(string) 引用哪个 Attacker 的哪个发现",
            "action": "(string: accept_and_fix | rebut_with_evidence)",
            "evidence": "(string, optional) 反驳时的证据",
            "explanation": "(string) 对这个发现的回应说明",
        }
    ],
    "updated_code": "(string) 完整可运行的代码",
}

JUDGE_JSON_SCHEMA = {
    "summary": "(string) 辩论过程综合总结",
    "total_issues_raised": "(integer)",
    "accepted_and_fixed": "(integer)",
    "rejected_by_coder": "(integer)",
    "suggestions_noted": "(integer)",
    "key_improvements": ["(string)"],
    "risk_security": "(string: critical | high | medium | low | none)",
    "risk_performance": "(string: critical | high | medium | low | none)",
    "risk_correctness": "(string: critical | high | medium | low | none)",
    "confidence": "(number 0-1)",
}

REQUIREMENT_JSON_SCHEMA = {
    "functional": ["(string) 功能点"],
    "constraints": ["(string) 约束条件"],
    "implicit": ["(string) 隐式需求"],
    "edge_cases": ["(string) 边界场景"],
}

TEST_JSON_SCHEMA = {
    "test_code": "(string) 完整的 pytest 测试代码",
}

# Schema registry: agent name → which JSON schema to require
AGENT_SCHEMAS = {
    "coder": CODER_JSON_SCHEMA,
    "security": ATTACKER_JSON_SCHEMA,
    "performance": ATTACKER_JSON_SCHEMA,
    "correctness": ATTACKER_JSON_SCHEMA,
    "judge": JUDGE_JSON_SCHEMA,
    "requirement_parser": REQUIREMENT_JSON_SCHEMA,
    "test_generator": TEST_JSON_SCHEMA,
}

# Anthropic SDK tool definitions (used only when llm_backend = "anthropic_api")
ATTACKER_SUBMIT_TOOL = {
    "name": "submit_review",
    "description": "提交你的审查结果，包括自然语言发言和结构化判断",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "你的完整发言内容（自然语言）"},
            "has_new_issues": {"type": "boolean", "description": "本轮是否发现了新问题"},
            "stance": {"type": "string", "enum": ["attacking", "satisfied"], "description": "attacking=仍有问题要提，satisfied=没有新问题了"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                        "description": {"type": "string"},
                        "test_input": {"type": "string", "description": "能触发此问题的具体测试输入（可选）"},
                    },
                    "required": ["category", "severity", "description"],
                },
                "description": "本轮发现的问题列表（没有则为空数组）",
            },
        },
        "required": ["message", "has_new_issues", "stance", "findings"],
    },
}

CODER_SUBMIT_TOOL = {
    "name": "submit_response",
    "description": "提交你对所有攻击的回应，包括反驳和修复",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "你的完整回应内容（自然语言）"},
            "responses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "finding_ref": {"type": "string", "description": "引用哪个 Attacker 的哪个发现"},
                        "action": {"type": "string", "enum": ["accept_and_fix", "rebut_with_evidence"], "description": "接受并修复，或用证据反驳"},
                        "evidence": {"type": "string", "description": "工具验证结果或代码执行输出（反驳时必填）"},
                        "explanation": {"type": "string", "description": "对这个发现的回应说明"},
                    },
                    "required": ["finding_ref", "action", "explanation"],
                },
                "description": "对每个攻击的回应（第一轮无攻击时可为空数组）",
            },
            "updated_code": {"type": "string", "description": "修复后的完整代码（如果有修复），或初版代码"},
        },
        "required": ["message", "responses", "updated_code"],
    },
}

CODER_TOOLS = [
    CODER_SUBMIT_TOOL,
    {
        "name": "run_code_snippet",
        "description": "执行一段代码片段，验证某个行为是否符合预期",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的代码"},
                "expected": {"type": "string", "description": "预期行为描述"},
            },
            "required": ["code", "expected"],
        },
    },
    {
        "name": "check_documentation",
        "description": "查询框架/库的官方文档，验证某个 API 的行为",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要查询的内容"},
            },
            "required": ["query"],
        },
    },
]


# ─── AgentResponse (shared) ──────────────────────────────────────────────────

class AgentResponse:
    def __init__(
        self,
        agent: str,
        content: str,
        code: str | None = None,
        structured: dict | None = None,
        tokens_used: int = 0,
        cache_read: int = 0,
        cache_creation: int = 0,
        latency_ms: int = 0,
    ):
        self.agent = agent
        self.content = content
        self.code = code
        self.structured = structured
        self.tokens_used = tokens_used
        self.cache_read = cache_read
        self.cache_creation = cache_creation
        self.latency_ms = latency_ms


# ─── Backend 1: claude -p (Claude Code CLI) ──────────────────────────────────

def _build_structured_prompt(
    system_prompt: str,
    messages: list[dict],
    agent: str,
) -> str:
    """
    Flatten system + messages into a single prompt string for claude -p.
    Append JSON schema requirement so the model returns structured output.
    """
    parts = []

    # System prompt as context
    parts.append(f"[系统指令]\n{system_prompt}")

    # Conversation history
    for msg in messages:
        role_label = "用户" if msg["role"] == "user" else "助手"
        parts.append(f"\n[{role_label}]\n{msg['content']}")

    # Require JSON structured output
    schema = AGENT_SCHEMAS.get(agent)
    if schema:
        schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
        parts.append(
            f"\n[输出要求]\n"
            f"你必须以 JSON 格式回复，严格遵守以下 schema。"
            f"不要输出任何 JSON 以外的内容，不要用 markdown 代码块包裹。\n"
            f"Schema:\n{schema_str}"
        )

    return "\n".join(parts)


def _extract_json_from_text(text: str) -> dict | None:
    """
    Extract JSON object from claude -p output.
    Handles cases where the model wraps JSON in markdown code blocks.
    """
    cleaned = text.strip()

    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ```) and last line (```)
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        cleaned = "\n".join(lines[start:end]).strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


async def _call_claude_cli(
    agent: str,
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4000,
) -> AgentResponse:
    """
    Call claude -p (Claude Code piped mode) as subprocess.
    No API key needed — uses your logged-in Claude Code session.
    """
    prompt = _build_structured_prompt(system_prompt, messages, agent)

    cmd = [settings.claude_cli_path, "-p", "--output-format", "text"]
    if settings.claude_cli_model:
        cmd.extend(["--model", settings.claude_cli_model])
    cmd.extend(["--max-turns", "1"])

    start = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=settings.claude_cli_timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise TimeoutError(f"claude -p timed out after {settings.claude_cli_timeout}s for agent {agent}")

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {err_msg[:500]}")

    raw_output = stdout.decode("utf-8", errors="replace").strip()

    if not raw_output:
        raise RuntimeError(f"claude -p returned empty output for agent {agent}")

    # Parse structured JSON from output
    structured = _extract_json_from_text(raw_output)
    content = ""
    code = None

    if structured:
        content = structured.get("message", raw_output)
        code = structured.get("updated_code")
        if structured.get("test_code"):
            content = structured["test_code"]
    else:
        content = raw_output
        logger.warning("json_parse_failed", agent=agent, raw_length=len(raw_output))

    # Estimate token count from character length (~1.5 chars/token for mixed CJK+English)
    estimated_tokens = len(prompt + raw_output) // 2

    return AgentResponse(
        agent=agent,
        content=content,
        code=code,
        structured=structured,
        tokens_used=estimated_tokens,
        latency_ms=elapsed_ms,
    )


# ─── Backend 2: Anthropic SDK (direct API) ───────────────────────────────────

def _get_anthropic_client():
    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _parse_api_response(response, agent: str) -> AgentResponse:
    """Extract structured output from Anthropic API tool_use blocks."""
    content_text = ""
    structured = None
    code = None

    for block in response.content:
        if block.type == "text":
            content_text += block.text
        elif block.type == "tool_use":
            structured = block.input
            if "message" in structured:
                content_text = structured["message"]
            if "updated_code" in structured:
                code = structured["updated_code"]

    tokens = response.usage.input_tokens + response.usage.output_tokens
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

    return AgentResponse(
        agent=agent,
        content=content_text,
        code=code,
        structured=structured,
        tokens_used=tokens,
        cache_read=cache_read,
        cache_creation=cache_creation,
    )


def _get_tools_for_agent(agent: str) -> tuple[list[dict], dict]:
    """Get tool definitions and tool_choice for Anthropic API mode."""
    if agent == "coder":
        return CODER_TOOLS, {"type": "tool", "name": "submit_response"}
    elif agent in ("security", "performance", "correctness"):
        return [ATTACKER_SUBMIT_TOOL], {"type": "tool", "name": "submit_review"}
    elif agent == "judge":
        from app.agents.judge import JUDGE_SUBMIT_TOOL
        return [JUDGE_SUBMIT_TOOL], {"type": "tool", "name": "submit_judgment"}
    elif agent == "requirement_parser":
        from app.engine.requirement_parser import PARSER_TOOL
        return [PARSER_TOOL], {"type": "tool", "name": "submit_analysis"}
    elif agent == "test_generator":
        tool = {
            "name": "submit_tests",
            "description": "提交测试代码",
            "input_schema": {
                "type": "object",
                "properties": {"test_code": {"type": "string", "description": "完整的 pytest 测试代码"}},
                "required": ["test_code"],
            },
        }
        return [tool], {"type": "tool", "name": "submit_tests"}
    return [], {"type": "auto"}


async def _call_anthropic_api(
    agent: str,
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4000,
) -> AgentResponse:
    """Call Anthropic API directly with tool_use structured output."""
    import anthropic

    client = _get_anthropic_client()
    tools, tool_choice = _get_tools_for_agent(agent)

    system_blocks = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    cached_tools = list(tools)
    if cached_tools:
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

    start = time.monotonic()
    response = await client.messages.create(
        model=model or settings.default_model,
        system=system_blocks,
        messages=messages,
        tools=cached_tools,
        tool_choice=tool_choice,
        max_tokens=max_tokens,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)

    result = _parse_api_response(response, agent)
    result.latency_ms = elapsed_ms
    return result


# ─── Unified entry point ─────────────────────────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, RuntimeError) and "timed out" in str(exc).lower():
        return True
    try:
        import anthropic
        if isinstance(exc, (anthropic.APITimeoutError, anthropic.RateLimitError)):
            return True
    except ImportError:
        pass
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(_is_retryable),
)
async def call_agent(
    agent: str,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    model: str | None = None,
    max_tokens: int = 4000,
) -> AgentResponse:
    """
    Unified agent call — routes to claude -p or Anthropic API based on config.

    When using claude -p:
      - tools/tool_choice params are ignored (structured output via JSON prompt)
      - model param is ignored (uses claude CLI's configured model)
      - No API key needed

    When using anthropic_api:
      - Full tool_use support with forced structured output
      - Requires ANTHROPIC_API_KEY
    """
    if settings.llm_backend == "claude_cli":
        return await _call_claude_cli(
            agent=agent,
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
        )
    else:
        return await _call_anthropic_api(
            agent=agent,
            system_prompt=system_prompt,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
        )
