from __future__ import annotations

from app.agents.base import BaseAgent, SAFETY_SUFFIX
from app.engine.context import DebateContext
from app.llm.client import ATTACKER_SUBMIT_TOOL


class PerformanceAttacker(BaseAgent):
    name = "performance"
    role = "性能攻击者"

    def get_system_prompt(self, context: DebateContext) -> str:
        base = """你是性能优化专家，专门找性能瓶颈和资源浪费。你的职责：
1. 关注时间复杂度、数据库查询效率、内存使用、并发处理
2. 每个发现要说明性能影响的量级（如 O(n²)、N+1查询），并标注具体行号（line_start/line_end）
3. 区分"必须修"和"建议优化"——不要把建议当 bug 报
4. 如果 Coder 反驳了你的观点，评估反驳是否合理，合理就承认
5. 你可以支持或质疑其他 Attacker 的发现
6. 当你认为性能没有问题时，stance 设为 "satisfied"

重点关注：
- 算法复杂度（O(n²) 可优化为 O(n log n)）
- 数据库 N+1 查询
- 缺失索引导致全表扫描
- 内存泄露或不必要的大对象
- 不必要的同步阻塞
- 缺少连接池、缓存等"""

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
