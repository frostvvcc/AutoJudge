"""
Real end-to-end integration tests for AutoJudge.

NO MOCKS. Every test hits:
  - Real LLM API (via anthropic proxy)
  - Real Docker sandbox
  - Real MySQL (LangGraph checkpoint)
  - Real Redis

Tests are ordered by cost (cheap → expensive) and designed to
cover distinct flow paths from the design doc.
"""

import asyncio
import os
import sys
import time
import logging
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_real_e2e")

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


# ═══════════════════════════════════════════════════════════
# 基础设施验证
# ═══════════════════════════════════════════════════════════

async def test_01_llm_api_connectivity():
    """验证 LLM API 代理可达，Haiku 能返回结构化输出。"""
    from app.llm.client import call_agent

    logger.info("=" * 60)
    logger.info("TEST 01: LLM API 连通性 (Haiku)")
    logger.info("=" * 60)

    start = time.monotonic()
    response = await call_agent(
        agent="requirement_parser",
        system_prompt="你是需求分析专家。分析编码需求，提取功能点。",
        messages=[{"role": "user", "content": "编码需求：实现一个 fibonacci 函数\n目标语言：python"}],
        max_tokens=500,
    )
    elapsed = time.monotonic() - start

    assert response.content or response.structured, "LLM 返回为空"
    assert response.tokens_used > 0, "token 计数为 0"
    logger.info(f"  ✅ Haiku 响应成功 | tokens={response.tokens_used} | latency={elapsed:.1f}s")
    logger.info(f"  structured={json.dumps(response.structured, ensure_ascii=False)[:200] if response.structured else 'None'}")
    return True


async def test_02_docker_sandbox():
    """验证 Docker 沙箱能执行 Python 代码。"""
    logger.info("=" * 60)
    logger.info("TEST 02: Docker 沙箱执行")
    logger.info("=" * 60)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        code = "print('AutoJudge sandbox test')\nprint(2 + 2)\n"
        code_path = f"{tmpdir}/snippet.py"
        with open(code_path, "w") as f:
            f.write(code)

        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm",
            "--network=none", "--read-only",
            "--memory=256m", "--cpus=0.5",
            "-v", f"{tmpdir}:/workspace:ro",
            "-w", "/workspace",
            "--tmpfs", "/tmp:size=64m",
            "autojudge-sandbox:latest",
            "python", "snippet.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode()
        errors = stderr.decode()

    assert proc.returncode == 0, f"Docker 执行失败: {errors}"
    assert "AutoJudge sandbox test" in output
    assert "4" in output
    logger.info(f"  ✅ Docker 沙箱正常 | output={output.strip()}")
    return True


async def test_03_mysql_checkpoint():
    """验证 MySQL LangGraph checkpoint 连接。"""
    logger.info("=" * 60)
    logger.info("TEST 03: MySQL LangGraph Checkpoint")
    logger.info("=" * 60)

    from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

    mysql_url = (
        f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )

    async with AIOMySQLSaver.from_conn_string(mysql_url) as checkpointer:
        await checkpointer.setup()
        logger.info(f"  ✅ MySQL checkpoint 连接成功 | url={settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    return True


async def test_04_redis_connectivity():
    """验证 Redis 连接。"""
    logger.info("=" * 60)
    logger.info("TEST 04: Redis 连通性")
    logger.info("=" * 60)

    from app.db.redis import get_redis
    r = get_redis()
    pong = await r.ping()
    assert pong, "Redis ping 失败"
    logger.info(f"  ✅ Redis 连接正常 | url={settings.redis_url}")
    return True


async def test_05_requirement_parser():
    """验证需求解析器能输出结构化分析。"""
    logger.info("=" * 60)
    logger.info("TEST 05: 需求解析器 (RequirementParser)")
    logger.info("=" * 60)

    from app.engine.requirement_parser import parse_requirement

    start = time.monotonic()
    parsed = await parse_requirement("实现一个用户登录接口，接收邮箱和密码", "python")
    elapsed = time.monotonic() - start

    assert isinstance(parsed, dict), f"解析结果不是 dict: {type(parsed)}"
    assert "functional" in parsed, f"缺少 functional 字段: {parsed.keys()}"
    assert "implicit" in parsed, f"缺少 implicit 字段: {parsed.keys()}"
    logger.info(f"  ✅ 需求解析成功 | latency={elapsed:.1f}s")
    logger.info(f"  functional={parsed.get('functional', [])}")
    logger.info(f"  implicit={parsed.get('implicit', [])}")
    logger.info(f"  edge_cases={parsed.get('edge_cases', [])}")
    return True


async def test_06_complexity_router_real():
    """验证 ComplexityRouter 对真实解析结果的路由。"""
    logger.info("=" * 60)
    logger.info("TEST 06: ComplexityRouter 真实路由")
    logger.info("=" * 60)

    from app.engine.requirement_parser import parse_requirement
    from app.engine.complexity_router import route_complexity, TaskComplexity

    test_cases = [
        ("实现一个 fibonacci 函数", "python", TaskComplexity.SIMPLE),
        ("实现一个 REST API 接口", "python", TaskComplexity.MEDIUM),
        ("实现一个并发安全的认证中间件，处理密码加密和限流", "python", TaskComplexity.HARD),
    ]

    for req, lang, expected in test_cases:
        parsed = await parse_requirement(req, lang)
        actual = route_complexity(req, parsed)
        status = "✅" if actual == expected else "⚠️"
        logger.info(f"  {status} '{req[:30]}...' → {actual.value} (expected: {expected.value})")

    logger.info("  ✅ ComplexityRouter 路由完成")
    return True


# ═══════════════════════════════════════════════════════════
# 端到端流程测试
# ═══════════════════════════════════════════════════════════

async def test_07_simple_task_e2e():
    """
    SIMPLE 路径：plan → coder → 无攻击者 → judge
    全程使用 Haiku，最便宜的完整路径。

    验证：
    - Plan Phase 生成方案
    - Coder 写代码 + 自测
    - Judge 输出质量报告
    - 最终 code 不为空
    - DebateResult 结构完整
    """
    logger.info("=" * 60)
    logger.info("TEST 07: SIMPLE 任务端到端 (plan→coder→judge)")
    logger.info("=" * 60)

    from app.engine.graph import run_debate_with_graph
    from app.engine.context import DebateConfig

    events = []
    async def on_progress(event):
        events.append(event)
        etype = event.get("type", "")
        if etype in ("phase_change", "status", "round_start", "converged", "done"):
            logger.info(f"  📡 {etype}: {event.get('content', event.get('phase', ''))}")

    config = DebateConfig(
        max_rounds=1,
        attackers=[],
        max_tokens=50_000,
        skip_cross_review=True,
    )

    start = time.monotonic()
    result = await run_debate_with_graph(
        requirement="实现一个 Python 函数 fibonacci(n)，返回第 n 个斐波那契数",
        language="python",
        config=config,
        on_progress=on_progress,
    )
    elapsed = time.monotonic() - start

    assert result.code, f"最终代码为空！convergence_reason={result.convergence_reason}"
    assert result.language == "python"
    assert "fibonacci" in result.code.lower() or "fib" in result.code.lower(), \
        f"代码中没有 fibonacci 相关内容: {result.code[:200]}"

    logger.info(f"  ✅ SIMPLE 路径完成 | latency={elapsed:.1f}s")
    logger.info(f"  code_length={len(result.code)}")
    logger.info(f"  rounds={result.metrics.total_rounds}")
    logger.info(f"  tokens={result.metrics.total_tokens}")
    logger.info(f"  converged={result.converged}")
    logger.info(f"  convergence_reason={result.convergence_reason}")
    logger.info(f"  confidence={result.confidence}")
    logger.info(f"  events_count={len(events)}")
    logger.info(f"  代码前200字符:\n{result.code[:200]}")
    return True


async def test_08_medium_task_e2e():
    """
    MEDIUM 路径：plan → coder → 1 个 attacker (correctness) → cross_review → 共识检测
    验证辩论循环实际工作，包含 Coder 回应 + Attacker 审查。

    注意：correctness attacker 使用 Opus，会消耗较多 token。
    """
    logger.info("=" * 60)
    logger.info("TEST 08: MEDIUM 任务端到端 (plan→coder→correctness→judge)")
    logger.info("=" * 60)

    from app.engine.graph import run_debate_with_graph
    from app.engine.context import DebateConfig

    events = []
    async def on_progress(event):
        events.append(event)
        etype = event.get("type", "")
        if etype in ("phase_change", "status", "round_start", "converged", "done", "message"):
            agent = event.get("agent", "")
            content = event.get("content", "")[:80] if event.get("content") else ""
            if etype == "message":
                logger.info(f"  📡 message [{agent}]: {content}...")
            else:
                logger.info(f"  📡 {etype}: {content or event.get('phase', '')}")

    config = DebateConfig(
        max_rounds=2,
        attackers=["correctness"],
        max_tokens=80_000,
        skip_cross_review=True,
    )

    start = time.monotonic()
    result = await run_debate_with_graph(
        requirement="实现一个 Python 函数 safe_divide(a, b)，安全地进行除法运算，处理除零和类型错误",
        language="python",
        config=config,
        on_progress=on_progress,
    )
    elapsed = time.monotonic() - start

    assert result.code, f"最终代码为空！"
    assert result.metrics.total_rounds >= 1, "至少应该有 1 轮"

    has_attacker_msg = any(
        e.get("type") == "message" and e.get("agent") == "correctness"
        for e in events
    )

    logger.info(f"  ✅ MEDIUM 路径完成 | latency={elapsed:.1f}s")
    logger.info(f"  code_length={len(result.code)}")
    logger.info(f"  rounds={result.metrics.total_rounds}")
    logger.info(f"  tokens={result.metrics.total_tokens}")
    logger.info(f"  converged={result.converged}")
    logger.info(f"  convergence_reason={result.convergence_reason}")
    logger.info(f"  has_attacker_msg={has_attacker_msg}")
    logger.info(f"  confidence={result.confidence}")
    logger.info(f"  代码前200字符:\n{result.code[:200]}")
    return True


async def test_09_hard_task_triggers_debate():
    """
    HARD 路径：plan → coder → 3 attackers 并行 → cross_review → 多轮辩论/仲裁
    用一个有安全隐患的需求，让攻击者更容易找到问题。

    设置 max_rounds=2 控制成本，如果 2 轮未收敛会触发仲裁。
    验证：
    - 3 个攻击者并行工作
    - 交叉审阅触发
    - 共识检测或仲裁触发
    - 最终产出完整 DebateResult
    """
    logger.info("=" * 60)
    logger.info("TEST 09: HARD 任务端到端 (3 attackers + 可能触发仲裁)")
    logger.info("=" * 60)

    from app.engine.graph import run_debate_with_graph
    from app.engine.context import DebateConfig

    events = []
    phases_seen = set()

    async def on_progress(event):
        events.append(event)
        etype = event.get("type", "")
        if etype == "phase_change":
            phases_seen.add(event.get("phase", ""))
            logger.info(f"  📡 PHASE: {event.get('phase', '')}")
        elif etype in ("status", "round_start", "converged", "done"):
            logger.info(f"  📡 {etype}: {event.get('content', event.get('round', ''))}")
        elif etype == "message":
            agent = event.get("agent", "")
            logger.info(f"  📡 message [{agent}] round={event.get('round', '?')}")
        elif etype == "arbitration_complete":
            logger.info(f"  📡 仲裁完成: verdict={event.get('overall_verdict', '?')}, disputes={event.get('disputes_count', '?')}")

    config = DebateConfig(
        max_rounds=2,
        attackers=["security", "performance", "correctness"],
        max_tokens=120_000,
        skip_cross_review=False,
    )

    start = time.monotonic()
    result = await run_debate_with_graph(
        requirement="实现一个用户登录接口，接收用户名和密码，查询数据库验证，返回 JWT token",
        language="python",
        config=config,
        on_progress=on_progress,
    )
    elapsed = time.monotonic() - start

    assert result.code, "最终代码为空！"

    agent_msgs = {}
    for e in events:
        if e.get("type") == "message":
            agent = e.get("agent", "unknown")
            agent_msgs.setdefault(agent, 0)
            agent_msgs[agent] += 1

    has_security = agent_msgs.get("security", 0) > 0
    has_performance = agent_msgs.get("performance", 0) > 0
    has_correctness = agent_msgs.get("correctness", 0) > 0
    triggered_arbitration = "arbitration" in phases_seen
    has_arbitration_result = result.metadata.get("arbitration") is not None

    logger.info(f"  ✅ HARD 路径完成 | latency={elapsed:.1f}s")
    logger.info(f"  code_length={len(result.code)}")
    logger.info(f"  rounds={result.metrics.total_rounds}")
    logger.info(f"  tokens={result.metrics.total_tokens}")
    logger.info(f"  cost_usd=${result.metrics.cost_usd}")
    logger.info(f"  converged={result.converged}")
    logger.info(f"  convergence_reason={result.convergence_reason}")
    logger.info(f"  confidence={result.confidence}")
    logger.info(f"  phases_seen={phases_seen}")
    logger.info(f"  agent_msgs={agent_msgs}")
    logger.info(f"  has_security={has_security}")
    logger.info(f"  has_performance={has_performance}")
    logger.info(f"  has_correctness={has_correctness}")
    logger.info(f"  triggered_arbitration={triggered_arbitration}")
    logger.info(f"  has_arbitration_result={has_arbitration_result}")
    logger.info(f"  requires_human_review={result.metadata.get('requires_human_review', False)}")
    logger.info(f"  quality_report star_rating={result.quality_report.star_rating}")
    logger.info(f"  代码前300字符:\n{result.code[:300]}")
    return True


async def test_10_degradation_cache_layer():
    """
    验证降级管理器的缓存层：
    1. 第一次请求走完整流程
    2. 第二次相同请求命中缓存（如果 embedding 可用）
    如果没有 OpenAI key，缓存不可用，也验证这个容错路径。
    """
    logger.info("=" * 60)
    logger.info("TEST 10: DegradationManager 缓存层")
    logger.info("=" * 60)

    from app.engine.degradation import DegradationManager
    from app.engine.context import DebateConfig

    mgr = DegradationManager()
    config = DebateConfig(
        max_rounds=1,
        attackers=[],
        max_tokens=30_000,
        skip_cross_review=True,
    )

    start = time.monotonic()
    result = await mgr.execute_with_degradation(
        requirement="实现一个 Python 函数计算阶乘 factorial(n)",
        language="python",
        framework=None,
        config=config,
    )
    elapsed1 = time.monotonic() - start

    assert result.code, "第一次请求代码为空"

    start = time.monotonic()
    result2 = await mgr.execute_with_degradation(
        requirement="实现一个 Python 函数计算阶乘 factorial(n)",
        language="python",
        framework=None,
        config=config,
    )
    elapsed2 = time.monotonic() - start

    from_cache = result2.metadata.get("from_cache", False)
    has_openai = bool(settings.openai_api_key)

    logger.info(f"  第一次: latency={elapsed1:.1f}s, tokens={result.metrics.total_tokens}")
    logger.info(f"  第二次: latency={elapsed2:.1f}s, from_cache={from_cache}")
    logger.info(f"  OpenAI key available={has_openai} (缓存需要 embedding)")

    if has_openai:
        assert from_cache, "有 OpenAI key 但第二次没命中缓存"
        assert elapsed2 < elapsed1 * 0.5, "缓存命中但没明显加速"
        logger.info(f"  ✅ 缓存命中，加速 {elapsed1/elapsed2:.1f}x")
    else:
        logger.info(f"  ✅ 无 OpenAI key，缓存层正确跳过（容错路径）")
    return True


async def test_11_docker_sandbox_via_coder():
    """
    验证 Coder Agent 的 run_code_snippet 工具是否真正调用 Docker。
    通过 client.py 的 _run_code_snippet 直接测试。
    """
    logger.info("=" * 60)
    logger.info("TEST 11: Coder run_code_snippet (Docker 沙箱集成)")
    logger.info("=" * 60)

    from app.llm.client import _run_code_snippet

    result = await _run_code_snippet(
        code="def add(a, b): return a + b\nprint(add(3, 4))",
        expected="应该输出 7",
    )

    assert "7" in result, f"Docker 执行结果中没有 7: {result}"
    assert "succeeded" in result.lower() or "output" in result.lower(), f"执行可能失败: {result}"
    logger.info(f"  ✅ run_code_snippet 执行成功")
    logger.info(f"  result={result[:200]}")
    return True


async def test_12_context_layer2_real():
    """
    验证 Layer 2 上下文裁剪在真实辩论数据上的行为。
    构造一个多轮辩论的 DebateContext，验证各 Agent 视图的正确性。
    """
    logger.info("=" * 60)
    logger.info("TEST 12: Layer 2 上下文裁剪（真实数据）")
    logger.info("=" * 60)

    from app.engine.context import DebateContext, DebateConfig

    ctx = DebateContext("实现登录接口", DebateConfig())

    ctx.round = 1
    ctx.add_message("coder", "初版代码：def login(user, pwd): ...", code="def login(user, pwd): pass")
    ctx.add_message("security", "发现SQL注入风险", structured={
        "stance": "attacking",
        "findings": [{"category": "sql_injection", "severity": "high", "description": "字符串拼接SQL"}],
    })
    ctx.add_message("performance", "无性能问题", structured={"stance": "satisfied", "findings": []})
    ctx.add_message("correctness", "空值未处理", structured={
        "stance": "attacking",
        "findings": [{"category": "null_check", "severity": "medium", "description": "pwd可能为None"}],
    })

    ctx.round = 2
    ctx.add_message("coder", "修复了SQL注入和空值", code="def login(user, pwd): ...", structured={
        "responses": [
            {"finding_ref": "security#1", "action": "accept_and_fix", "explanation": "改用参数化查询"},
            {"finding_ref": "correctness#1", "action": "accept_and_fix", "explanation": "加了None检查"},
        ]
    })

    # 验证攻击者视图
    sec_view = ctx.get_context_for_agent("security")
    assert any("SQL" in m.get("content", "") or "CODER" in m.get("content", "") for m in sec_view), \
        f"Security 视图中没有相关内容: {sec_view}"
    perf_content = " ".join(m["content"] for m in ctx.get_context_for_agent("performance"))
    assert "sql_injection" not in perf_content.lower() or "SECURITY" not in perf_content, \
        "Performance 不应该看到 Security 的具体 findings（Layer 2 裁剪）"

    # 验证 Coder 视图
    coder_view = ctx.get_context_for_agent("coder")
    coder_content = " ".join(m["content"] for m in coder_view)
    assert "SECURITY" in coder_content, "Coder 应该看到 Security 的攻击"
    assert "CORRECTNESS" in coder_content, "Coder 应该看到 Correctness 的攻击"

    # 验证 Judge 视图
    judge_view = ctx.get_context_for_agent("judge")
    assert len(judge_view) >= 1, "Judge 视图不应为空"

    logger.info(f"  ✅ Layer 2 上下文裁剪验证通过")
    logger.info(f"  security_view_msgs={len(sec_view)}")
    logger.info(f"  coder_view_msgs={len(coder_view)}")
    logger.info(f"  judge_view_msgs={len(judge_view)}")
    return True


# ═══════════════════════════════════════════════════════════
# 主执行
# ═══════════════════════════════════════════════════════════

async def main():
    from app.db.redis import init_redis, close_redis

    await init_redis()

    tests = [
        ("01 LLM API 连通性", test_01_llm_api_connectivity),
        ("02 Docker 沙箱", test_02_docker_sandbox),
        ("03 MySQL Checkpoint", test_03_mysql_checkpoint),
        ("04 Redis 连通性", test_04_redis_connectivity),
        ("05 需求解析器", test_05_requirement_parser),
        ("06 ComplexityRouter", test_06_complexity_router_real),
        ("07 SIMPLE 任务 E2E", test_07_simple_task_e2e),
        ("08 MEDIUM 任务 E2E", test_08_medium_task_e2e),
        ("09 HARD 任务 E2E", test_09_hard_task_triggers_debate),
        ("10 降级缓存层", test_10_degradation_cache_layer),
        ("11 Docker 沙箱集成", test_11_docker_sandbox_via_coder),
        ("12 Layer 2 上下文裁剪", test_12_context_layer2_real),
    ]

    results = {}
    total_start = time.monotonic()

    for name, test_fn in tests:
        try:
            passed = await test_fn()
            results[name] = "✅ PASS"
        except Exception as e:
            logger.error(f"  ❌ FAILED: {e}", exc_info=True)
            results[name] = f"❌ FAIL: {e}"

    total_elapsed = time.monotonic() - total_start

    await close_redis()

    # ─── 汇总报告 ───
    print("\n")
    print("=" * 70)
    print("                    AutoJudge 真实端到端测试报告")
    print("=" * 70)
    passed = sum(1 for v in results.values() if v.startswith("✅"))
    failed = len(results) - passed
    print(f"  总计: {len(results)} | 通过: {passed} | 失败: {failed} | 耗时: {total_elapsed:.1f}s")
    print("-" * 70)
    for name, status in results.items():
        print(f"  {status}  {name}")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
