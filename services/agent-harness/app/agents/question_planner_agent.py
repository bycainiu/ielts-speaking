from __future__ import annotations

import re
from hashlib import sha256
from random import Random
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.content.question_text import is_placeholder_question_text
from app.mcp.question_bank_mcp import QuestionBankMcpTools, SearchQuestionsResult
from app.mcp.security import McpAuthorizationError, McpToolContext
from app.protocols.schemas import PlanRequest, SessionMode
from app.rag.llamaindex_service import KnowledgeServiceError


QUESTION_BANK_READ_SCOPE = "question_bank:read"
QUESTION_BANK_PLANNER_TOOLS = ["search_questions", "get_cue_card", "get_followup_templates"]
WORD_RE = re.compile(r"[a-z0-9']+")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
DEFAULT_PART_COUNTS = {1: 4, 2: 1, 3: 2}
PART_TIMER_SECONDS = {1: 30, 2: 120, 3: 45}
PART_TIMEBOX_SECONDS = {1: 300, 2: 180, 3: 300}
PLANNER_VERSION = "question_set_planner.v1"


class QuestionPlannerEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["question_bank", "fallback_catalog"]
    source_ref: dict[str, str] | None = None
    score: float | None = Field(default=None, ge=0, le=1)


class PlannedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    part: int = Field(ge=1, le=3)
    text: str = Field(min_length=1)
    topic: str | None = None
    timer_policy: dict[str, int]
    cue_card: dict[str, Any] | None = None
    linked_part2_question_id: str | None = None
    linked_part2_topic: str | None = None
    discussion_level: Literal["personal", "social", "abstract"] | None = None
    discussion_focus: str | None = None
    evidence: QuestionPlannerEvidence

    @field_validator("text", "question_id", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any) -> str:
        return _required_text(value)

    @field_validator("topic", "linked_part2_question_id", "linked_part2_topic", "discussion_focus", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _optional_text(value)


class QuestionPartPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part: int = Field(ge=1, le=3)
    title: str = Field(min_length=1)
    suggested_seconds: int = Field(gt=0)
    timebox_seconds: int = Field(gt=0)
    questions: list[PlannedQuestion] = Field(min_length=1)


class QuestionSetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_version: str = PLANNER_VERSION
    mode: SessionMode
    user_id: str = Field(min_length=1)
    season_id: str | None = None
    topic_ids: list[str] = Field(default_factory=list)
    target_parts: list[int] = Field(min_length=1)
    parts: list[QuestionPartPlan] = Field(min_length=1)
    fallback_used: bool = False
    rationale: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target_parts_have_questions(self) -> "QuestionSetPlan":
        planned_parts = {part.part for part in self.parts}
        missing = [part for part in self.target_parts if part not in planned_parts]
        if missing:
            raise ValueError(f"target parts missing from plan: {missing}")
        return self


class QuestionBankToolFactory(Protocol):
    def __call__(self) -> QuestionBankMcpTools:
        ...


class QuestionSetPlannerAgent:
    def __init__(
        self,
        question_bank_tools: QuestionBankMcpTools | None = None,
        *,
        part_counts: Mapping[int, int] | None = None,
    ) -> None:
        self.question_bank_tools = question_bank_tools
        self.part_counts = dict(part_counts or DEFAULT_PART_COUNTS)

    def plan(self, request: PlanRequest) -> QuestionSetPlan:
        target_parts = target_parts_for_request(request)
        parts: list[QuestionPartPlan] = []
        fallback_used = False
        rationale: list[str] = []
        part2_context: dict[str, str] | None = None

        for part in target_parts:
            requested_count = self.part_counts.get(part, 1)
            questions, used_fallback = self._plan_part_questions(
                request,
                part=part,
                requested_count=requested_count,
                linked_part2_context=part2_context,
            )
            fallback_used = fallback_used or used_fallback
            if used_fallback:
                rationale.append(f"Part {part} 使用内置题目兜底，后续可由 question-bank-mcp 替换。")
            else:
                rationale.append(f"Part {part} 已从 question-bank-mcp 规划题目。")
            if part == 2 and questions:
                part2_context = part2_link_context(questions[0])

            parts.append(
                QuestionPartPlan(
                    part=part,
                    title=f"Part {part}",
                    suggested_seconds=PART_TIMER_SECONDS[part],
                    timebox_seconds=PART_TIMEBOX_SECONDS[part],
                    questions=questions,
                )
            )

        return QuestionSetPlan(
            mode=request.mode,
            user_id=request.user_id,
            season_id=request.season_id,
            topic_ids=list(request.topic_ids),
            target_parts=target_parts,
            parts=parts,
            fallback_used=fallback_used,
            rationale=rationale,
        )

    def _plan_part_questions(
        self,
        request: PlanRequest,
        *,
        part: int,
        requested_count: int,
        linked_part2_context: dict[str, str] | None = None,
    ) -> tuple[list[PlannedQuestion], bool]:
        candidates: list[PlannedQuestion] = []
        if self.question_bank_tools is not None:
            candidates = self._retrieve_question_bank_candidates(
                request,
                part=part,
                top_k=min(max(requested_count * 8, 12), 20),
                linked_part2_context=linked_part2_context,
            )
        selected = select_distinct_questions(
            rank_candidates_for_session(candidates, request=request, part=part),
            requested_count=requested_count,
        )
        if len(selected) >= requested_count:
            return enrich_part3_questions(selected, linked_part2_context), False

        fallback = fallback_questions(part=part, request=request, linked_part2_context=linked_part2_context)
        selected = select_distinct_questions(
            [*selected, *rank_candidates_for_session(fallback, request=request, part=part, salt="fallback")],
            requested_count=requested_count,
        )
        return enrich_part3_questions(selected, linked_part2_context), True

    def _retrieve_question_bank_candidates(
        self,
        request: PlanRequest,
        *,
        part: int,
        top_k: int,
        linked_part2_context: dict[str, str] | None = None,
    ) -> list[PlannedQuestion]:
        context = McpToolContext(
            user_id=request.user_id,
            session_id=request.session_seed or f"planner:{request.user_id}",
            scopes=[QUESTION_BANK_READ_SCOPE],
            allowed_tools=QUESTION_BANK_PLANNER_TOOLS,
        )
        queries = build_search_queries(request, part=part, linked_part2_context=linked_part2_context)
        topic_id = topic_id_filter_for_request(request)
        topic = topic_filter_for_request(request)
        candidates: list[PlannedQuestion] = []
        if part == 3 and linked_part2_context:
            candidates.extend(followup_questions_for_context(self.question_bank_tools, context, linked_part2_context))
        for query in queries:
            try:
                result = self.question_bank_tools.search_questions(
                    context,
                    query=query,
                    active_season_id=request.season_id,
                    part=part,
                    topic=topic,
                    topic_id=topic_id,
                    top_k=top_k,
                )
            except (McpAuthorizationError, ValueError, KnowledgeServiceError):
                continue
            candidates.extend(planned_questions_from_search(result, cue_cards=cue_cards_for_result(self.question_bank_tools, context, result)))
        return candidates


def target_parts_for_request(request: PlanRequest) -> list[int]:
    if request.mode == "part_practice":
        return [request.part or 1]
    if request.mode == "topic_practice" and request.part:
        return [request.part]
    return [1, 2, 3]


def build_search_queries(
    request: PlanRequest,
    *,
    part: int,
    linked_part2_context: dict[str, str] | None = None,
) -> list[str]:
    topic_hint = " ".join(topic_terms_for_request(request)).strip()
    background_hint = " ".join(background_keywords_for_request(request, limit=5)).strip()
    mode_hint = request.mode.replace("_", " ")
    if part == 3 and linked_part2_context:
        part2_topic = linked_part2_context.get("topic") or linked_part2_context.get("prompt") or ""
        queries = [
            f"IELTS Speaking Part 3 social discussion about {part2_topic}".strip(),
            f"Part 3 abstract follow-up after Part 2 {part2_topic}".strip(),
        ]
        if background_hint:
            queries.append(f"IELTS Speaking Part 3 {part2_topic} {background_hint}".strip())
        return unique_texts(queries)
    if topic_hint:
        queries = [
            f"IELTS Speaking Part {part} {topic_hint}",
            f"{topic_hint} {mode_hint}",
        ]
        if background_hint:
            queries.append(f"IELTS Speaking Part {part} {topic_hint} {background_hint}")
        return unique_texts(queries)
    if background_hint:
        return unique_texts(
            [
                f"IELTS Speaking Part {part} {background_hint}",
                f"{mode_hint} Part {part} {background_hint}",
                f"IELTS Speaking Part {part} active season question",
            ]
        )
    return [f"IELTS Speaking Part {part} active season question", f"{mode_hint} Part {part}"]


def topic_terms_for_request(request: PlanRequest) -> list[str]:
    labels = [readable_topic_label(label) for label in request.topic_labels if _optional_text(label)]
    non_uuid_topics = [readable_topic_label(topic) for topic in request.topic_ids if not is_uuid_like(topic)]
    return unique_texts([*labels, *non_uuid_topics])


def topic_id_filter_for_request(request: PlanRequest) -> str | None:
    for topic_id in request.topic_ids:
        if is_uuid_like(topic_id):
            return topic_id
    return None


def topic_filter_for_request(request: PlanRequest) -> str | None:
    for topic in request.topic_ids:
        if not is_uuid_like(topic):
            return topic
    return None


def is_uuid_like(value: str) -> bool:
    return bool(UUID_RE.match(str(value).strip()))


def background_keywords_for_request(request: PlanRequest, *, limit: int) -> list[str]:
    background = request.user_background if isinstance(request.user_background, Mapping) else {}
    values: list[str] = []
    values.extend(background_fact_values(background.get("agent_facts")))
    values.extend(background_fact_values(background.get("facts")))
    values.extend(profile_values(background.get("profile")))
    values.extend(questionnaire_values(background.get("questionnaire")))

    keywords: list[str] = []
    seen: set[str] = set()
    for value in values:
        for token in WORD_RE.findall(value.lower()):
            if len(token) < 4 or token in seen:
                continue
            seen.add(token)
            keywords.append(token)
            if len(keywords) >= limit:
                return keywords
    return keywords


def background_fact_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        allowed_usage = item.get("allowed_usage")
        if isinstance(allowed_usage, list) and "question_personalization" not in allowed_usage:
            continue
        text = _optional_text(item.get("fact_value"))
        if text:
            values.append(text)
    return values


def profile_values(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    values: list[str] = []
    for key in ("display_name", "timezone", "preferred_exam_date"):
        text = _optional_text(value.get(key))
        if text:
            values.append(text)
    for key in ("target_band", "current_band"):
        if value.get(key) is not None:
            values.append(f"{key} {value.get(key)}")
    return values


def questionnaire_values(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    answers = value.get("answers")
    if isinstance(answers, str):
        return [answers]
    if not isinstance(answers, Mapping):
        return []
    return [_required_text(item) for item in answers.values() if _optional_text(item)]


def unique_texts(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = " ".join(str(value).split())
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def planned_questions_from_search(result: SearchQuestionsResult, *, cue_cards: Mapping[str, dict[str, Any]] | None = None) -> list[PlannedQuestion]:
    planned: list[PlannedQuestion] = []
    cue_cards = cue_cards or {}
    for item in result.results:
        question_text = extract_question_text(item.content)
        if is_placeholder_question_text(question_text):
            continue
        cue_card = cue_cards.get(item.question_id) if item.part == 2 else None
        if item.part == 2 and cue_card is None:
            cue_card = default_cue_card(question_text)
        planned.append(
            PlannedQuestion(
                question_id=item.question_id,
                part=item.part,
                text=question_text,
                topic=item.topic,
                timer_policy={"suggested_seconds": PART_TIMER_SECONDS[item.part]},
                cue_card=cue_card,
                evidence=QuestionPlannerEvidence(
                    source="question_bank",
                    source_ref=item.source_ref.model_dump(mode="json"),
                    score=item.score,
                ),
            )
        )
    return planned


def followup_questions_for_context(
    question_bank_tools: QuestionBankMcpTools,
    context: McpToolContext,
    linked_part2_context: Mapping[str, str],
) -> list[PlannedQuestion]:
    part2_question_id = _optional_text(linked_part2_context.get("question_id"))
    if part2_question_id is None:
        return []
    try:
        result = question_bank_tools.get_followup_templates(context, question_id=part2_question_id, part=3)
    except (McpAuthorizationError, ValueError, KnowledgeServiceError):
        return []

    planned: list[PlannedQuestion] = []
    linked_topic = _optional_text(linked_part2_context.get("topic"))
    for index, item in enumerate(result.followups):
        if is_placeholder_question_text(item.text):
            continue
        followup_id = _optional_text(item.followup_id) or f"{part2_question_id}:followup:{index + 1}"
        planned.append(
            PlannedQuestion(
                question_id=followup_id,
                part=3,
                text=item.text,
                topic=linked_topic,
                timer_policy={"suggested_seconds": PART_TIMER_SECONDS[3]},
                linked_part2_question_id=part2_question_id,
                linked_part2_topic=linked_topic,
                discussion_level="abstract",
                discussion_focus=discussion_focus_for_topic(linked_topic),
                evidence=QuestionPlannerEvidence(
                    source="question_bank",
                    source_ref=item.source_ref.model_dump(mode="json"),
                ),
            )
        )
    return planned


def cue_cards_for_result(
    question_bank_tools: QuestionBankMcpTools,
    context: McpToolContext,
    result: SearchQuestionsResult,
) -> dict[str, dict[str, Any]]:
    cue_cards: dict[str, dict[str, Any]] = {}
    for item in result.results:
        if item.part != 2 or not item.has_cue_card:
            continue
        try:
            cue_card = question_bank_tools.get_cue_card(context, question_id=item.question_id)
        except (McpAuthorizationError, ValueError, KnowledgeServiceError):
            continue
        if cue_card is None:
            continue
        cue_cards[item.question_id] = {
            "prompt": cue_card.prompt,
            "bullet_points": cue_card.bullet_points,
            "preparation_seconds": cue_card.preparation_seconds,
            "speaking_seconds": cue_card.speaking_seconds,
            "source_ref": cue_card.source_ref.model_dump(mode="json"),
        }
    return cue_cards


def extract_question_text(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("Question:"):
            return _required_text(stripped.removeprefix("Question:"))
    return _required_text(content.splitlines()[0] if content.splitlines() else content)


def select_distinct_questions(candidates: Sequence[PlannedQuestion], *, requested_count: int) -> list[PlannedQuestion]:
    selected: list[PlannedQuestion] = []
    selected_tokens: list[set[str]] = []
    seen_ids: set[str] = set()

    for candidate in candidates:
        if candidate.question_id in seen_ids:
            continue
        tokens = normalized_tokens(candidate.text)
        if any(is_highly_similar(tokens, existing) for existing in selected_tokens):
            continue
        selected.append(candidate)
        selected_tokens.append(tokens)
        seen_ids.add(candidate.question_id)
        if len(selected) >= requested_count:
            break

    return selected


def rank_candidates_for_session(
    candidates: Sequence[PlannedQuestion],
    *,
    request: PlanRequest,
    part: int,
    salt: str = "question_bank",
) -> list[PlannedQuestion]:
    if not request.session_seed:
        return list(candidates)

    seed = stable_seed(
        request.session_seed,
        request.user_id,
        request.mode,
        request.season_id or "",
        ",".join(request.topic_ids),
        ",".join(request.topic_labels),
        str(part),
        salt,
    )
    rng = Random(seed)
    decorated: list[tuple[float, float, int, PlannedQuestion]] = []
    for index, candidate in enumerate(candidates):
        score = candidate.evidence.score if candidate.evidence.score is not None else 0.65
        relevance_bucket = round(score / 0.05) * 0.05
        decorated.append((relevance_bucket, rng.random(), -index, candidate))
    decorated.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in decorated]


def stable_seed(*parts: str) -> int:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def fallback_questions(
    *,
    part: int,
    request: PlanRequest,
    linked_part2_context: dict[str, str] | None = None,
) -> list[PlannedQuestion]:
    catalog = TOPIC_FALLBACK_CATALOG if request.mode == "topic_practice" else FALLBACK_CATALOG
    raw_questions = part3_questions_for_context(request, linked_part2_context) if part == 3 else catalog[part]
    return [
        PlannedQuestion(
            question_id=f"planner_fallback_p{part}_q{index + 1}",
            part=part,
            text=fallback_question_text(item, request),
            topic=raw_question_topic(item, request),
            timer_policy={"suggested_seconds": PART_TIMER_SECONDS[part]},
            cue_card=default_cue_card(fallback_question_text(item, request)) if part == 2 else None,
            linked_part2_question_id=linked_part2_context.get("question_id") if part == 3 and linked_part2_context else None,
            linked_part2_topic=linked_part2_context.get("topic") if part == 3 and linked_part2_context else None,
            discussion_level=raw_question_discussion_level(item) if part == 3 else None,
            discussion_focus=raw_question_discussion_focus(item) if part == 3 else None,
            evidence=QuestionPlannerEvidence(source="fallback_catalog"),
        )
        for index, item in enumerate(raw_questions)
    ]


def default_cue_card(prompt: str) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "bullet_points": [
            "what it is",
            "when or where it happened",
            "who was involved",
            "why it was important to you",
        ],
        "preparation_seconds": 60,
        "speaking_seconds": PART_TIMER_SECONDS[2],
    }


def part2_link_context(question: PlannedQuestion) -> dict[str, str]:
    cue_card = question.cue_card or {}
    prompt = _optional_text(cue_card.get("prompt")) or question.text
    topic = question.topic or infer_topic_from_text(prompt)
    return {
        "question_id": question.question_id,
        "topic": topic,
        "prompt": prompt,
    }


def enrich_part3_questions(
    questions: Sequence[PlannedQuestion],
    linked_part2_context: dict[str, str] | None,
) -> list[PlannedQuestion]:
    if not linked_part2_context:
        return list(questions)
    enriched: list[PlannedQuestion] = []
    for question in questions:
        if question.part != 3:
            enriched.append(question)
            continue
        enriched.append(
            question.model_copy(
                update={
                    "linked_part2_question_id": question.linked_part2_question_id
                    or linked_part2_context.get("question_id"),
                    "linked_part2_topic": question.linked_part2_topic or linked_part2_context.get("topic"),
                    "discussion_level": question.discussion_level or "abstract",
                    "discussion_focus": question.discussion_focus or discussion_focus_for_topic(linked_part2_context.get("topic")),
                }
            )
        )
    return enriched


def first_topic(request: PlanRequest) -> str | None:
    terms = topic_terms_for_request(request)
    if terms:
        return terms[0]
    return request.topic_ids[0] if request.topic_ids else None


def raw_question_text(item: str | Mapping[str, str]) -> str:
    if isinstance(item, Mapping):
        return _required_text(item.get("text"))
    return _required_text(item)


def fallback_question_text(item: str | Mapping[str, str], request: PlanRequest) -> str:
    text = raw_question_text(item)
    if request.mode != "topic_practice":
        return text
    topic = first_topic(request) or "selected_topic"
    label = readable_topic_label(topic)
    return (
        text.replace("your selected topic", f"questions about {label}")
        .replace("this topic", label)
        .replace("selected topic", label)
    )


def raw_question_topic(item: str | Mapping[str, str], request: PlanRequest) -> str | None:
    if isinstance(item, Mapping):
        topic = _optional_text(item.get("topic"))
        if topic == "selected_topic":
            return first_topic(request) or topic
        return topic or first_topic(request)
    return first_topic(request)


def raw_question_discussion_level(item: str | Mapping[str, str]) -> Literal["personal", "social", "abstract"] | None:
    if isinstance(item, Mapping):
        value = _optional_text(item.get("discussion_level"))
        if value in {"personal", "social", "abstract"}:
            return value  # type: ignore[return-value]
    return "abstract"


def raw_question_discussion_focus(item: str | Mapping[str, str]) -> str | None:
    if isinstance(item, Mapping):
        return _optional_text(item.get("discussion_focus"))
    return None


def part3_questions_for_context(
    request: PlanRequest,
    linked_part2_context: dict[str, str] | None,
) -> list[dict[str, str]]:
    topic = first_topic(request) or (linked_part2_context or {}).get("topic")
    focus = discussion_focus_for_topic(topic)
    readable_topic = readable_topic_label(topic or focus)

    if focus == "public_places":
        return [
            {
                "topic": "public_places",
                "discussion_level": "social",
                "discussion_focus": focus,
                "text": "Why are public places important for people in a city?",
            },
            {
                "topic": "urban_planning",
                "discussion_level": "abstract",
                "discussion_focus": focus,
                "text": "How can local governments make cities more pleasant to live in?",
            },
            {
                "topic": "future_cities",
                "discussion_level": "abstract",
                "discussion_focus": focus,
                "text": "Do you think people's ideas about city life will change in the future?",
            },
        ]

    return [
        {
            "topic": topic or "selected_topic",
            "discussion_level": "social",
            "discussion_focus": focus,
            "text": f"Why do people have different opinions about {readable_topic}?",
        },
        {
            "topic": topic or "selected_topic",
            "discussion_level": "abstract",
            "discussion_focus": focus,
            "text": f"How might {readable_topic} influence people's lives in the future?",
        },
        {
            "topic": topic or "selected_topic",
            "discussion_level": "abstract",
            "discussion_focus": focus,
            "text": f"Should governments or communities pay more attention to {readable_topic}?",
        },
    ]


def infer_topic_from_text(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("city", "cities", "place", "public")):
        return "place"
    if any(word in lowered for word in ("work", "job", "study", "school")):
        return "work_or_study"
    if any(word in lowered for word in ("technology", "computer", "internet", "online")):
        return "technology"
    return "general_life"


def discussion_focus_for_topic(topic: str | None) -> str:
    normalized = (topic or "").lower()
    if any(word in normalized for word in ("place", "city", "urban", "community")):
        return "public_places"
    if any(word in normalized for word in ("work", "study", "school", "job")):
        return "education_and_work"
    if any(word in normalized for word in ("technology", "online", "internet")):
        return "technology_and_society"
    if "travel" in normalized:
        return "travel_and_culture"
    return "social_change"


def readable_topic_label(topic: str) -> str:
    cleaned = topic.removeprefix("topic_").replace("_", " ").strip()
    return cleaned or "this topic"


def normalized_tokens(text: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "about",
        "do",
        "does",
        "how",
        "in",
        "is",
        "of",
        "or",
        "the",
        "to",
        "what",
        "when",
        "where",
        "why",
        "you",
        "your",
    }
    return {word for word in WORD_RE.findall(text.lower()) if word not in stop_words}


def is_highly_similar(left: set[str], right: set[str]) -> bool:
    if not left or not right:
        return False
    intersection = len(left.intersection(right))
    union = len(left.union(right))
    return intersection / union >= 0.82


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError("required text is missing")
    return text


FALLBACK_CATALOG: dict[int, list[dict[str, str]]] = {
    1: [
        {"topic": "hometown", "text": "Let's talk about your hometown. Where is your hometown?"},
        {"topic": "hometown", "text": "What do you like most about your hometown?"},
        {"topic": "work_or_study", "text": "Do you work or are you a student?"},
        {"topic": "daily_routine", "text": "What do you usually do after work or study?"},
        {"topic": "free_time", "text": "What do you like doing in your free time?"},
    ],
    2: [
        {"topic": "place", "text": "Describe a place in your city that you enjoy visiting."},
    ],
    3: [
        {"topic": "city_life", "text": "Why do some people prefer living in big cities?"},
        {"topic": "city_life", "text": "How can cities become more comfortable for young people?"},
        {"topic": "future", "text": "Do you think city life will become easier in the future?"},
    ],
}

TOPIC_FALLBACK_CATALOG: dict[int, list[dict[str, str]]] = {
    1: [
        {"topic": "selected_topic", "text": "Let's practise your selected topic. How often does this topic come up in your daily life?"},
        {"topic": "selected_topic", "text": "What personal experience can you connect with this topic?"},
        {"topic": "selected_topic", "text": "Who do you usually talk to about this topic?"},
        {"topic": "selected_topic", "text": "Has your opinion about this topic changed over time?"},
    ],
    2: [
        {"topic": "selected_topic", "text": "Describe an experience related to your selected topic."},
    ],
    3: [
        {"topic": "selected_topic", "text": "Why do people have different opinions about this topic?"},
        {"topic": "selected_topic", "text": "How might this topic change in the future?"},
    ],
}
