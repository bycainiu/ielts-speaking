from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.protocols.schemas import SessionMode


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationTurn(StrictModel):
    turn_id: str
    role: Literal["examiner", "candidate"]
    part: int = Field(ge=1, le=3)
    text: str
    question_id: str | None = None
    metrics: dict[str, Any] | None = None


class RunningAssessment(StrictModel):
    estimated_band: float | None = None
    fluency_indicators: dict[str, float] = Field(default_factory=dict)
    vocabulary_breadth: float | None = None
    weak_areas: list[str] = Field(default_factory=list)
    strong_areas: list[str] = Field(default_factory=list)
    turn_count: int = 0


class ExamConstraints(StrictModel):
    max_questions_per_part: dict[int, int] = Field(default_factory=lambda: {1: 10, 2: 1, 3: 5})
    max_followups_per_question: int = 2
    part_timebox_seconds: dict[int, int] = Field(default_factory=lambda: {1: 300, 2: 180, 3: 300})
    max_total_seconds: int = 900
    forbidden_topics: list[str] = Field(default_factory=list)


class SessionContext(StrictModel):
    session_id: str
    mode: SessionMode
    current_part: int = Field(default=1, ge=1, le=3)
    question_index: int = Field(default=0, ge=0)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    running_assessment: RunningAssessment = Field(default_factory=RunningAssessment)
    exam_constraints: ExamConstraints = Field(default_factory=ExamConstraints)
    question_plan: dict[str, Any] | None = None


# Director -> Specialist
TASK_PLAN_QUESTIONS = "task.plan_questions"
TASK_DELIVER_QUESTION = "task.deliver_question"
TASK_ANALYZE_RESPONSE = "task.analyze_response"
TASK_DECIDE_FOLLOWUP = "task.decide_followup"
TASK_SCORE_SESSION = "task.score_session"

# Specialist -> Director
RESULT_QUESTIONS_PLANNED = "result.questions_planned"
RESULT_EXAMINER_UTTERANCE = "result.examiner_utterance"
RESULT_RESPONSE_ANALYSIS = "result.response_analysis"
RESULT_FOLLOWUP_DECISION = "result.followup_decision"
RESULT_SCORE_REPORT = "result.score_report"

# Specialist <-> Specialist
INFO_INTERIM_ASSESSMENT = "info.interim_assessment"
REQUEST_ADJUST_QUESTIONS = "request.adjust_questions"
INFO_TOPIC_SHIFT = "info.topic_shift"

AgentMessageType = Literal[
    "task.plan_questions",
    "task.deliver_question",
    "task.analyze_response",
    "task.decide_followup",
    "task.score_session",
    "result.questions_planned",
    "result.examiner_utterance",
    "result.response_analysis",
    "result.followup_decision",
    "result.score_report",
    "info.interim_assessment",
    "request.adjust_questions",
    "info.topic_shift",
]

ALL_AGENT_MESSAGE_TYPES: frozenset[str] = frozenset(
    {
        TASK_PLAN_QUESTIONS,
        TASK_DELIVER_QUESTION,
        TASK_ANALYZE_RESPONSE,
        TASK_DECIDE_FOLLOWUP,
        TASK_SCORE_SESSION,
        RESULT_QUESTIONS_PLANNED,
        RESULT_EXAMINER_UTTERANCE,
        RESULT_RESPONSE_ANALYSIS,
        RESULT_FOLLOWUP_DECISION,
        RESULT_SCORE_REPORT,
        INFO_INTERIM_ASSESSMENT,
        REQUEST_ADJUST_QUESTIONS,
        INFO_TOPIC_SHIFT,
    }
)


class AgentMessage(StrictModel):
    message_id: str
    run_id: str
    session_id: str
    source_agent: str
    target_agent: str
    message_type: AgentMessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    reply_to: str | None = None
    context: SessionContext
    trace_metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def default_exam_constraints() -> ExamConstraints:
    return ExamConstraints()
