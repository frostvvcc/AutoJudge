"""
MCP Server for code analysis tools (bandit + semgrep).
Attackers call these tools via MCP protocol for real static analysis.

Can be used in two ways:
1. Direct import: SecurityAttacker imports bandit_scan/semgrep_scan directly
2. MCP Server: run as standalone process for MCP protocol access
   python -m app.mcp.servers.code_analysis
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)

server = None


async def bandit_scan(code: str, language: str = "python") -> dict:
    """Run bandit security scan on code snippet."""
    if language != "python":
        return {"results": [], "note": f"bandit only supports Python, got {language}"}

    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False
    ) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                ["bandit", "-r", f.name, "-f", "json", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout.strip():
                return json.loads(result.stdout)
            return {"results": [], "errors": result.stderr}
        except FileNotFoundError:
            return {
                "results": [],
                "error": "bandit not installed",
            }
        except subprocess.TimeoutExpired:
            return {"results": [], "error": "scan timeout"}
        except json.JSONDecodeError:
            return {
                "results": [],
                "error": "invalid bandit output",
                "raw": result.stdout[:500],
            }


async def semgrep_scan(code: str, language: str = "python") -> dict:
    """Run semgrep scan on code snippet."""
    suffix_map = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "java": ".java",
        "go": ".go",
        "rust": ".rs",
    }
    suffix = suffix_map.get(language, ".py")

    with tempfile.NamedTemporaryFile(
        suffix=suffix, mode="w", delete=False
    ) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [
                    "semgrep",
                    "--config",
                    "auto",
                    f.name,
                    "--json",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout.strip():
                return json.loads(result.stdout)
            return {"results": [], "errors": result.stderr}
        except FileNotFoundError:
            return {
                "results": [],
                "error": "semgrep not installed",
            }
        except subprocess.TimeoutExpired:
            return {"results": [], "error": "scan timeout"}
        except json.JSONDecodeError:
            return {
                "results": [],
                "error": "invalid semgrep output",
            }


def _build_mcp_server():
    """Build MCP Server with tool registrations (called at module load or __main__)."""
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent

        srv = Server("code-analysis")

        @srv.list_tools()
        async def list_tools():
            return [
                Tool(
                    name="bandit_scan",
                    description="Run bandit security scan on Python code",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "language": {"type": "string", "default": "python"},
                        },
                        "required": ["code"],
                    },
                ),
                Tool(
                    name="semgrep_scan",
                    description="Run semgrep scan on code",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "language": {"type": "string", "default": "python"},
                        },
                        "required": ["code"],
                    },
                ),
            ]

        @srv.call_tool()
        async def call_tool(name: str, arguments: dict):
            if name == "bandit_scan":
                result = await bandit_scan(arguments["code"], arguments.get("language", "python"))
            elif name == "semgrep_scan":
                result = await semgrep_scan(arguments["code"], arguments.get("language", "python"))
            else:
                result = {"error": f"Unknown tool: {name}"}
            return [TextContent(type="text", text=json.dumps(result))]

        return srv
    except ImportError:
        return None


if __name__ == "__main__":
    srv = _build_mcp_server()
    if srv is not None:
        import asyncio
        from mcp.server.stdio import stdio_server

        async def main():
            init_options = srv.create_initialization_options()
            async with stdio_server() as (read, write):
                await srv.run(read, write, init_options)

        asyncio.run(main())
    else:
        print("MCP SDK not installed. Install with: pip install mcp")
