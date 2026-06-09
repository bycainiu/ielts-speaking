from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.score_calibrator import CalibrationAnchorSample
from app.rag.chunk_schema import ScoringCriterion


SourceCompliance = Literal["synthetic_internal", "authorized", "user_consent"]


class AnchorCriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: float = Field(ge=0, le=9)
    rationale: str = Field(min_length=1)


class AnchorSpeakingSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    part: Literal[1, 2, 3]
    target_band: float = Field(ge=4, le=8)
    transcript: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    source_compliance: SourceCompliance
    scores: dict[ScoringCriterion, AnchorCriterionScore]
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_all_criteria(self) -> "AnchorSpeakingSample":
        required = {"fluency_coherence", "lexical_resource", "grammatical_range_accuracy", "pronunciation"}
        missing = required.difference(self.scores)
        if missing:
            raise ValueError(f"anchor sample missing criteria: {', '.join(sorted(missing))}")
        return self


class AnchorDatasetAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_count: int = Field(ge=0)
    covered_bands: list[float] = Field(default_factory=list)
    covered_criteria: list[str] = Field(default_factory=list)
    source_compliance_values: list[str] = Field(default_factory=list)
    passed: bool
    findings: list[str] = Field(default_factory=list)


def build_default_anchor_samples() -> list[AnchorSpeakingSample]:
    raw_samples: list[dict[str, Any]] = [
        {
            "sample_id": "anchor-b4-part1-hometown",
            "part": 1,
            "target_band": 4.0,
            "topic": "hometown",
            "transcript": "My hometown is small. I like it because my family there. It has shops and park. I go there sometimes.",
            "scores": {
                "fluency_coherence": (4.0, "短句为主，连接较弱，展开有限。"),
                "lexical_resource": (4.0, "词汇简单重复，话题词有限。"),
                "grammatical_range_accuracy": (4.0, "基础句可理解，但有明显语法错误。"),
                "pronunciation": (4.0, "可懂度尚可，但停顿和节奏不稳定。"),
            },
        },
        {
            "sample_id": "anchor-b5-part2-place",
            "part": 2,
            "target_band": 5.0,
            "topic": "public_places",
            "transcript": "I want to describe a park near my house. I went there with my friend last month. The park is beautiful and quiet, and we talked for a long time. I like it because it helps me relax after study.",
            "scores": {
                "fluency_coherence": (5.0, "能持续表达，但细节和组织仍偏简单。"),
                "lexical_resource": (5.0, "词汇足以说明主题，但搭配不够丰富。"),
                "grammatical_range_accuracy": (5.0, "简单句准确度尚可，复杂结构有限。"),
                "pronunciation": (5.0, "整体可懂，节奏和重音证据有限。"),
            },
        },
        {
            "sample_id": "anchor-b6-part1-study",
            "part": 1,
            "target_band": 6.0,
            "topic": "study",
            "transcript": "I am studying computer science at university. I chose it because I enjoy solving practical problems, especially when a small program can make daily work easier. Sometimes the courses are stressful, but they also give me a clear goal.",
            "scores": {
                "fluency_coherence": (6.0, "回答有原因和例子，偶尔略停顿。"),
                "lexical_resource": (6.0, "有自然话题词和搭配，仍可更灵活。"),
                "grammatical_range_accuracy": (6.0, "简单和部分复杂结构混合，错误不妨碍理解。"),
                "pronunciation": (6.0, "可懂度稳定，节奏有基本分块。"),
            },
        },
        {
            "sample_id": "anchor-b7-part3-technology",
            "part": 3,
            "target_band": 7.0,
            "topic": "technology",
            "transcript": "Technology changes education because it gives students access to materials that used to be expensive or difficult to find. At the same time, it cannot replace a good teacher, because students still need guidance, discussion, and feedback to understand ideas deeply.",
            "scores": {
                "fluency_coherence": (7.0, "观点清楚，能平衡两面并自然衔接。"),
                "lexical_resource": (7.0, "词汇贴合抽象讨论，搭配自然。"),
                "grammatical_range_accuracy": (7.0, "复杂句控制较好，错误少。"),
                "pronunciation": (7.0, "重音和意群分块较稳定，可懂度高。"),
            },
        },
        {
            "sample_id": "anchor-b8-part3-city",
            "part": 3,
            "target_band": 8.0,
            "topic": "city_life",
            "transcript": "A comfortable city is not simply a place with tall buildings; it is a place where ordinary routines feel manageable. Reliable transport, safe public spaces, and mixed neighbourhoods allow people from different backgrounds to participate in city life rather than just pass through it.",
            "scores": {
                "fluency_coherence": (8.0, "抽象观点组织成熟，逻辑推进自然。"),
                "lexical_resource": (8.0, "词汇精准，有自然搭配和抽象表达。"),
                "grammatical_range_accuracy": (8.0, "复杂结构多样且控制稳定。"),
                "pronunciation": (8.0, "节奏、重音和可懂度证据强。"),
            },
        },
    ]
    samples: list[AnchorSpeakingSample] = []
    for raw in raw_samples:
        scores = {
            criterion: AnchorCriterionScore(band=band, rationale=rationale)
            for criterion, (band, rationale) in raw["scores"].items()
        }
        samples.append(
            AnchorSpeakingSample(
                sample_id=raw["sample_id"],
                part=raw["part"],
                target_band=raw["target_band"],
                topic=raw["topic"],
                transcript=raw["transcript"],
                source_compliance="synthetic_internal",
                scores=scores,
                notes="内部合成校准样本，仅用于模型回归和模拟评分校准，不作为真实考生样本。",
            )
        )
    return samples


def audit_anchor_dataset(samples: list[AnchorSpeakingSample]) -> AnchorDatasetAudit:
    covered_bands = sorted({sample.target_band for sample in samples})
    covered_criteria = sorted({criterion for sample in samples for criterion in sample.scores})
    source_values = sorted({sample.source_compliance for sample in samples})
    findings: list[str] = []
    for expected_band in [4.0, 5.0, 6.0, 7.0, 8.0]:
        if expected_band not in covered_bands:
            findings.append(f"missing_band:{expected_band:.1f}")
    for criterion in ["fluency_coherence", "lexical_resource", "grammatical_range_accuracy", "pronunciation"]:
        if criterion not in covered_criteria:
            findings.append(f"missing_criterion:{criterion}")
    if any(sample.source_compliance not in {"synthetic_internal", "authorized", "user_consent"} for sample in samples):
        findings.append("source_compliance_invalid")
    return AnchorDatasetAudit(
        sample_count=len(samples),
        covered_bands=covered_bands,
        covered_criteria=covered_criteria,
        source_compliance_values=source_values,
        passed=not findings,
        findings=findings,
    )


def to_calibration_anchor_samples(samples: list[AnchorSpeakingSample]) -> list[CalibrationAnchorSample]:
    anchors: list[CalibrationAnchorSample] = []
    for sample in samples:
        for criterion, score in sample.scores.items():
            anchors.append(
                CalibrationAnchorSample(
                    anchor_sample_id=f"{sample.sample_id}:{criterion}",
                    criterion=criterion,
                    band=score.band,
                    score=1.0,
                    rationale=score.rationale,
                    content=sample.transcript,
                )
            )
    return anchors
