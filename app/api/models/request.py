from __future__ import annotations

import re

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GenerateConfig(BaseModel):
    mode: Literal["flash", "pro"] = "pro"
    max_rounds: int = Field(default=5, ge=1, le=7)
    attackers: list[str] = Field(
        default=["security", "performance", "correctness"]
    )
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = Field(default=100_000, ge=10_000, le=500_000)

    @field_validator("attackers")
    @classmethod
    def validate_attackers(cls, v: list[str]) -> list[str]:
        allowed = {"security", "performance", "correctness"}
        for a in v:
            if a not in allowed:
                raise ValueError(
                    f"Unknown attacker '{a}'. Allowed: {', '.join(sorted(allowed))}"
                )
        return v


class GenerateRequest(BaseModel):
    task: str
    language: str = "python"
    framework: str | None = None
    config: GenerateConfig | None = None

    @field_validator("task")
    @classmethod
    def validate_task(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Task description too short (min 10 chars)")
        if len(v) > 5000:
            raise ValueError("Task description too long (max 5000 chars)")

        injection_patterns = [
            r"ignore\s+(previous|above|all)\s+instructions",
            r"you\s+are\s+now\s+a",
            r"system\s*:\s*",
            r"<\s*system\s*>",
            r"forget\s+(everything|all|your)",
            r"\[INST\]",
            r"<<\s*SYS\s*>>",
        ]
        for pattern in injection_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Invalid input detected")

        return v.strip()

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"python", "javascript", "typescript", "java", "go", "rust"}
        if v.lower() not in allowed:
            raise ValueError(
                f"Unsupported language. Allowed: {', '.join(sorted(allowed))}"
            )
        return v.lower()
