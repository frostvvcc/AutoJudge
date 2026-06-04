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
    "star_rating": "(integer 1-5) 星级评级",
    "star_comment": "(string) 一句话评语",
    "resolved_issues": ["(string) 已解决的问题"],
    "unresolved_issues": [{"issue": "(string)", "current_status": "(string)", "impact": "(string)", "suggestion": "(string)"}],
    "total_issues_raised": "(integer)",
    "accepted_and_fixed": "(integer)",
    "rejected_by_coder": "(integer)",
    "suggestions_noted": "(integer)",
    "key_improvements": ["(string)"],
    "score_security": "(integer 0-100) 安全性评分",
    "score_performance": "(integer 0-100) 性能评分",
    "score_correctness": "(integer 0-100) 正确性评分",
    "risk_security": "(string: critical | high | medium | low | none)",
    "risk_performance": "(string: critical | high | medium | low | none)",
    "risk_correctness": "(string: critical | high | medium | low | none)",
    "usage_advice": "(string) 使用建议",
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
            f"在完成所有分析和验证后，你的最终回复必须是一个纯 JSON 对象。"
            f"严格遵守以下 schema，不要在 JSON 前后添加任何其他文字。"
            f"如果你需要执行代码来验证，先执行完，然后再输出 JSON 结果。\n"
            f"Schema:\n{schema_str}"
        )

    return "\n".join(parts)


def _extract_json_from_text(text: str) -> dict | None:
    """
    Extract JSON object from claude -p output.
    Handles: direct JSON, markdown code blocks, JSON embedded in prose.
    """
    cleaned = text.strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Extract from markdown code blocks (```json ... ``` or ``` ... ```)
    code_block_pattern = re.compile(r"```(?:json)?\s*\n([\s\S]*?)\n\s*```")
    for match in code_block_pattern.finditer(cleaned):
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Find the last JSON object in text (most likely the final output)
    brace_depth = 0
    json_start = -1
    last_json = None
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if brace_depth == 0:
                json_start = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and json_start >= 0:
                candidate = cleaned[json_start : i + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        last_json = parsed
                except json.JSONDecodeError:
                    pass
                json_start = -1

    return last_json


async def _call_claude_cli(
    agent: str,
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 4000,
) -> AgentResponse:
    """
    Call claude -p (Claude Code piped mode) as subprocess.
    No API key needed — uses your logged-in Claude Code session.

    Uses --output-format json for structured result parsing,
    --max-turns 5 for multi-turn tool use (Coder self-test),
    --dangerously-skip-permissions to avoid interactive prompts.
    """
    prompt = _build_structured_prompt(system_prompt, messages, agent)

    max_turns = "5" if agent == "coder" else "1"

    cmd = [
        settings.claude_cli_path, "-p",
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--max-turns", max_turns,
    ]
    if settings.claude_cli_model:
        cmd.extend(["--model", settings.claude_cli_model])

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

    raw_stdout = stdout.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {err_msg[:500]}")

    if not raw_stdout:
        raise RuntimeError(f"claude -p returned empty output for agent {agent}")

    # Parse the JSON envelope from --output-format json
    raw_output = raw_stdout
    actual_tokens = 0
    try:
        envelope = json.loads(raw_stdout)
        raw_output = envelope.get("result", raw_stdout)
        usage = envelope.get("usage", {})
        actual_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    except (json.JSONDecodeError, TypeError):
        pass

    # Extract structured JSON from the result text
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
        # Fallback: extract code blocks from natural language output
        code_blocks = re.findall(r"```(?:python)?\s*\n([\s\S]*?)\n\s*```", raw_output)
        if code_blocks:
            code = max(code_blocks, key=len)
            structured = {
                "message": raw_output,
                "updated_code": code,
                "responses": [],
            }
        if not code_blocks:
            logger.warning("json_parse_failed agent=%s raw_length=%d", agent, len(raw_output))

    tokens_used = actual_tokens if actual_tokens > 0 else len(prompt + raw_output) // 2

    return AgentResponse(
        agent=agent,
        content=content,
        code=code,
        structured=structured,
        tokens_used=tokens_used,
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
        # Use "any" so Coder can call run_code_snippet / check_documentation
        # before submitting final response via submit_response
        return CODER_TOOLS, {"type": "any"}
    elif agent in ("security", "performance", "correctness"):
        return [ATTACKER_SUBMIT_TOOL], {"type": "tool", "name": "submit_review"}
    elif agent == "judge":
        from app.agents.judge import JUDGE_SUBMIT_TOOL
        return [JUDGE_SUBMIT_TOOL], {"type": "tool", "name": "submit_judgment"}
    elif agent == "arbitrator":
        from app.agents.arbitrator import ARBITRATOR_SUBMIT_TOOL
        return [ARBITRATOR_SUBMIT_TOOL], {"type": "tool", "name": "submit_arbitration"}
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


async def _execute_coder_tool(tool_name: str, tool_input: dict) -> str:
    """Execute Coder's verification tools and return result text."""
    if tool_name == "run_code_snippet":
        return await _run_code_snippet(
            tool_input.get("code", ""), tool_input.get("expected", "")
        )
    elif tool_name == "check_documentation":
        return (
            f"Documentation query: {tool_input.get('query', '')}\n"
            "Please verify this based on your knowledge of the framework/library. "
            "If uncertain, note the uncertainty in your response."
        )
    return f"Unknown tool: {tool_name}"


async def _run_code_snippet(code: str, expected: str) -> str:
    """Run a code snippet in a subprocess sandbox and return output."""
    import tempfile

    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False
    ) as f:
        f.write(code)
        f.flush()
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", f.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=10
            )
            output = stdout.decode("utf-8", errors="replace")
            errors = stderr.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                return f"Execution succeeded.\nOutput:\n{output}\nExpected: {expected}"
            else:
                return f"Execution failed (exit {proc.returncode}).\nStderr:\n{errors}\nExpected: {expected}"
        except asyncio.TimeoutError:
            return "Execution timed out after 10s."
        except FileNotFoundError:
            return "Python not available for code execution."


async def _call_anthropic_api(
    agent: str,
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4000,
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
) -> AgentResponse:
    """Call Anthropic API directly with tool_use structured output.

    For Coder agent, implements a tool_use loop: if the model calls
    run_code_snippet or check_documentation, execute the tool and
    continue the conversation until submit_response is called.
    """
    import anthropic
    from app.llm.model_router import get_model_for_agent

    client = _get_anthropic_client()
    default_tools, default_tool_choice = _get_tools_for_agent(agent)
    tools = tools or default_tools
    tool_choice = tool_choice or default_tool_choice
    resolved_model = model or get_model_for_agent(agent)

    system_blocks = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    cached_tools = list(tools)
    if cached_tools:
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

    conv_messages = list(messages)
    total_tokens = 0
    total_cache_read = 0
    total_cache_creation = 0

    start = time.monotonic()
    max_tool_turns = 5

    for turn in range(max_tool_turns + 1):
        response = await client.messages.create(
            model=resolved_model,
            system=system_blocks,
            messages=conv_messages,
            tools=cached_tools,
            tool_choice={"type": "any"} if agent == "coder" else tool_choice,
            max_tokens=max_tokens,
        )

        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        total_cache_read += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        total_cache_creation += getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        if agent != "coder" or response.stop_reason != "tool_use":
            break

        # Check if model called a verification tool (not submit_response)
        pending_tool_calls = []
        has_submit = False
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "submit_response":
                    has_submit = True
                else:
                    pending_tool_calls.append(block)

        if has_submit or not pending_tool_calls:
            break

        # Execute verification tools and continue conversation
        conv_messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in pending_tool_calls:
            result_text = await _execute_coder_tool(tc.name, tc.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_text,
            })
            logger.info(
                "coder_tool_executed",
                tool=tc.name, turn=turn,
            )
        conv_messages.append({"role": "user", "content": tool_results})

    elapsed_ms = int((time.monotonic() - start) * 1000)

    result = _parse_api_response(response, agent)
    result.tokens_used = total_tokens
    result.cache_read = total_cache_read
    result.cache_creation = total_cache_creation
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
            tools=tools,
            tool_choice=tool_choice,
        )
