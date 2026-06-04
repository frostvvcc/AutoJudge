from __future__ import annotations

import logging

from app.agents.base import BaseAgent, SAFETY_SUFFIX
from app.engine.context import DebateContext
from app.engine.budget import BudgetManager
from app.llm.client import ATTACKER_SUBMIT_TOOL, AgentResponse

logger = logging.getLogger(__name__)


class SecurityAttacker(BaseAgent):
    name = "security"
    role = "安全攻击者"

    def get_system_prompt(self, context: DebateContext) -> str:
        base = """你是安全审计专家，专门找代码中的安全漏洞。你的职责：
1. 从 OWASP Top 10 和常见安全问题角度审查代码
2. 每个发现必须包含：具体位置、攻击方式、预期危害
3. 如果 Coder 反驳了你的观点，评估反驳是否合理，合理就承认
4. 你可以支持或质疑其他 Attacker 的发现
5. 当你认为代码安全没有问题时，stance 设为 "satisfied"
6. 不要把建议当 bug 报——区分"必须修"和"建议优化"

重点关注：
- SQL 注入、XSS、CSRF
- 认证与授权缺陷
- 信息泄露（错误消息、日志）
- 输入校验不足
- 敏感数据明文存储
- 密码学误用"""

        parts = [base]

        if context.experience_context:
            parts.append(f"\n{context.experience_context}")

        if context.current_code:
            parts.append(f"\n当前代码：\n```\n{context.current_code}\n```")

        parts.append(SAFETY_SUFFIX.format(role=self.role))

        return "\n".join(parts)

    def get_tools(self) -> list[dict]:
        return [ATTACKER_SUBMIT_TOOL]

    def get_tool_choice(self) -> dict:
        return {"type": "tool", "name": "submit_review"}

    async def speak(
        self,
        context: DebateContext,
        prompt: str,
        budget: BudgetManager,
        model: str | None = None,
    ) -> AgentResponse:
        """LLM reasoning + static analysis tool verification (dual-source attack)."""
        tool_findings = []
        if context.current_code:
            tool_findings = await self._run_static_analysis(context.current_code)

        if tool_findings:
            prompt += (
                "\n\n以下是静态分析工具（bandit/semgrep）的实际扫描结果，"
                "请将这些工具发现纳入你的审查，标注来源为工具验证：\n"
                + "\n".join(tool_findings)
            )

        return await super().speak(context, prompt, budget, model)

    async def _run_static_analysis(self, code: str) -> list[str]:
        findings = []

        try:
            from app.mcp.client import get_code_analysis_client

            client = await get_code_analysis_client()

            bandit_result = await client.call_tool(
                "bandit_scan", {"code": code, "language": "python"}
            )
            for item in bandit_result.get("results", []):
                findings.append(
                    f"[bandit {item.get('test_id', '?')}] "
                    f"Severity: {item.get('issue_severity', '?')} | "
                    f"Line {item.get('line_number', '?')}: "
                    f"{item.get('issue_text', '?')}"
                )

            semgrep_result = await client.call_tool(
                "semgrep_scan", {"code": code, "language": "python"}
            )
            for item in semgrep_result.get("results", []):
                findings.append(
                    f"[semgrep] {item.get('check_id', '?')}: "
                    f"{item.get('extra', {}).get('message', '?')}"
                )

            return findings

        except Exception as e:
            logger.warning("mcp_static_analysis_failed: %s, trying direct import", e)

        return await self._run_static_analysis_fallback(code)

    async def _run_static_analysis_fallback(self, code: str) -> list[str]:
        findings = []
        try:
            from app.mcp.servers.code_analysis import bandit_scan
            result = await bandit_scan(code, "python")
            for item in result.get("results", []):
                findings.append(
                    f"[bandit {item.get('test_id', '?')}] "
                    f"Severity: {item.get('issue_severity', '?')} | "
                    f"Line {item.get('line_number', '?')}: "
                    f"{item.get('issue_text', '?')}"
                )
        except Exception as e:
            logger.debug("bandit_scan_skipped: %s", e)

        try:
            from app.mcp.servers.code_analysis import semgrep_scan
            result = await semgrep_scan(code, "python")
            for item in result.get("results", []):
                findings.append(
                    f"[semgrep] {item.get('check_id', '?')}: "
                    f"{item.get('extra', {}).get('message', '?')}"
                )
        except Exception as e:
            logger.debug("semgrep_scan_skipped: %s", e)

        return findings
