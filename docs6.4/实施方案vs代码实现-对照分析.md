# AutoJudge 实施方案 vs 代码实现 — 对照分析

## 总览

实施方案定义了七大模块 + 十项工程落地加固 + 六阶段实施计划。代码在 Phase 1-4 的范围内基本落地，但**多个模块之间缺乏集成**——各模块独立编写完成，orchestrator 作为中心调度器并没有将它们串联起来。下表列出逐项对照，后续章节给出具体分析。

---

## 一、逐项对照总表

| # | 实施方案要求 | 代码状态 | 问题 |
|---|------------|---------|------|
| 1 | Coder + 3 Attacker + Judge 角色定义 | 已实现 | 无 |
| 2 | 三阶段轮次执行（Coder → 并行 Attacker → 交叉审阅） | 已实现 | 无 |
| 3 | 共享上下文 DebateContext（滑动窗口 + 早期摘要 + 角色交替） | 已实现 | 无 |
| 4 | 共识检测（仅基于 Structured Output stance） | 已实现 | 无 |
| 5 | Token 预算管理（per-Agent 上限 + cache 统计） | 已实现 | 无 |
| 6 | LangGraph 状态图（并行分支 + Checkpoint + 条件边） | graph.py 已定义 | **未被使用**，详见第二节 |
| 7 | WebSocket 双向通信 + 用户中途干预 | 部分实现 | **缺少 LangGraph interrupt**，详见第三节 |
| 8 | Coder 反驳工具（submit_response + run_code_snippet + check_documentation） | 工具 schema 已定义 | **run_code_snippet / check_documentation 无执行后端**，详见第四节 |
| 9 | MCP Server（bandit_scan + semgrep_scan） | 函数已实现 | **不是真正的 MCP Server**；SecurityAttacker 未调用，详见第五节 |
| 10 | 需求理解（RequirementParser） | 已实现 | 无 |
| 11 | 任务复杂度路由（ComplexityRouter） | 已实现 | **未集成到 orchestrator / generate.py** |
| 12 | 四级降级 + 熔断器 | 已实现 | **未集成到 generate.py** |
| 13 | 并发控制（ResourceManager） | 已实现 | **未集成到 orchestrator / generate.py** |
| 14 | 结果缓存（ResultCache） | 已实现 | **未集成到 orchestrator / generate.py** |
| 15 | 三层 Memory（攻击经验 + 用户偏好 + 修复模式） | 三个类均已实现 | **未集成到 orchestrator** |
| 16 | Memory 淘汰（EvictionManager） | 已实现 | **未被任何代码调用** |
| 17 | 代码执行验证（TestRunner） | 已实现 | **未集成到 orchestrator** |
| 18 | 智能模型路由（Sonnet/Haiku 按 Agent 分配） | model_router.py 已实现 | **call_agent 未调用 get_model_for_agent** |
| 19 | Prompt Caching（cache_control 标记静态前缀） | 已实现 | 仅 anthropic_api 模式生效 |
| 20 | API 安全（认证 + 限流 + Prompt Injection 防御） | 已实现 | **AuthMiddleware 未挂载到 FastAPI app** |
| 21 | Prometheus 指标 + 结构化日志 | 已实现 | **metrics 函数未在 orchestrator 中被调用** |
| 22 | LangSmith 集成 | setup 函数已实现 | **main.py 未调用 setup_langsmith** |
| 23 | Anthropic SDK + tool_use 结构化输出 | 已实现 | 无 |
| 24 | Claude CLI (-p) 后端 | 已实现 | 方案未提及，是额外实现 |
| 25 | 自建评测集 + 三组对比 | custom_runner.py 已实现 | 任务数不足（10 vs 方案要求 50-100） |
| 26 | 静态分析评分（bandit + semgrep） | static_analysis.py 已实现 | 无 |
| 27 | HumanEval 评测 | **缺失** | humaneval_runner.py 不存在 |
| 28 | 评测报告生成 | **缺失** | compare.py, report.py 不存在 |
| 29 | React 前端可视化 | 基本组件已创建 | 缺少 AgentAvatar, FindingCard, RoundTimeline 三个组件 |
| 30 | CI（GitHub Actions） | 已实现 | 无 |
| 31 | Docker + docker-compose | 已实现 | 无 |

---

## 二、核心问题：LangGraph 定义了但未使用

`graph.py` 完整定义了 LangGraph 状态图：6 个节点、并行边、条件边、MemorySaver checkpoint。但 `generate.py` 的两个端点（POST `/api/v1/generate` 和 WebSocket `/ws/generate`）都直接实例化 `DebateOrchestrator` 并调用 `orchestrator.run()`，**从未调用 `build_debate_graph()`**。

这意味着实施方案中 LangGraph 的三个核心能力在实际运行时全部不生效：

| 能力 | 方案描述 | 实际情况 |
|------|---------|---------|
| 并行分支 | 三路 Attacker 由 LangGraph 自动并行执行和汇合 | orchestrator.py 用 `asyncio.gather` 手动并行 |
| Checkpoint | 每一步自动持久化，断线后用 thread_id 恢复 | 无持久化，断线即丢失 |
| Interrupt | 交叉审阅后暂停等待用户干预，通过 aupdate_state 注入 | 无 interrupt，WebSocket 只有单向推送 |

**影响**：面试时如果说"我用了 LangGraph 的并行分支、Checkpoint 和 Interrupt"，但代码实际走的是 orchestrator.py 的 asyncio.gather 循环，会对不上。

**修复方向**：二选一——要么让 generate.py 使用 `build_debate_graph()` 编译后的 graph 来驱动对话，把 orchestrator.py 作为 legacy 移除；要么删除 graph.py，在简历中明确说编排用 asyncio 手动管理。

---

## 三、WebSocket 用户干预未实现

实施方案定义了三种用户干预消息：

```
{"type": "skip_attacker", "attacker": "performance"}
{"type": "add_context", "content": "..."}
{"type": "force_stop"}
```

`generate.py` 的 WebSocket 端点接收初始消息后直接进入 `orchestrator.run()`，**此后再也不从 WebSocket 读取客户端消息**。用户的 skip/add_context/force_stop 指令无法被接收和处理。

`orchestrator.py` 中 DebateContext 有 `skip_list` 和 `extra_context` 字段，但没有在运行中动态更新它们的入口。

---

## 四、Coder 工具定义了但无执行后端

Coder 有三个工具：

| 工具 | 定义 | 执行逻辑 |
|------|------|---------|
| `submit_response` | 已定义（CODER_SUBMIT_TOOL） | 由 `_parse_api_response` 提取结构化输出，可用 |
| `run_code_snippet` | 已定义 | **无执行后端**——Claude 发出 tool_use 请求后，没有代码去实际运行代码片段并返回结果 |
| `check_documentation` | 已定义 | **无执行后端**——没有代码去查询文档并返回结果 |

实施方案的核心卖点是"Coder 用工具验证后反驳"，但 `call_agent` 使用 `tool_choice={"type": "tool", "name": "submit_response"}`，强制 Claude 只调用 submit_response。即使去掉 tool_choice 约束让 Claude 调用 run_code_snippet，也没有处理 tool_use 请求的循环（Anthropic API 的 tool_use 需要多轮 turn-by-turn 循环来执行工具并返回结果）。

---

## 五、MCP Server 不是真正的 MCP

`code_analysis.py` 实现了 `bandit_scan` 和 `semgrep_scan` 两个 async 函数，但：

1. **没有用 `mcp.server.Server` 封装**——实施方案要求这些工具作为 MCP Server 独立进程运行，Agent 通过 MCP 协议调用。实际只是普通函数。
2. **SecurityAttacker 没有调用这些函数**——`security_attacker.py` 的 `get_system_prompt` 方法没有任何地方调用 `bandit_scan` 或 `semgrep_scan`。
3. 实施方案描述的 `self.mcp_client.call_tool("bandit_scan", ...)` 调用路径不存在。`app/mcp/client.py`（MCP 客户端）文件也不存在。

---

## 六、多模块未集成到主流程

以下模块全部独立实现但**未被 orchestrator.py 或 generate.py 调用**：

### 6.1 三层 Memory 系统

`orchestrator.py` 的 `__init__` 中没有实例化任何 Memory 类：

```python
# 实际代码
class DebateOrchestrator:
    def __init__(self):
        self.coder = CoderAgent()
        self.judge = JudgeAgent()
        self.consensus_detector = ConsensusDetector()
        # 没有 attack_kb, user_prefs, fix_patterns
```

实施方案要求：
- 新请求进来时检索历史攻击经验注入 Attacker prompt
- 加载用户偏好注入 Coder prompt
- Coder 修复时检索修复模式
- 对抗结束后存储本次成果

### 6.2 TestRunner

实施方案要求对抗收敛后、Judge 总结前执行代码验证：语法检查 → LLM 生成测试 → Docker 沙箱执行 → 验证不通过则反馈 Coder 再修一轮。

`orchestrator.py` 的 `run()` 方法中对抗循环结束后直接进入 Judge 总结，没有调用 TestRunner。

### 6.3 ComplexityRouter

实施方案要求在需求理解阶段判定任务复杂度：simple → 跳过对抗直接生成；medium → 1 个 Attacker 3 轮；hard → 完整三路对抗 7 轮。

`orchestrator.py` 和 `generate.py` 都没有调用 `route_complexity()`。所有请求无差别走完整对抗。

### 6.4 DegradationManager

`generate.py` 直接调用 `DebateOrchestrator().run()`，没有通过 `DegradationManager.execute_with_degradation()` 包装。LLM API 故障时没有降级兜底。

### 6.5 ResourceManager

`generate.py` 没有用 `debate_semaphore` 控制并发。多个用户同时请求时没有并发限制。

### 6.6 ResultCache

`generate.py` 没有在请求前查缓存、请求后存缓存。相同的需求会重复跑对抗。

### 6.7 AuthMiddleware

`main.py` 没有挂载 `AuthMiddleware`。API 没有认证和限流。

### 6.8 智能模型路由

`model_router.py` 定义了 agent → model 映射，但 `call_agent` 函数不会自动查询这个映射。所有 Agent 使用同一个模型。

### 6.9 Prometheus 指标

`metrics.py` 定义了完整的指标（debate_requests_total, agent_call_duration 等），但 orchestrator 中没有调用 `record_debate_complete` 或 `record_agent_call`。

### 6.10 LangSmith

`tracer.py` 中的 `setup_langsmith()` 没有在 `main.py` 中被调用。

---

## 七、评测体系不完整

| 方案要求 | 实际 |
|---------|------|
| 50-100 个自建评测任务 | tasks.json 只有 10 个 |
| HumanEval 164 题评测 | humaneval_runner.py 不存在 |
| 三组对比 + 聚合指标 | custom_runner.py 实现了三组对比框架，但缺少 compare.py 汇总 |
| 评测报告生成 | report.py 不存在 |
| 分类专项评测集（security_tasks.json 等） | 不存在 |

custom_runner.py 的 `run_evaluation` 函数可以运行，但它的 `compute_aggregate_metrics` 只统计 token/延迟/轮次，**没有实现缺陷检出率计算**——实施方案的核心指标 `check_known_issues(code, task["known_issues"])` 在代码中不存在。

---

## 八、前端组件缺失

| 组件 | 状态 |
|------|------|
| DebatePanel | 存在 |
| CodeEditor | 存在 |
| ConsensusIndicator | 存在 |
| RiskGauge | 存在 |
| MetricsBar | 存在 |
| InputForm | 存在 |
| AgentAvatar | **不存在** |
| FindingCard | **不存在** |
| RoundTimeline | **不存在** |

---

## 九、graph.py 中交叉审阅是串行的

`graph.py` 的 `cross_review_node` 中，三个 Attacker 的交叉审阅用 for 循环串行调用：

```python
for name, agent in agents.items():
    response = await agent.speak(ctx, cross_prompt, budget)
```

而 `orchestrator.py` 的交叉审阅正确使用了 `asyncio.gather` 并行执行。但由于 graph.py 未被实际使用，这个问题目前不影响运行。

---

## 十、代码质量可用的部分

以下部分实现质量与方案高度一致，可直接面试使用：

1. **DebateContext**：滑动窗口 + 早期摘要 + 角色交替保证，与方案代码几乎一致
2. **ConsensusDetector**：仅基于 stance 字段，有完整单测
3. **BudgetManager**：per-Agent 上限 + cache 统计 + 成本估算，有完整单测
4. **请求校验**：Prompt Injection 正则 + 语言/长度校验，有完整单测
5. **四级降级 + CircuitBreaker**：实现完整，state 属性设计正确
6. **Anthropic SDK 集成**：tool_use 结构化输出 + prompt caching + 重试（tenacity）
7. **Claude CLI 后端**：方案之外的额外能力，支持无 API Key 运行
8. **Docker 沙箱执行**：安全配置完整（--network=none, --read-only, --memory, --cpus）

---

## 十一、文件存在性差异

### 方案中列出但不存在的文件

| 文件路径 | 用途 |
|---------|------|
| app/llm/retry.py | 重试逻辑（已内联到 client.py 的 tenacity 装饰器） |
| app/mcp/client.py | MCP 客户端 |
| app/api/routes/metrics.py | 可观测性指标端点 |
| eval/humaneval_runner.py | HumanEval 评测 |
| eval/compare.py | 三组对比汇总 |
| eval/report.py | 评测报告生成 |
| eval/datasets/security_tasks.json | 安全专项任务 |
| eval/datasets/performance_tasks.json | 性能专项任务 |
| eval/datasets/correctness_tasks.json | 正确性专项任务 |
| tests/test_orchestrator.py | 编排引擎测试 |
| tests/test_agents/ | Agent 测试目录 |
| README.md | 项目说明 |
| frontend/src/components/AgentAvatar.tsx | Agent 头像组件 |
| frontend/src/components/FindingCard.tsx | 攻击发现卡片 |
| frontend/src/components/RoundTimeline.tsx | 轮次时间线 |

---

## 十二、按优先级排列的修复建议

### P0 — 不修会导致面试被质疑

1. **选择 graph.py 或 orchestrator.py 之一作为主编排，删除另一个**。如果保留 graph.py，则 generate.py 需要调用 `build_debate_graph()` 并使用 compiled graph 的 `ainvoke`/`astream`。如果保留 orchestrator.py，则简历中不能说"LangGraph 并行分支 + Checkpoint + Interrupt"，需要改为"asyncio.gather 并行 + 手动状态管理"。
2. **在 orchestrator.py 中集成 Memory、TestRunner、ComplexityRouter**。这些是方案的核心卖点，面试必问。至少 Memory 的读写链路和 TestRunner 的验证链路要通。
3. **Coder 的 run_code_snippet 工具要有执行后端**。需要做一个 tool_use loop：检测到 tool_use 不是 submit_response 时，执行工具并把结果返回给模型继续。

### P1 — 不修会降低项目完整度

4. **在 generate.py 中集成 DegradationManager 包裹 orchestrator 调用**。
5. **在 main.py 中挂载 AuthMiddleware**。
6. **在 call_agent 中集成 model_router**，根据 agent name 自动选择模型。
7. **MCP Server 改为真正的 MCP 协议**，或者把 bandit_scan/semgrep_scan 直接集成到 SecurityAttacker.speak() 调用链中。
8. **将 tasks.json 扩充到 50 个任务**，补充 check_known_issues 缺陷检出率计算逻辑。

### P2 — 锦上添花

9. 在 main.py 中调用 `setup_langsmith()`。
10. 在 orchestrator 中调用 metrics 函数。
11. 集成 ResourceManager 到 generate.py。
12. 集成 ResultCache 到 generate.py。
13. 补齐前端缺失组件（AgentAvatar, FindingCard, RoundTimeline）。
14. 编写 test_orchestrator.py。
