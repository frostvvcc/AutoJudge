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

import contextvars

from app.config import settings

logger = logging.getLogger(__name__)

_stream_callback: contextvars.ContextVar[callable | None] = contextvars.ContextVar(
    '_stream_callback', default=None
)


def set_stream_callback(cb: callable | None):
    _stream_callback.set(cb)


async def _emit_stream(text: str):
    cb = _stream_callback.get(None)
    if cb:
        try:
            await cb(text)
        except Exception:
            pass





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
                        "line_start": {"type": "integer", "description": "问题代码的起始行号（必填，从1开始）"},
                        "line_end": {"type": "integer", "description": "问题代码的结束行号（必填，与line_start相同则为单行）"},
                    },
                    "required": ["category", "severity", "description", "line_start", "line_end"],
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

CODER_TOOLS = [CODER_SUBMIT_TOOL]


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



AGENT_TEMPERATURE = {
    "coder": 0.3,
    "planner": 0.5,
    "security": 0.7,
    "performance": 0.7,
    "correctness": 0.7,
    "judge": 0.3,
    "arbitrator": 0.4,
    "cross_review": 0.5,
    "compressor": 0.2,
    "requirement_parser": 0.3,
    "test_generator": 0.3,
}


# ─── Backend 2: Anthropic SDK (direct API) ───────────────────────────────────

def _get_anthropic_client(api_key: str | None = None):
    import anthropic
    return anthropic.AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)


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


async def _call_anthropic_api(
    agent: str,
    system_prompt: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4000,
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    api_key: str | None = None,
) -> AgentResponse:
    """Call Anthropic API directly with tool_use structured output."""
    import anthropic
    from app.llm.model_router import get_model_for_agent

    client = _get_anthropic_client(api_key=api_key)
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

    temperature = AGENT_TEMPERATURE.get(agent, 0.5)

    start = time.monotonic()

    has_stream_cb = _stream_callback.get(None) is not None
    if has_stream_cb:
        async with client.messages.stream(
            model=resolved_model,
            system=system_blocks,
            messages=messages,
            tools=cached_tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
        ) as stream:
            async for text in stream.text_stream:
                await _emit_stream(text)
            response = await stream.get_final_message()
    else:
        response = await client.messages.create(
            model=resolved_model,
            system=system_blocks,
            messages=messages,
            tools=cached_tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)

    result = _parse_api_response(response, agent)
    result.tokens_used = response.usage.input_tokens + response.usage.output_tokens
    result.cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    result.cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
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
                    chunk = delta.get("text", "")
                    current_block["text"] += chunk
                    if chunk:
                        await _emit_stream(chunk)
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
    api_key: str | None = None,
    base_url: str | None = None,
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

    temperature = AGENT_TEMPERATURE.get(agent, 0.5)

    body: dict = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "system": system_blocks,
        "messages": messages,
        "temperature": temperature,
    }
    if cached_tools:
        body["tools"] = cached_tools
    if tool_choice:
        body["tool_choice"] = tool_choice

    resolved_base_url = base_url or settings.anthropic_proxy_base_url
    resolved_api_key = api_key or settings.anthropic_proxy_api_key
    url = f"{resolved_base_url}/v1/messages"
    headers = {
        "x-api-key": resolved_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    start = time.monotonic()

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=400, write=30, pool=30)) as http:
        data = await _stream_anthropic_sse(http, url, headers, body)

    usage = data.get("usage", {})
    total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    total_cache_read = usage.get("cache_read_input_tokens", 0)
    total_cache_creation = usage.get("cache_creation_input_tokens", 0)
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

    if agent == "judge":
        block_types = [b.get("type") for b in data.get("content", [])]
        logger.info("proxy_judge_response stop=%s blocks=%s structured_keys=%s",
                     data.get("stop_reason"), block_types,
                     list(structured.keys()) if isinstance(structured, dict) and structured else "empty")

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
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    err_str = str(exc).lower()
    if isinstance(exc, RuntimeError) and any(
        kw in err_str for kw in ("timed out", "502", "503", "524", "bad gateway", "upstream")
    ):
        return True
    try:
        import httpx
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.ProxyError,
                            httpx.RemoteProtocolError, httpx.ConnectTimeout)):
            return True
    except ImportError:
        pass
    try:
        import anthropic
        if isinstance(exc, (anthropic.APITimeoutError, anthropic.RateLimitError,
                            anthropic.APIConnectionError)):
            return True
    except ImportError:
        pass
    return False


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=3, max=45),
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
    """Unified agent call — routes to proxy or direct API based on config."""
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
