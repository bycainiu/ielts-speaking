from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.mcp.report_mcp import PracticePlanInput, ReportEvidence, ScoreReportInput
from app.rag.chunk_schema import ScoringCriterion


CRITERION_LABELS: dict[ScoringCriterion, str] = {
    "fluency_coherence": "Fluency and Coherence",
    "lexical_resource": "Lexical Resource",
    "grammatical_range_accuracy": "Grammar Range and Accuracy",
    "pronunciation": "Pronunciation",
}
CRITERION_FOCUS: dict[ScoringCriterion, str] = {
    "fluency_coherence": "流利度和连贯展开",
    "lexical_resource": "话题词与具体表达",
    "grammatical_range_accuracy": "句型控制和准确性",
    "pronunciation": "可懂度、节奏和停顿分块",
}
WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


class FeedbackCoachAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)
    question_text: str | None = None
    part: Literal[1, 2, 3] | None = None
    topic: str | None = None
    topic_guidance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", "transcript", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("text is required")
        return text


class GeneratedFeedbackItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ScoringCriterion
    priority: int = Field(ge=1, le=5)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class GeneratedReferenceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str | None = None
    band_target: float | None = Field(default=None, ge=0, le=9)
    skeleton: dict[str, Any] = Field(default_factory=dict)
    answer_text: str = Field(min_length=1)
    personalization_notes: str | None = None


class FeedbackCoachInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    score_report: ScoreReportInput
    answers: list[FeedbackCoachAnswer] = Field(default_factory=list)
    user_background: dict[str, Any] = Field(default_factory=dict)
    max_feedback_items: int = Field(default=3, ge=1, le=5)


class FeedbackCoachOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    feedback_items: list[GeneratedFeedbackItem] = Field(default_factory=list)
    reference_answers: list[GeneratedReferenceAnswer] = Field(default_factory=list)
    next_practice_plan: list[PracticePlanInput] = Field(default_factory=list)
    raw_output: dict[str, Any] = Field(default_factory=dict)


class FeedbackCoachAgent:
    coach_version = "feedback_coach.v1"

    def generate(self, coach_input: FeedbackCoachInput) -> FeedbackCoachOutput:
        weakest = weakest_criteria(coach_input.score_report)
        selected = weakest[: coach_input.max_feedback_items]
        primary_answer = select_primary_answer(coach_input.answers)
        feedback_items = [
            feedback_for_criterion(criterion, score, priority=index + 1)
            for index, (criterion, score) in enumerate(selected)
        ]
        reference_answers = []
        if primary_answer is not None:
            reference_answers.append(
                build_reference_answer(
                    primary_answer,
                    target_band=target_reference_band(coach_input.score_report.overall_band),
                    user_background=coach_input.user_background,
                )
            )
        next_plan = [
            PracticePlanInput(
                priority=index + 1,
                focus=CRITERION_FOCUS[criterion],
                task=practice_task_for_criterion(criterion),
            )
            for index, (criterion, _score) in enumerate(selected[:3])
        ]

        focus_text = "、".join(CRITERION_FOCUS[criterion] for criterion, _score in selected[:2])
        summary = (
            f"当前模拟总分为 {coach_input.score_report.overall_band:.1f}，"
            f"本轮最值得优先处理的是 {focus_text or '回答展开和证据质量'}。"
        )
        return FeedbackCoachOutput(
            summary=summary,
            feedback_items=feedback_items,
            reference_answers=reference_answers,
            next_practice_plan=next_plan,
            raw_output={
                "coach_version": self.coach_version,
                "selected_criteria": [criterion for criterion, _score in selected],
                "answer_count": len(coach_input.answers),
                "reference_answer_policy": "flexible_model_not_memorization_script",
            },
        )


def weakest_criteria(report: ScoreReportInput) -> list[tuple[ScoringCriterion, Any]]:
    return sorted(
        report.criteria.items(),
        key=lambda item: (item[1].band, item[1].confidence, criterion_sort_weight(item[0])),
    )


def criterion_sort_weight(criterion: ScoringCriterion) -> int:
    order: dict[ScoringCriterion, int] = {
        "fluency_coherence": 0,
        "lexical_resource": 1,
        "grammatical_range_accuracy": 2,
        "pronunciation": 3,
    }
    return order[criterion]


def feedback_for_criterion(criterion: ScoringCriterion, score: Any, *, priority: int) -> GeneratedFeedbackItem:
    suggestion = first_suggestion(score.suggestions, criterion)
    evidence_refs = [evidence_ref(item) for item in score.evidence[:2]]
    label = CRITERION_LABELS[criterion]
    return GeneratedFeedbackItem(
        category=criterion,
        priority=priority,
        title=f"优先改进 {label}",
        body=(
            f"该维度当前为 Band {score.band:.1f}，置信度 {score.confidence:.2f}。"
            f"{suggestion} 下次回答后请用同一条标准复听 1 次，只改一个最明显的问题。"
        ),
        evidence_refs=evidence_refs,
    )


def first_suggestion(suggestions: list[str], criterion: ScoringCriterion) -> str:
    if suggestions:
        return suggestions[0]
    defaults: dict[ScoringCriterion, str] = {
        "fluency_coherence": "先用一句直接回答，再补原因和例子，避免只给结论。",
        "lexical_resource": "准备 2-3 个贴近题目的自然搭配，用具体名词替换泛泛表达。",
        "grammatical_range_accuracy": "优先保证主谓一致和时态稳定，再增加从句或对比结构。",
        "pronunciation": "用意群分块朗读答案，保证关键词清楚，不追求夸张口音。",
    }
    return defaults[criterion]


def evidence_ref(evidence: ReportEvidence) -> dict[str, Any]:
    return {
        "turn_id": evidence.turn_id,
        "quote": evidence.quote,
        "reason": evidence.reason,
    }


def select_primary_answer(answers: list[FeedbackCoachAnswer]) -> FeedbackCoachAnswer | None:
    if not answers:
        return None
    return max(answers, key=lambda item: len(WORD_RE.findall(item.transcript)))


def target_reference_band(overall_band: float) -> float:
    return max(6.0, min(7.5, round((overall_band + 0.5) * 2) / 2))


def build_reference_answer(
    answer: FeedbackCoachAnswer,
    *,
    target_band: float,
    user_background: dict[str, Any],
) -> GeneratedReferenceAnswer:
    topic = readable_topic(answer)
    background_hint = safe_background_hint(user_background)
    skeleton = {
        "opening": "直接回答题目，不绕圈。",
        "reason": "给出一个清楚原因，并用 because / so 连接。",
        "example": "加入一个真实、短小的个人例子。",
        "extension": "补一句影响或感受，避免背诵整段。",
    }
    if answer.part == 2:
        skeleton = {
            "opening": "点明要描述的人、地点、物品或经历。",
            "detail_1": "补充时间、地点、参与者等具体信息。",
            "detail_2": "讲一个可视化的小事件，而不是罗列形容词。",
            "reflection": "解释为什么这件事重要或难忘。",
        }
    elif answer.part == 3:
        skeleton = {
            "position": "先给出观点。",
            "reason": "解释背后的社会或现实原因。",
            "example": "给一个群体或城市层面的例子。",
            "balance": "补一句对比或限制，让回答更像讨论。",
        }

    answer_text = reference_text_for(answer, topic=topic, background_hint=background_hint)
    return GeneratedReferenceAnswer(
        turn_id=answer.turn_id,
        band_target=target_band,
        skeleton=skeleton,
        answer_text=answer_text,
        personalization_notes="这是可替换的结构示例，不建议逐句背诵；请把例子换成自己的真实经历和熟悉表达。",
    )


def reference_text_for(answer: FeedbackCoachAnswer, *, topic: str, background_hint: str | None) -> str:
    personal_clause = f" In my own case, {background_hint}." if background_hint else ""
    if answer.part == 2:
        return (
            f"I'd like to talk about {topic}. The first thing I remember is the specific situation, "
            "because small details make the story easier to follow. Then I would explain what happened, "
            "who was involved, and why it mattered to me."
            f"{personal_clause} What made it memorable was not that it was perfect, but that it gave me "
            "a clear feeling or lesson I can describe naturally."
        )
    if answer.part == 3:
        return (
            f"In my view, {topic} matters because it affects both individual choices and the wider community. "
            "One reason is that people often make decisions based on convenience, cost, and social expectations. "
            "For example, a city or school can shape people's habits by making some choices easier than others."
            f"{personal_clause} At the same time, it depends on age, background, and personal priorities, so "
            "there is rarely one answer that fits everyone."
        )
    return (
        f"I would say {topic} is part of my everyday life, but the main reason is quite practical. "
        "It helps me organize my time and feel more comfortable with what I am doing. "
        "For example, I usually connect it with a real place, person, or routine, so my answer sounds specific."
        f"{personal_clause} Overall, I think a simple answer with one clear example is better than a long memorized one."
    )


def readable_topic(answer: FeedbackCoachAnswer) -> str:
    if answer.topic:
        return answer.topic.replace("_", " ")
    guidance = answer.topic_guidance or {}
    primary_topic = guidance.get("primary_topic")
    if primary_topic:
        return str(primary_topic).replace("_", " ")
    question = (answer.question_text or "").strip().rstrip("?")
    if question:
        return "this topic"
    return "this question"


def safe_background_hint(user_background: dict[str, Any]) -> str | None:
    for key in ("agent_facts", "facts", "background_facts"):
        facts = user_background.get(key)
        if isinstance(facts, list):
            for item in facts:
                if isinstance(item, dict):
                    value = item.get("fact_value") or item.get("value")
                    if value:
                        return str(value).strip()
                elif item:
                    return str(item).strip()
    profile = user_background.get("profile")
    if isinstance(profile, dict):
        for key in ("occupation", "city", "study_field"):
            value = profile.get(key)
            if value:
                return str(value).strip()
    return None


def practice_task_for_criterion(criterion: ScoringCriterion) -> str:
    tasks: dict[ScoringCriterion, str] = {
        "fluency_coherence": "录一段 60-90 秒回答，强制使用“观点-原因-例子-补充”四步结构。",
        "lexical_resource": "为同一题准备 5 个自然搭配，并用其中 2 个重新回答，不追求生僻词。",
        "grammatical_range_accuracy": "选 3 句原回答，改写成一个简单句、一个原因句、一个对比句。",
        "pronunciation": "把参考答案按意群切成 5-7 段，慢速朗读并检查关键词是否清楚。",
    }
    return tasks[criterion]
