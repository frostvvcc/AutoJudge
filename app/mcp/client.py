"""
MCP Client for code-analysis server.

Connects to the code_analysis MCP Server via stdio transport,
providing process-isolated access to bandit and semgrep scanning.

Why MCP instead of direct import:
- Process isolation: bandit/semgrep crash on malicious input won't take down the main process
- Protocol standardization: swap tools (e.g. CodeQL) without changing SecurityAttacker code
- Security boundary: tools can only interact through declared MCP interfaces
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

_client: CodeAnalysisClient | None = None


class CodeAnalysisClient:

    def __init__(self):
        self._session = None
        self._exit_stack: AsyncExitStack | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp.servers.code_analysis"],
        )

        streams = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(*streams)
        )
        await self._session.initialize()

        tools_result = await self._session.list_tools()
        tool_names = sorted(t.name for t in tools_result.tools)
        logger.info("mcp_code_analysis_connected tools=%s", tool_names)

        self._connected = True

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if not self._connected:
            async with self._lock:
                if not self._connected:
                    await self.connect()

        result = await self._session.call_tool(tool_name, arguments=arguments)

        if result.isError:
            logger.warning("mcp_tool_error tool=%s", tool_name)
            return {"results": [], "error": "MCP tool returned error"}

        if result.content:
            return json.loads(result.content[0].text)

        return {"results": []}

    async def close(self):
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._session = None
            self._connected = False
            logger.info("mcp_code_analysis_closed")


async def get_code_analysis_client() -> CodeAnalysisClient:
    global _client
    if _client is None:
        _client = CodeAnalysisClient()
    return _client


async def close_code_analysis_client():
    global _client
    if _client is not None:
        await _client.close()
        _client = None
