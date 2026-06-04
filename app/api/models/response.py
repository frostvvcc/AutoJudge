from __future__ import annotations

from pydantic import BaseModel, Field


class Finding(BaseModel):
    category: str
    severity: str
    description: str
    test_input: str | None = None


class AgentMessage(BaseModel):
    agent: str
    content: str
    round: int
    code: str | None = None
    structured: dict | None = None


class RoundData(BaseModel):
    round: int
    messages: list[AgentMessage]


class DebateSummary(BaseModel):
    total_issues_raised: int = 0
    accepted_and_fixed: int = 0
    rejected_by_coder: int = 0
    suggestions_noted: int = 0
    key_improvements: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    security: str = "unknown"
    performance: str = "unknown"
    correctness: str = "unknown"


class DebateMetrics(BaseModel):
    total_rounds: int = 0
    total_tokens: int = 0
    total_latency_ms: int = 0
    cost_usd: float = 0.0
    cache_stats: dict = Field(default_factory=dict)
    tokens_by_agent: dict[str, int] = Field(default_factory=dict)


class DebateResult(BaseModel):
    code: str = ""
    language: str = "python"
    confidence: float = 0.0

    debate: dict = Field(default_factory=dict)
    summary: DebateSummary = Field(default_factory=DebateSummary)
    risk_assessment: RiskAssessment = Field(default_factory=RiskAssessment)
    metrics: DebateMetrics = Field(default_factory=DebateMetrics)

    converged: bool = False
    convergence_reason: str = ""
    metadata: dict = Field(default_factory=dict)
