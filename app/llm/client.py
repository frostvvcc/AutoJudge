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
    """Run a code snippet in Docker sandbox with resource limits."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = f"{tmpdir}/snippet.py"
        with open(code_path, "w") as f:
            f.write(code)

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "--rm",
                "--network=none",
                "--read-only",
                "--memory=256m",
                "--cpus=0.5",
                "-v", f"{tmpdir}:/workspace:ro",
                "-w", "/workspace",
                "--tmpfs", "/tmp:size=64m",
                "autojudge-sandbox:latest",
                "python", "snippet.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=15
            )
            output = stdout.decode("utf-8", errors="replace")
            errors = stderr.decode("utf-8", errors="replace")
            if proc.returncode == 0:
                return f"Execution succeeded.\nOutput:\n{output}\nExpected: {expected}"
            else:
                return f"Execution failed (exit {proc.returncode}).\nStderr:\n{errors}\nExpected: {expected}"
        except asyncio.TimeoutError:
            return "Execution timed out after 15s."
        except FileNotFoundError:
            return "Docker is not available. Code verification requires Docker for sandbox isolation."


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



# ─── Backend 3: Anthropic-compatible proxy (SSE streaming) ──────────────────

async def _stream_anthropic_sse(http, url: str, headers: dict, body: dict) -> dict:
    """Send a streaming request and reassemble SSE chunks into a full response."""
    body["stream"] = True
    content_blocks: list[dict] = []
    current_block: dict | None = None
    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_creation = 0
    stop_reason = None

    async with http.stream("POST", url, headers=headers, json=body) as resp:
        if resp.status_code != 200:
            error_body = ""
            async for chunk in resp.aiter_text():
                error_body += chunk
                if len(error_body) > 300:
                    break
            raise RuntimeError(f"Proxy API error {resp.status_code}: {error_body[:300]}")

        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload.strip() == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "message_start":
                msg = event.get("message", {})
                usage = msg.get("usage", {})
                input_tokens += usage.get("input_tokens", 0)
                cache_read += usage.get("cache_read_input_tokens", 0)
                cache_creation += usage.get("cache_creation_input_tokens", 0)

            elif etype == "content_block_start":
                block = event.get("content_block", {})
                current_block = dict(block)
                if block.get("type") == "tool_use":
                    current_block.setdefault("input", {})
                    current_block["_input_json"] = ""

            elif etype == "content_block_delta":
                delta = event.get("delta", {})
                if current_block is None:
                    continue
                if delta.get("type") == "text_delta":
                    current_block.setdefault("text", "")
                    current_block["text"] += delta.get("text", "")
                elif delta.get("type") == "input_json_delta":
                    current_block["_input_json"] += delta.get("partial_json", "")

            elif etype == "content_block_stop":
                if current_block is not None:
                    raw = current_block.pop("_input_json", "")
                    if raw:
                        try:
                            current_block["input"] = json.loads(raw)
                        except json.JSONDecodeError:
                            current_block["input"] = {}
                    content_blocks.append(current_block)
                    current_block = None

            elif etype == "message_delta":
                delta = event.get("delta", {})
                stop_reason = delta.get("stop_reason", stop_reason)
                usage = event.get("usage", {})
                output_tokens += usage.get("output_tokens", 0)

    return {
        "content": content_blocks,
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
        },
    }


async def _call_anthropic_proxy(
    agent: str,
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4000,
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
) -> AgentResponse:
    """Call Anthropic-compatible proxy via SSE streaming (avoids CDN timeout)."""
    import httpx
    from app.llm.model_router import get_model_for_agent

    default_tools, default_tool_choice = _get_tools_for_agent(agent)
    tools = tools or default_tools
    tool_choice = tool_choice or default_tool_choice
    resolved_model = model or get_model_for_agent(agent)

    system_blocks = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    cached_tools = list(tools) if tools else []
    if cached_tools:
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

    body: dict = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "system": system_blocks,
        "messages": messages,
    }
    if cached_tools:
        body["tools"] = cached_tools
    if tool_choice:
        body["tool_choice"] = tool_choice

    url = f"{settings.anthropic_proxy_base_url}/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_proxy_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    start = time.monotonic()

    conv_messages = list(messages)
    total_tokens = 0
    total_cache_read = 0
    total_cache_creation = 0
    max_tool_turns = 10 if agent == "coder" else 0

    async with httpx.AsyncClient(timeout=600) as http:
        for turn in range(max_tool_turns + 1):
            body["messages"] = conv_messages
            is_last_turn = (turn == max_tool_turns)
            if agent == "coder":
                effective_choice = (
                    {"type": "tool", "name": "submit_response"}
                    if is_last_turn
                    else {"type": "any"}
                )
            else:
                effective_choice = tool_choice
            if effective_choice:
                body["tool_choice"] = effective_choice

            data = await _stream_anthropic_sse(http, url, headers, body)

            usage = data.get("usage", {})
            total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            total_cache_read += usage.get("cache_read_input_tokens", 0)
            total_cache_creation += usage.get("cache_creation_input_tokens", 0)

            if agent != "coder" or data.get("stop_reason") != "tool_use":
                break

            pending_tool_calls = []
            has_submit = False
            for block in data.get("content", []):
                if block.get("type") == "tool_use":
                    if block.get("name") == "submit_response":
                        has_submit = True
                    else:
                        pending_tool_calls.append(block)

            if has_submit or not pending_tool_calls:
                break

            conv_messages.append({"role": "assistant", "content": data["content"]})
            tool_results = []
            for tc in pending_tool_calls:
                result_text = await _execute_coder_tool(tc["name"], tc.get("input", {}))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_text,
                })
            conv_messages.append({"role": "user", "content": tool_results})

    elapsed_ms = int((time.monotonic() - start) * 1000)

    content_text = ""
    structured = None
    code = None

    for block in data.get("content", []):
        if block.get("type") == "text":
            content_text += block.get("text", "")
        elif block.get("type") == "tool_use":
            structured = block.get("input", {})
            if "message" in structured:
                content_text = structured["message"]
            if "updated_code" in structured:
                code = structured["updated_code"]

    if code is None and agent == "coder":
        for msg in reversed(conv_messages):
            if msg.get("role") != "assistant":
                continue
            for block in (msg.get("content") or []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    inp = block.get("input", {})
                    if block.get("name") == "submit_response" and inp.get("updated_code"):
                        code = inp["updated_code"]
                        structured = inp
                        break
                    if block.get("name") == "run_code_snippet" and inp.get("code"):
                        code = inp["code"]
                        break
            if code:
                break

    return AgentResponse(
        agent=agent,
        content=content_text,
        code=code,
        structured=structured,
        tokens_used=total_tokens,
        cache_read=total_cache_read,
        cache_creation=total_cache_creation,
        latency_ms=elapsed_ms,
    )


# ─── Unified entry point ─────────────────────────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    err_str = str(exc).lower()
    if isinstance(exc, RuntimeError) and ("timed out" in err_str or "503" in err_str or "524" in err_str):
        return True
    try:
        import httpx
        if isinstance(exc, (httpx.ReadTimeout, httpx.ProxyError, httpx.RemoteProtocolError)):
            return True
    except ImportError:
        pass
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
    if settings.llm_backend == "anthropic_proxy":
        return await _call_anthropic_proxy(
            agent=agent,
            system_prompt=system_prompt,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
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
