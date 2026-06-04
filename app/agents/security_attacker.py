from __future__ import annotations

from app.agents.base import BaseAgent, SAFETY_SUFFIX
from app.engine.context import DebateContext
from app.llm.client import ATTACKER_SUBMIT_TOOL


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
