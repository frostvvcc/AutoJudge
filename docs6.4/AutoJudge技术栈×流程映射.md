# AutoJudge 技术栈 × 流程映射

> 日期：2026-06-05
> 说明：本文档对照完整流程图，标注每一步用了什么技术、怎么用的、代码在哪。
> 看法：先看流程图里的 `【技术】` 标注，再看下面的详细解释。

---

## 一、带技术标注的完整流程图

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          AutoJudge 完整流程（每一步标注所用技术）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


  用户提交需求（前端 TaskCenter 页面）
         │
         │  【React 19 + TypeScript 5.7 + Tailwind CSS】
         │  【react-router-dom 7 路由: / → TaskCenter】
         │
         ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  前端建立 WebSocket 连接                                             │
  │                                                                      │
  │  【FastAPI WebSocket】 /api/v1/ws/generate                          │
  │  【PyJWT】 前端 send({token}) → 后端 decode_token() 验证身份         │
  │  【asyncio.Queue】 创建 interrupt_queue 等待后续 HITL 交互           │
  └──────────────────────────────────────────────────────────────────────┘
         │
         │  【DegradationManager】先查 Redis 缓存 → 未命中 → 进入 L0 完整流程
         │  【CircuitBreaker】检查熔断状态 → closed → 放行
         │
         ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  预处理                                                               │
  │                                                                      │
  │  【Anthropic tool_use】parse_requirement() 解析需求                   │
  │  【ComplexityRouter】根据需求复杂度自动调参（轮次/攻击维度）           │
  │  【ChromaDB (HNSW+余弦)】检索历史攻击经验 top-5，注入 Agent 上下文    │
  │  【Redis】加载用户偏好（常用语言/编码风格）                           │
  └──────────────────────────────────────────────────────────────────────┘
         │
         │  【LangGraph StateGraph】构建初始 DebateState，编译图
         │  【AIOMySQLSaver】连接 MySQL，启用 checkpoint（每个节点自动存档）
         │  【contextvars.ContextVar】注册 _progress_callback（并发安全）
         │
         ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  图开始执行                                                           │
  │  graph.compile(checkpointer=checkpointer)                            │
  │  compiled.ainvoke(initial_state, graph_config)                        │
  │                                                                      │
  │  【LangGraph interrupt + Command(resume) 循环】                      │
  │  碰到 interrupt → 抛 GraphInterrupt → 主循环捕获                      │
  │  → 调 interrupt_handler → WebSocket 推前端 → 等用户回复               │
  │  → Command(resume=user_response) 恢复图执行                           │
  │  最多 20 轮中断-恢复循环                                              │
  └──────────────────────────────────────────────────────────────────────┘
         │
         │
═══════════════════════════════════════════════════════════════════════════
  PHASE 1: 方案设计（plan_node）
═══════════════════════════════════════════════════════════════════════════
         │
         ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Coder 生成 2 个方案                                                  │
  │                                                                      │
  │  【Anthropic tool_use (httpx)】                                      │
  │   调 _call_anthropic_proxy()，POST 到代理 /v1/messages               │
  │   model = Haiku（轻量模型，控制成本）                                 │
  │                                                                      │
  │  【Prompt Caching (cache_control: ephemeral)】                       │
  │   system prompt + tools 加 cache 标记                                 │
  │   同 Agent 多轮调用时这些不变内容走缓存，省 input token               │
  │                                                                      │
  │  【model_router.py】                                                 │
  │   get_model_for_agent("planner") → Haiku 模型                        │
  │   轻量任务用小模型，重活用 Opus                                       │
  └──────────────────┬───────────────────────────────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  方案推送给用户                                                       │
  │                                                                      │
  │  【WebSocket send_json】                                             │
  │   _notify({type: "plan_proposal", content: plans_content})           │
  │   → on_progress 回调 → websocket.send_json(event)                   │
  │   → 前端 DebateContext handleEvent case "plan_proposal" 接收         │
  │   → PlanDisplayCard 组件渲染双卡片                                    │
  │                                                                      │
  │  【LangGraph interrupt()】                                           │
  │   interrupt({type: "plan_review", content, round, max_rounds})       │
  │   → 图暂停 → 抛 GraphInterrupt                                      │
  │   → generate.py handle_interrupt() 通过 WebSocket 推给前端           │
  │   → 前端展示 [选A] [选B] [交给Coder选] [输入框]                      │
  │   → 用户操作 → WebSocket send({type: "interrupt_response", data})    │
  │   → 后端 interrupt_queue.get() 收到                                  │
  │   → Command(resume=user_response) 恢复图                             │
  │                                                                      │
  │  对话式交互（输入框打字）：                                            │
  │   action="chat" → Coder 重新生成方案 → 再次 interrupt → 循环         │
  │   【防死循环】R3 温和提示 / R5 强引导 / R7 硬上限自动推进             │
  │   【120秒超时】asyncio.wait_for(interrupt_queue.get(), timeout=120)   │
  └──────────────────┬───────────────────────────────────────────────────┘
                     │
                方案确定
                     │
                     │  【LangGraph add_edge("plan", "coder")】
                     │
═══════════════════════════════════════════════════════════════════════════
  PHASE 2: Coder 写代码 + 自测（coder_node）
═══════════════════════════════════════════════════════════════════════════
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Coder 按方案写代码                                                   │
  │                                                                      │
  │  【Anthropic tool_use + tool_choice: "any"】                         │
  │   tool_choice 设为 "any" 而不是强制 submit_response                  │
  │   因为 Coder 需要先调 run_code_snippet 自测，再提交                   │
  │                                                                      │
  │  【多轮 tool_use 循环 (max_tool_turns=5)】                           │
  │   Turn 1: LLM 返回 → tool_use(run_code_snippet, {code, expected})   │
  │           → 执行 → 返回结果                                          │
  │   Turn 2: LLM 看到执行结果 → 修复 → tool_use(run_code_snippet)      │
  │   Turn 3: 执行通过 → tool_use(submit_response, {code, message})     │
  │   对应流程设计里的 "test→fix→test→fix→submit"                        │
  │                                                                      │
  │  【Docker 沙箱】 ← run_code_snippet 的底层                           │
  │   docker run --rm                                                    │
  │     --network=none      ← 禁止网络（防恶意代码外连）                  │
  │     --read-only         ← 只读文件系统（防写入攻击）                  │
  │     --memory=256m       ← 内存限制（防 OOM）                         │
  │     --cpus=0.5          ← CPU 限制（防算力滥用）                     │
  │     --tmpfs /tmp:64m    ← 临时写入空间                               │
  │   asyncio.wait_for(timeout=15)  ← 15 秒执行超时                     │
  │                                                                      │
  │  代码位置：                                                           │
  │  · tool_use 循环: client.py:294-338 (_call_anthropic_api)            │
  │  · 代理版循环:    client.py:398-448 (_call_anthropic_proxy)          │
  │  · Docker 执行:   client.py:215-251 (_run_code_snippet)              │
  └──────────────────┬───────────────────────────────────────────────────┘
                     │
                     │  Coder 提交代码
                     │
                     │  【LangGraph 并行 fan-out】
                     │  graph.add_edge("coder", "security")
                     │  graph.add_edge("coder", "performance")
                     │  graph.add_edge("coder", "correctness")
                     │  三条 edge 同时走 → 三个节点并行执行
                     │
═══════════════════════════════════════════════════════════════════════════
  PHASE 3: 辩论循环
═══════════════════════════════════════════════════════════════════════════
                     │
                     ▼
  ┏━━━━━━━━━━━━━━━━ 单轮辩论开始 ━━━━━━━━━━━━━━━━━━┓
  ┃                                                  ┃
  ┃  ┌───────────────────────────────────────────┐   ┃
  ┃  │  Stage 1: Coder 逐条回应（第 2 轮+）      │   ┃
  ┃  │                                           │   ┃
  ┃  │  【Anthropic tool_use】                   │   ┃
  ┃  │   tool: submit_response                   │   ┃
  ┃  │   每条攻击选 action:                      │   ┃
  ┃  │   · "accept_and_fix" → 修改代码           │   ┃
  ┃  │   · "rebut_with_evidence" → 调            │   ┃
  ┃  │     run_code_snippet 拿执行结果当证据      │   ┃
  ┃  │                                           │   ┃
  ┃  │  【Docker 沙箱】反驳时执行代码拿证据       │   ┃
  ┃  └──────────────────┬────────────────────────┘   ┃
  ┃                     │                            ┃
  ┃                     ▼                            ┃
  ┃  ┌───────────────────────────────────────────┐   ┃
  ┃  │  Stage 2: 3 个 Attacker 并行攻击          │   ┃
  ┃  │                                           │   ┃
  ┃  │  【LangGraph 并行节点】                   │   ┃
  ┃  │   图引擎自动并行执行三个 Attacker 节点     │   ┃
  ┃  │   总耗时 = max(三个的耗时) ≈ 20-30 秒     │   ┃
  ┃  │   而不是串行 60-90 秒                      │   ┃
  ┃  │                                           │   ┃
  ┃  │  【Anthropic tool_use + tool_choice 强制】│   ┃
  ┃  │   tool: submit_review                     │   ┃
  ┃  │   tool_choice: {type:"tool",              │   ┃
  ┃  │                  name:"submit_review"}    │   ┃
  ┃  │   → LLM 必须调用此工具，输出结构化数据    │   ┃
  ┃  │                                           │   ┃
  ┃  │   输出字段（强制，不是文本解析）：          │   ┃
  ┃  │   · stance: "attacking" | "satisfied"     │   ┃
  ┃  │   · findings: [{severity, description,    │   ┃
  ┃  │                  test_input}]              │   ┃
  ┃  │                                           │   ┃
  ┃  │  【Prompt Caching】                       │   ┃
  ┃  │   三个 Attacker 的 system prompt 和 tool  │   ┃
  ┃  │   schema 加了 cache_control: ephemeral    │   ┃
  ┃  │   多轮辩论时这些不变内容走缓存             │   ┃
  ┃  │                                           │   ┃
  ┃  │  【model_router.py】                      │   ┃
  ┃  │   security/performance/correctness        │   ┃
  ┃  │   → 用 Opus 模型（重活用大模型）          │   ┃
  ┃  │                                           │   ┃
  ┃  │  ┌──────────┐┌──────────┐┌──────────┐    │   ┃
  ┃  │  │ Security ││  Perf    ││Correct   │    │   ┃
  ┃  │  │ Attacker ││ Attacker ││ness      │    │   ┃
  ┃  │  │          ││          ││Attacker  │    │   ┃
  ┃  │  └──────────┘└──────────┘└──────────┘    │   ┃
  ┃  └──────────────────┬────────────────────────┘   ┃
  ┃                     │                            ┃
  ┃                     ▼                            ┃
  ┃  ┌───────────────────────────────────────────┐   ┃
  ┃  │  Stage 3: 交叉审阅（Cross-Review）        │   ┃
  ┃  │                                           │   ┃
  ┃  │  【asyncio.gather】                       │   ┃
  ┃  │   三个 Attacker 同时看对方的发现           │   ┃
  ┃  │   asyncio.gather(*[safe_cross(n,a)        │   ┃
  ┃  │                    for n,a in active])     │   ┃
  ┃  │   并行执行，补充/支持/质疑对方观点         │   ┃
  ┃  │                                           │   ┃
  ┃  │  【model_router.py】                      │   ┃
  ┃  │   cross_review → 用 Haiku（轻量任务）     │   ┃
  ┃  └──────────────────┬────────────────────────┘   ┃
  ┃                     │                            ┃
  ┃                     ▼                            ┃
  ┃  ┌───────────────────────────────────────────┐   ┃
  ┃  │  Stage 4: 共识检测                        │   ┃
  ┃  │                                           │   ┃
  ┃  │  【ConsensusDetector】                    │   ┃
  ┃  │   只看结构化输出的 stance 字段             │   ┃
  ┃  │   不做自然语言解析（因为 tool_use 已经     │   ┃
  ┃  │   强制输出了枚举值，是确定性的）            │   ┃
  ┃  │                                           │   ┃
  ┃  │   if stance == "satisfied": ✅             │   ┃
  ┃  │   if stance == "attacking": ❌             │   ┃
  ┃  │   all satisfied? → converged = True       │   ┃
  ┃  │                                           │   ┃
  ┃  │  【LangGraph conditional_edges】          │   ┃
  ┃  │   check_consensus_edge() 返回三路之一：    │   ┃
  ┃  └──────────────────┬────────────────────────┘   ┃
  ┃                     │                            ┃
  ┗━━━━━━━━━━━━━━━━ 单轮辩论结束 ━━━━━━━━━━━━━━━━━━┛
                     │
          ┌──────────┼──────────────┐
          │          │              │
     "continue"  "converged"  "budget_exceeded"
          │          │              │
          ▼          │              │
   回 coder_node     │              │
   （下一轮辩论）     │              │
                     │              │
                     │              │
                     │              │
═══════════════════════════════════════════════════════════════════════════
  PHASE 4: Arbitrator 仲裁（arbitration_node）—— 仅辩论未收敛时
═══════════════════════════════════════════════════════════════════════════
                     │              │
                     │              ▼
                     │   ┌──────────────────────────────────────────────┐
                     │   │  Step 1: 提取未解决争议                       │
                     │   │                                              │
                     │   │  _extract_unresolved_disputes()              │
                     │   │  只看最后一轮 stance="attacking" 的 findings  │
                     │   │  过滤掉早期已解决的争议                       │
                     │   └──────────────────┬───────────────────────────┘
                     │                      │
                     │                      ▼
                     │   ┌──────────────────────────────────────────────┐
                     │   │  Step 2: Arbitrator 独立裁决                  │
                     │   │                                              │
                     │   │  【Anthropic tool_use + tool_choice 强制】   │
                     │   │   tool: submit_arbitration                   │
                     │   │   tool_choice: {type:"tool",                 │
                     │   │                 name:"submit_arbitration"}   │
                     │   │                                              │
                     │   │   输出（全部结构化，不是文本）：               │
                     │   │   · rulings: [{                              │
                     │   │       dispute_id,                            │
                     │   │       verdict: dismissed|acknowledged|        │
                     │   │               must_fix|deferred|needs_human, │
                     │   │       re_assessed_severity,                  │
                     │   │       reasoning                              │
                     │   │     }]                                       │
                     │   │   · overall_verdict: deliverable |           │
                     │   │     fix_then_deliver | not_deliverable       │
                     │   │   · confidence: 0-1                          │
                     │   │                                              │
                     │   │  四维评判矩阵（写在 system prompt 里）：      │
                     │   │   Severity Verification  30%                 │
                     │   │   Evidence Quality       30%                 │
                     │   │   Fix Feasibility        20%                 │
                     │   │   Coder Rebuttal Validity 20%                │
                     │   │                                              │
                     │   │  代码: app/agents/arbitrator.py              │
                     │   └──────────────────┬───────────────────────────┘
                     │                      │
                     │                      ▼
                     │   ┌──────────────────────────────────────────────┐
                     │   │  Step 3: 展示裁决 + 用户确认                  │
                     │   │                                              │
                     │   │  【WebSocket send_json】                     │
                     │   │   _notify({type: "arbitration_complete",     │
                     │   │           disputes_count, overall_verdict})  │
                     │   │   → 前端 ArbitrationPanel 组件渲染            │
                     │   │                                              │
                     │   │  【LangGraph interrupt()】                   │
                     │   │   interrupt({type: "arbitration_review",     │
                     │   │             rulings, overall_verdict})       │
                     │   │   → 图暂停 → WebSocket 推前端                │
                     │   │   → [接受全部] [我有异议]                     │
                     │   │   → 120 秒超时自动接受                       │
                     │   │                                              │
                     │   │  用户异议处理：                               │
                     │   │   override.action = "upgrade"                │
                     │   │     → ruling.verdict = "must_fix"            │
                     │   │   override.action = "downgrade"              │
                     │   │     → 先检查安全红线                          │
                     │   │                                              │
                     │   │  【安全红线规则】                             │
                     │   │   _security_redline_allows()                 │
                     │   │   SQL注入/RCE/XSS 等 critical 级别           │
                     │   │   不允许用户降级 → 拒绝并记录                  │
                     │   └──────────────────┬───────────────────────────┘
                     │                      │
                     │           ┌──────────┴──────────┐
                     │           │                     │
                     │     must_fix=0             must_fix>0
                     │     (可交付)               (需修复)
                     │           │                     │
                     │    【_arbitration_edge          │
                     │     → "deliver"】               │
                     │           │              【_arbitration_edge
                     │           │               → "fix"】
                     │           │                     │
                     │           │                     │
═══════════════════════════════════════════════════════════════════════════
  PHASE 5: 修复阶段（final_fix_node）
═══════════════════════════════════════════════════════════════════════════
                     │           │                     │
                     │           │                     ▼
                     │           │  ┌──────────────────────────────────┐
                     │           │  │  Coder 修复 + 自测               │
                     │           │  │                                  │
                     │           │  │  【Anthropic tool_use 循环】     │
                     │           │  │   和 PHASE 2 一样的 tool_use     │
                     │           │  │   loop，run_code_snippet 自测    │
                     │           │  │                                  │
                     │           │  │  【Docker 沙箱】自测执行          │
                     │           │  └──────────────┬───────────────────┘
                     │           │                 │
                     │           │            自测通过？
                     │           │            │        │
                     │           │           Yes      No (失败)
                     │           │            │        │
                     │           │            │        ▼
                     │           │            │  ┌─────────────────────┐
                     │           │            │  │ 策略多样化           │
                     │           │            │  │                     │
                     │           │            │  │ 【STRATEGY_ANGLES】 │
                     │           │            │  │  4 个切换角度：      │
                     │           │            │  │  A: 换数据结构/算法  │
                     │           │            │  │  B: 换实现层级       │
                     │           │            │  │  C: 换依赖/库        │
                     │           │            │  │  D: 简化需求范围     │
                     │           │            │  │                     │
                     │           │            │  │ 第 1 次失败立即触发  │
                     │           │            │  │ 不等第 3 次          │
                     │           │            │  └──────────┬──────────┘
                     │           │            │             │
                     │           │            │             ▼
                     │           │            │  ┌─────────────────────┐
                     │           │            │  │ 用户审核替代方案     │
                     │           │            │  │                     │
                     │           │            │  │ 【LangGraph         │
                     │           │            │  │  interrupt()】      │
                     │           │            │  │  {type:             │
                     │           │            │  │   "strategy_review",│
                     │           │            │  │   attempt,          │
                     │           │            │  │   strategy}         │
                     │           │            │  │                     │
                     │           │            │  │ → WebSocket 推前端  │
                     │           │            │  │ → [同意] [不同意]   │
                     │           │            │  │ → 120秒超时自动同意 │
                     │           │            │  └──────────┬──────────┘
                     │           │            │             │
                     │           │            │    Coder 按新角度修复
                     │           │            │    最多 3 次尝试
                     │           │            │             │
                     │           │            ▼             ▼
                     │           │  ┌──────────────────────────────────┐
                     │           │  │  Arbitrator 定向复核              │
                     │           │  │                                  │
                     │           │  │  【Anthropic tool_use】          │
                     │           │  │   tool: submit_fix_review        │
                     │           │  │   arbitrator.review_fixes()      │
                     │           │  │   逐条检查 must_fix 是否修好     │
                     │           │  │   不找新问题，不发起新攻击       │
                     │           │  │                                  │
                     │           │  │  未修好 → Coder 补修（再次自测） │
                     │           │  └──────────────┬───────────────────┘
                     │           │                 │
                     │           │            修复完成
                     │           │                 │
                     │           │                 │
═══════════════════════════════════════════════════════════════════════════
  PHASE 6: Judge 生成报告（judge_node）
═══════════════════════════════════════════════════════════════════════════
                     │           │                 │
                     ▼           ▼                 ▼
                   所有路径汇入 judge_node
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Judge 生成"代码质量报告"                                             │
  │                                                                      │
  │  【Anthropic tool_use + tool_choice 强制】                           │
  │   tool: submit_judgment                                              │
  │   tool_choice: {type:"tool", name:"submit_judgment"}                 │
  │                                                                      │
  │   强制输出字段（结构化，不是文本解析）：                                │
  │   · star_rating: 1-5 星                                              │
  │   · star_comment: 一句话评价                                          │
  │   · resolved_issues: ["已修复问题1", ...]                             │
  │   · unresolved_issues: [{                                            │
  │       issue, current_state, impact, suggestion                       │
  │     }]                                                               │
  │   · score_security: 0-100                                            │
  │   · score_performance: 0-100                                         │
  │   · score_correctness: 0-100                                         │
  │   · usage_advice: "使用建议"                                          │
  │                                                                      │
  │  【Pydantic QualityReport 模型】                                     │
  │   从 tool_use 输出直接映射到 Pydantic 模型                            │
  │   → FastAPI 自动序列化为 JSON 返回给前端                              │
  │                                                                      │
  │  代码: app/agents/judge.py (JUDGE_SUBMIT_TOOL)                       │
  └──────────────────┬───────────────────────────────────────────────────┘
                     │
                     │  【LangGraph add_edge("judge", END)】
                     │
═══════════════════════════════════════════════════════════════════════════
  PHASE 7: 返回最终结果
═══════════════════════════════════════════════════════════════════════════
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  构建 DebateResult                                                    │
  │                                                                      │
  │  【Pydantic 数据模型】                                               │
  │   DebateResult / DebateSummary / RiskAssessment /                    │
  │   DebateMetrics / QualityReport                                      │
  │   各字段从 final_state 和 judge_report 中提取                         │
  │                                                                      │
  │  代码: graph.py:1099-1151 (result = DebateResult(...))               │
  └──────────────────┬───────────────────────────────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  后处理 + 持久化                                                      │
  │                                                                      │
  │  【MySQL + SQLAlchemy (async)】                                      │
  │   _save_session() 写入两张表：                                        │
  │   · debate_sessions: 任务/配置/结果/质量报告/metrics                  │
  │   · debate_messages: 每条 Agent 发言（agent, content, round,         │
  │                      code, structured_json）                         │
  │                                                                      │
  │  【ChromaDB】写回攻击经验                                             │
  │   被接受的 findings → attack_kb.store_findings()                      │
  │   → 下次新任务能检索到这些经验                                        │
  │                                                                      │
  │  【Redis】写回用户偏好 + 缓存结果                                     │
  │   user_prefs.update_from_request()                                   │
  │   cache.store(requirement, language, result)                          │
  │                                                                      │
  │  【Prometheus + structlog】                                          │
  │   record_debate_complete() 记录 metrics                              │
  └──────────────────┬───────────────────────────────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  推送最终结果给前端                                                    │
  │                                                                      │
  │  【WebSocket send_json】                                             │
  │   {type: "result", data: result.model_dump(), session_sid}           │
  │   → 前端 handleEvent case "result" 接收                              │
  │   → QualityReportPanel 组件渲染星级/分数/建议                         │
  │                                                                      │
  │  【React 19 + TypeScript 5.7 + Tailwind CSS】                       │
  │   前端组件渲染：                                                      │
  │   · QualityReportPanel — 星级+进度条+建议                             │
  │   · AttackResponsePanel — 攻防对照卡片                                │
  │   · PipelineProgress — 全流程进度条                                   │
  │   · CodeEvolution — 代码版本切换+Diff                                 │
  │   · RealtimeDashboard — Attacker 状态+风险趋势                       │
  └──────────────────────────────────────────────────────────────────────┘
```

---

## 二、技术栈一览表（按"在流程中出现的先后顺序"排列）

| # | 技术 | 在流程哪里 | 干什么用的 | 关键代码 |
|---|------|-----------|-----------|---------|
| 1 | **React 19 + TS 5.7 + Vite 6 + Tailwind** | 前端全局 | 页面渲染、组件、样式 | `frontend/src/` |
| 2 | **react-router-dom 7** | 前端路由 | `/` 任务中心 → `/workspace/:sid` 工作台 → `/history` | `main.tsx` |
| 3 | **FastAPI WebSocket** | 前后端通信 | 实时推送事件 + HITL 双向交互 | `generate.py:190-348` |
| 4 | **PyJWT + bcrypt** | 连接认证 | JWT 验证身份，bcrypt 存密码 | `auth/jwt.py`, `auth/deps.py` |
| 5 | **DegradationManager + CircuitBreaker** | 流程最外层 | L0→L1→L2→L3 四级降级 + 熔断恢复 | `degradation.py` |
| 6 | **Redis** | 预处理+后处理 | 用户偏好存取 + 结果缓存 | `memory/user_preferences.py`, `result_cache.py` |
| 7 | **ChromaDB (HNSW+cosine)** | 预处理+后处理 | 历史攻击经验的向量存取 | `memory/attack_knowledge.py` |
| 8 | **LangGraph StateGraph** | PHASE 1-7 全流程 | 编排 9 节点有向图，管理状态流转 | `graph.py:821-868` |
| 9 | **AIOMySQLSaver (Checkpoint)** | 每个节点完成后 | 图状态自动持久化到 MySQL，断连可恢复 | `graph.py:980-983` |
| 10 | **contextvars.ContextVar** | 回调注册 | 多任务并发时回调不串台 | `graph.py:69-71` |
| 11 | **LangGraph interrupt + Command(resume)** | PHASE 1/4/5 的用户交互 | 暂停图→WebSocket推前端→等回复→恢复图 | `graph.py:214,610,707` |
| 12 | **Anthropic tool_use + tool_choice** | 每次 LLM 调用 | 强制结构化输出，不做文本解析 | `client.py` 全部 |
| 13 | **httpx 直连代理 (anthropic_proxy)** | 每次 LLM 调用底层 | 绕过代理 WAF，手动构造 HTTP 请求 | `client.py:353-476` |
| 14 | **Prompt Caching (cache_control)** | 每次 LLM 调用 | system prompt + tools 缓存，省重复 token | `client.py:278-284` |
| 15 | **model_router.py** | 每次 LLM 调用 | Opus 做重活，Haiku 做轻活 | `llm/model_router.py` |
| 16 | **Docker 沙箱** | PHASE 2/3/5 的代码执行 | 5 层隔离执行代码（断网+只读+限内存+限CPU+超时） | `client.py:215-251` |
| 17 | **asyncio.gather** | PHASE 3 交叉审阅 | 3 个 Attacker 并行看对方发现 | `graph.py:417-419` |
| 18 | **ConsensusDetector** | PHASE 3 共识检测 | 只看 stance 枚举值，不解析自然语言 | `consensus.py` |
| 19 | **tenacity 重试** | LLM 调用容错 | 指数退避重试 3 次（超时/限流/503） | `client.py:502-506` |
| 20 | **Pydantic** | 配置+API模型 | .env 加载、请求验证、响应序列化 | `config.py`, `response.py` |
| 21 | **MySQL + SQLAlchemy (async)** | 数据持久化 | sessions + messages 两张表存辩论记录 | `db/models.py` |
| 22 | **Prometheus + structlog** | 可观测性 | Agent 调用和辩论完成的 metrics 记录 | `tracing/metrics.py` |

---

## 三、3 个 HITL 交互点的技术链路图

这 3 个交互点用的是同一套技术链路，只是 payload 不同：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│    图节点内部                     后端 WebSocket handler        前端      │
│                                                                          │
│    interrupt(payload)             handle_interrupt(payload)     React     │
│         │                              │                        │        │
│         ▼                              │                        │        │
│    抛 GraphInterrupt ──────────────────▶│                        │        │
│                                        │                        │        │
│                                        ▼                        │        │
│                                   websocket.send_json ─────────▶│        │
│                                   ({type:"interrupt",           │        │
│                                     payload})                   │        │
│                                                                 ▼        │
│                                                            用户看到       │
│                                                            交互界面       │
│                                                                 │        │
│                                                            用户操作       │
│                                                                 │        │
│                                   interrupt_queue.get() ◀───────│        │
│                                   ({type:"interrupt_response",  │        │
│                                     data})                      │        │
│                                        │                                 │
│    Command(resume=data) ◀──────────────│                                 │
│         │                                                                │
│         ▼                                                                │
│    图从 interrupt 处                                                     │
│    恢复执行                                                              │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

交互点 ①  PHASE 1  payload = {type:"plan_review", content:方案, round}
交互点 ②  PHASE 4  payload = {type:"arbitration_review", rulings, overall_verdict}
交互点 ③  PHASE 5  payload = {type:"strategy_review", attempt, strategy}

三个点都有 120 秒超时：asyncio.wait_for(interrupt_queue.get(), timeout=120)
超时后返回空 dict {} → 图自动推进（自动选/自动接受/自动同意）
REST API 模式：enable_interrupt=False → 所有 interrupt() 直接跳过
```

---

## 四、Coder 的 tool_use 循环详解

这是你项目里最核心的 LLM 调用模式，值得单独画：

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Coder 的 tool_use 循环（max_tool_turns = 5）                            │
│                                                                          │
│  Turn 1:                                                                 │
│  ┌─────────────┐     ┌──────────────────────┐     ┌───────────────────┐ │
│  │  发送请求    │     │  LLM 返回            │     │  后端执行         │ │
│  │             │────▶│  tool_use:            │────▶│                   │ │
│  │  messages + │     │  run_code_snippet     │     │  Docker 沙箱跑代码│ │
│  │  tools +    │     │  {code:"...",         │     │  返回执行结果     │ │
│  │  tool_choice│     │   expected:"..."}     │     │                   │ │
│  │  = "any"    │     │                      │     │                   │ │
│  └─────────────┘     └──────────────────────┘     └────────┬──────────┘ │
│                                                            │            │
│  Turn 2:                                                   │            │
│  ┌─────────────┐     ┌──────────────────────┐              │            │
│  │  把执行结果  │     │  LLM 看到结果        │              │            │
│  │  作为        │────▶│  发现有 bug → 修复   │              │            │
│  │  tool_result │     │  tool_use:            │──────────────┘            │
│  │  喂回 LLM   │     │  run_code_snippet     │  再次 Docker 执行         │
│  └─────────────┘     │  (修复后的代码)       │                          │
│                      └──────────────────────┘                          │
│                                                                          │
│  Turn 3:                                                                 │
│  ┌─────────────┐     ┌──────────────────────┐                          │
│  │  执行通过了  │     │  LLM 确认测试通过    │                          │
│  │  的结果     │────▶│  tool_use:            │  ← 这次调的是终止工具     │
│  │  喂回 LLM   │     │  submit_response     │                          │
│  └─────────────┘     │  {message, responses, │                          │
│                      │   updated_code}       │                          │
│                      └──────────────────────┘                          │
│                                                                          │
│  关键设计：                                                              │
│  · tool_choice="any" 让 LLM 自主决定先测试还是直接提交                    │
│  · 碰到 submit_response → 跳出循环（has_submit=True → break）           │
│  · 碰到其他工具 → 执行 → 结果喂回 → 继续循环                              │
│  · 最多 5 轮（test→fix→test→fix→submit）                                │
│  · Attacker/Judge/Arbitrator 没有这个循环（tool_choice 强制调指定工具）   │
│                                                                          │
│  代码：client.py:294-338 (anthropic_api)                                │
│        client.py:398-448 (anthropic_proxy)                              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 五、降级机制图

```
┌──────────────────────────────────────────────────────────────────────────┐
│  DegradationManager — 四级降级 + CircuitBreaker                          │
│                                                                          │
│  ┌─ 请求进入 ─┐                                                         │
│  │            │                                                          │
│  │  先查 Redis 缓存 ─── 命中 → 直接返回缓存结果                          │
│  │            │                                                          │
│  │  未命中    │                                                          │
│  │            ▼                                                          │
│  │  ┌─────────────────────────────────────────────────────┐             │
│  │  │  L0: 完整 LangGraph 辩论                             │             │
│  │  │  run_debate_with_graph()                             │             │
│  │  │  · Plan → Coder → 3 Attacker → Cross → Consensus   │             │
│  │  │  · 可能触发 Arbitrator → Fix → Judge                │             │
│  │  │  · 超时 = rounds × per_round × 1.5                  │             │
│  │  └────────────────────────┬────────────────────────────┘             │
│  │                      成功？│                                          │
│  │                   ┌───────┴───────┐                                  │
│  │                  Yes              No (超时/异常)                      │
│  │                   │               │                                  │
│  │              返回结果      CircuitBreaker.record_failure()            │
│  │                           连续 3 次 → 熔断打开                       │
│  │                                   │                                  │
│  │                                   ▼                                  │
│  │  ┌─────────────────────────────────────────────────────┐             │
│  │  │  L1: 精简辩论                                        │             │
│  │  │  DebateOrchestrator（不走 LangGraph）                │             │
│  │  │  · 只保留 1 个 Attacker (correctness)                │             │
│  │  │  · 只跑 2 轮                                        │             │
│  │  │  · 跳过交叉审阅                                      │             │
│  │  │  · 超时 60 秒                                        │             │
│  │  └────────────────────────┬────────────────────────────┘             │
│  │                      成功？│                                          │
│  │                   ┌───────┴───────┐                                  │
│  │                  Yes              No                                 │
│  │                   │               │                                  │
│  │              返回结果              ▼                                  │
│  │  (metadata.degradation    ┌─────────────────────┐                    │
│  │   = "L1_PARTIAL")        │  L2: 无辩论         │                    │
│  │                           │  Coder 单独生成      │                    │
│  │                           │  不攻击不审查        │                    │
│  │                           └──────────┬──────────┘                    │
│  │                                 成功？│                              │
│  │                              ┌───────┴───────┐                      │
│  │                             Yes              No                     │
│  │                              │               │                      │
│  │                         返回结果              ▼                      │
│  │                   (= "L2_SINGLE_AGENT")  ┌──────────┐               │
│  │                                          │ L3: 兜底  │               │
│  │                                          │ 返回空结果│               │
│  │                                          │ + 错误原因│               │
│  │                                          └──────────┘               │
│  │                                     (= "L3_UNAVAILABLE")            │
│  └─────────────────────────────────────────────────────────────────────┘
│                                                                          │
│  CircuitBreaker 三态模型：                                               │
│  closed ──(连续3次失败)──▶ open ──(60秒后)──▶ half-open ──(成功)──▶ closed│
│                                               ──(失败)──▶ open          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 六、模型路由表

```
┌──────────────────────────────────────────────────────────────┐
│  model_router.py — 谁用大模型谁用小模型                       │
│                                                              │
│  重活 → Opus (claude-opus-4-6)                               │
│  ┌──────────────┬────────────────────────────────┐          │
│  │ coder        │ 写代码、修代码、自测            │          │
│  │ security     │ 安全攻击（要找出真实漏洞）       │          │
│  │ performance  │ 性能攻击（要分析复杂度）         │          │
│  │ correctness  │ 正确性攻击（要验证逻辑）         │          │
│  │ judge        │ 写质量报告（要综合分析）          │          │
│  │ arbitrator   │ 仲裁裁决（要权衡多方证据）       │          │
│  └──────────────┴────────────────────────────────┘          │
│                                                              │
│  轻活 → Haiku (claude-haiku-4-5-20251001)                    │
│  ┌──────────────┬────────────────────────────────┐          │
│  │ planner      │ 方案设计（只说思路不写代码）     │          │
│  │ cross_review │ 交叉审阅（看对方发现，补充确认） │          │
│  │ compressor   │ 上下文压缩（摘要）              │          │
│  │ test_generator│ 生成测试用例                   │          │
│  │ req_parser   │ 解析用户需求                    │          │
│  └──────────────┴────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
```

---

## 七、面试快速回答模板

> 面试官问："说说你这个项目用了什么技术？"

**30 秒版：**
"用 LangGraph 编排 9 个节点的有向图，Coder→3 个 Attacker 是并行 fan-out，共识检测做条件路由。所有 Agent 输出用 Anthropic tool_use 强制结构化，不做文本解析。3 个用户交互点用 LangGraph interrupt + WebSocket 实现图暂停-恢复。代码执行在 Docker 沙箱里隔离，5 层安全约束。"

**追问"WebSocket 具体怎么用的？"**
"两个方向：后端通过 on_progress 回调实时推事件给前端——进度、Agent 状态、消息；反过来，LangGraph interrupt 暂停图执行后，通过 WebSocket 把 interrupt payload 推给前端，用户操作完 WebSocket 回传 interrupt_response，后端 asyncio.Queue 接收，Command(resume) 恢复图执行。所有交互 120 秒超时自动推进。REST 模式没有 WebSocket，interrupt 全部跳过。"

**追问"tool_use 是什么？为什么不直接让 LLM 输出 JSON？"**
"tool_use 是 Anthropic API 原生支持的结构化输出机制。我给每个 Agent 定义了一个 Tool（比如 Attacker 的 submit_review），用 tool_choice 强制 LLM 调用这个工具。LLM 的输出直接就是 JSON 对象，不需要正则提取、不会格式错误。Coder 比较特殊，tool_choice 是 'any'，因为它需要先调 run_code_snippet 自测，再调 submit_response 提交，形成一个最多 5 轮的 tool_use loop。"

**追问"降级机制怎么做的？"**
"四级降级。L0 是完整 LangGraph 辩论，超时或异常后 CircuitBreaker 计数，连续 3 次触发熔断。L1 切到精简辩论——只保留 correctness attacker、2 轮、跳过交叉审阅。L1 也失败就 L2 无辩论直出。L3 返回空结果。熔断 60 秒后半开尝试恢复。"
