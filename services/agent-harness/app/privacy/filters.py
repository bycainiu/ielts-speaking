from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.observability.langfuse_client import sanitize_text


PrivacyLevel = Literal["normal", "sensitive", "private"]


class BackgroundFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str | None = None
    fact_key: str = Field(min_length=1)
    fact_value: str = Field(min_length=1)
    privacy_level: PrivacyLevel = "normal"
    allowed_usage: list[str] = Field(default_factory=list)
    is_excluded: bool = False

    @field_validator("fact_key", "fact_value", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("required text is empty")
        return text


class PrivacyFilterResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_facts: list[BackgroundFact]
    blocked_fact_keys: list[str]
    trace_payload: dict[str, Any]


def filter_agent_background(
    facts: Sequence[BackgroundFact | Mapping[str, Any]],
    *,
    privacy_exclusions: Sequence[str] = (),
    allowed_levels: Sequence[PrivacyLevel] = ("normal", "sensitive"),
    trace_limit: int = 120,
) -> PrivacyFilterResult:
    exclusion_set = {value.strip().lower() for value in privacy_exclusions if value and value.strip()}
    allowed_level_set = set(allowed_levels)
    prompt_facts: list[BackgroundFact] = []
    blocked: list[str] = []

    for raw_fact in facts:
        fact = raw_fact if isinstance(raw_fact, BackgroundFact) else BackgroundFact.model_validate(raw_fact)
        key = fact.fact_key.strip().lower()
        if fact.is_excluded or key in exclusion_set or fact.privacy_level not in allowed_level_set:
            blocked.append(fact.fact_key)
            continue
        prompt_facts.append(fact)

    return PrivacyFilterResult(
        prompt_facts=prompt_facts,
        blocked_fact_keys=blocked,
        trace_payload={
            "facts": [
                {
                    "topic": fact.topic,
                    "fact_key": fact.fact_key,
                    "fact_value": sanitize_text(fact.fact_value, limit=trace_limit),
                    "privacy_level": fact.privacy_level,
                }
                for fact in prompt_facts
            ],
            "blocked_fact_keys": blocked,
        },
    )


def redact_trace_payload(value: Any, *, limit: int = 300) -> Any:
    if isinstance(value, str):
        return sanitize_text(value, limit=limit)
    if isinstance(value, Mapping):
        return {str(key): redact_trace_payload(nested, limit=limit) for key, nested in value.items()}
    if isinstance(value, list):
        return [redact_trace_payload(item, limit=limit) for item in value]
    return value
