from __future__ import annotations

import logging

import structlog

try:
    from prometheus_client import Counter, Histogram, Gauge

    debate_requests_total = Counter(
        "autojudge_debate_requests_total",
        "Total debate requests",
        ["language", "complexity", "degradation_level"],
    )
    debate_duration_seconds = Histogram(
        "autojudge_debate_duration_seconds",
        "Debate end-to-end duration",
        buckets=[5, 10, 20, 35, 60, 120],
    )
    debate_rounds = Histogram(
        "autojudge_debate_rounds",
        "Number of rounds before convergence",
        buckets=[1, 2, 3, 4, 5, 6, 7],
    )
    debate_convergence_rate = Counter(
        "autojudge_debate_convergence_total",
        "Debates that converged vs forced stop",
        ["outcome"],
    )
    agent_call_duration = Histogram(
        "autojudge_agent_call_seconds",
        "Per-agent LLM call duration",
        ["agent"],
        buckets=[1, 2, 3, 5, 8, 15],
    )
    agent_tokens_used = Histogram(
        "autojudge_agent_tokens",
        "Tokens used per agent call",
        ["agent"],
        buckets=[500, 1000, 2000, 4000, 8000],
    )
    agent_errors_total = Counter(
        "autojudge_agent_errors_total",
        "Agent call failures",
        ["agent", "error_type"],
    )
    rebuttal_total = Counter(
        "autojudge_rebuttal_total",
        "Total rebuttals by Coder",
        ["outcome"],
    )
    tool_assisted_rebuttal = Counter(
        "autojudge_tool_assisted_rebuttal_total",
        "Rebuttals that used tool verification",
    )
    cache_hit_total = Counter(
        "autojudge_cache_total",
        "Cache lookups",
        ["result"],
    )
    active_debates = Gauge(
        "autojudge_active_debates",
        "Currently running debates",
    )

    PROMETHEUS_AVAILABLE = True

except ImportError:
    PROMETHEUS_AVAILABLE = False


logger = structlog.get_logger()


def record_debate_complete(
    language: str,
    complexity: str,
    rounds: int,
    converged: bool,
    duration_s: float,
    degradation_level: str = "L0_NORMAL",
):
    if PROMETHEUS_AVAILABLE:
        debate_requests_total.labels(
            language=language,
            complexity=complexity,
            degradation_level=degradation_level,
        ).inc()
        debate_duration_seconds.observe(duration_s)
        debate_rounds.observe(rounds)
        outcome = "converged" if converged else "forced_stop"
        debate_convergence_rate.labels(outcome=outcome).inc()

    logger.info(
        "debate_complete",
        language=language,
        complexity=complexity,
        rounds=rounds,
        converged=converged,
        duration_s=round(duration_s, 2),
        degradation_level=degradation_level,
    )


def record_agent_call(
    agent: str, tokens: int, duration_s: float
):
    if PROMETHEUS_AVAILABLE:
        agent_call_duration.labels(agent=agent).observe(duration_s)
        agent_tokens_used.labels(agent=agent).observe(tokens)

    logger.info(
        "agent_call_complete",
        agent=agent,
        tokens=tokens,
        duration_s=round(duration_s, 2),
    )


def record_agent_error(agent: str, error_type: str):
    if PROMETHEUS_AVAILABLE:
        agent_errors_total.labels(
            agent=agent, error_type=error_type
        ).inc()

    logger.warning(
        "agent_error", agent=agent, error_type=error_type
    )
