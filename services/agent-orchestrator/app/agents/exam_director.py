from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.protocols.agent_message import (
    AgentMessage,
    TASK_ANALYZE_RESPONSE,
    TASK_DECIDE_FOLLOWUP,
    TASK_DELIVER_QUESTION,
    TASK_PLAN_QUESTIONS,
    TASK_SCORE_SESSION,
    SessionContext,
    default_exam_constraints,
)
from app.protocols.message_bus import InMemoryMessageBus, MessageBusTimeoutError
from app.protocols.schemas import (
    AgentResponse,
    ConsumeAsrRequest,
    NextAction,
    NextTurnRequest,
    PlanRequest,
    ScoreSessionRequest,
    SessionMode,
)
from app.protocols.session_event import build_session_event
from app.observability.trace import OrchestratorTraceRecorder
from app.rules.fallback_plan import build_fallback_question_plan
from app.rules.session_payload import (
    examiner_message_payload,
    part_started_payload,
    timer_started_payload,
)
from app.safety.exam_constraints import ExamConstraintViolation, validate_followup, validate_question_plan


def _mode_policy(mode: SessionMode) -> dict[str, Any]:
    if mode == "full_exam":
        return {
            "prompt_profile": "examiner_exam",
            "allow_structure_suggestions": False,
            "allow_chinese_hints": False,
        }
    return {
        "prompt_profile": "examiner_practice",
        "allow_structure_suggestions": True,
        "allow_chinese_hints": True,
    }


def _build_session_context(session_id: str, request: PlanRequest) -> SessionContext:
    return SessionContext(
        session_id=session_id,
        mode=request.mode,
        current_part=request.part or 1,
        user_profile=dict(request.user_background),
        exam_constraints=default_exam_constraints(),
    )


def _initial_state(session_id: str, request: PlanRequest, question_plan: dict[str, Any]) -> dict[str, Any]:
    first_question = question_plan["parts"][0]["questions"][0]
    return {
        "session_id": session_id,
        "mode": request.mode,
        "status": "in_progress",
        "current_part": 1,
        "question_index": 0,
        "followup_count": 0,
        "question_plan": question_plan,
        "current_question_id": first_question["question_id"],
        "current_question_text": first_question.get("text") or first_question.get("topic"),
        "mode_policy": _mode_policy(request.mode),
        "orchestrator_version": "phase2_multi_agent",
    }


class ExamDirector:
    def __init__(
        self,
        message_bus: InMemoryMessageBus,
        *,
        agent_timeout: float = 30.0,
        trace_recorder: OrchestratorTraceRecorder | None = None,
    ) -> None:
        self._bus = message_bus
        self._trace = trace_recorder
        self._agent_timeout = agent_timeout

    def _publish_route(self, *, run_id: str, session_id: str, target_agent: str, route: str, part: int | None = None) -> None:
        if self._trace is None:
            return
        self._trace.stream_broker.publish(
            run_id=run_id,
            session_id=session_id,
            kind="director.route_change",
            phase="exam_director",
            payload={
                "agent": "exam_director",
                "target": target_agent,
                "route": route,
                **({"part": part} if part is not None else {}),
            },
        )

    def _build_delivery_events(
        self,
        *,
        session_id: str,
        run_id: str,
        part: int,
        question: dict[str, Any],
        part_plan: dict[str, Any] | None,
        examiner_text: str,
        source: str | None,
        include_part_started: bool,
        created_at: datetime,
    ) -> list[Any]:
        events = []
        if include_part_started:
            events.append(
                build_session_event(
                    event_type="part.started",
                    session_id=session_id,
                    run_id=run_id,
                    payload=part_started_payload(part=part, part_plan=part_plan, question=question),
                    created_at=created_at,
                )
            )
        message_payload = examiner_message_payload(
            part=part,
            question=question,
            examiner_text=examiner_text,
            source=source,
        )
        events.append(
            build_session_event(
                event_type="examiner.message",
                session_id=session_id,
                run_id=run_id,
                payload=message_payload,
                created_at=created_at,
            )
        )
        timer_policy = message_payload.get("timer_policy") or {}
        suggested_seconds = timer_policy.get("suggested_seconds") or timer_policy.get("preparation_seconds")
        events.append(
            build_session_event(
                event_type="timer.started",
                session_id=session_id,
                run_id=run_id,
                payload=timer_started_payload(
                    part=part,
                    question=question,
                    suggested_seconds=int(suggested_seconds) if suggested_seconds is not None else None,
                ),
                created_at=created_at,
            )
        )
        return events

    async def handle_plan(self, session_id: str, request: PlanRequest, *, run_id: str) -> AgentResponse:
        context = _build_session_context(session_id, request)
        self._publish_route(
            run_id=run_id,
            session_id=session_id,
            target_agent="question_strategist",
            route="plan_questions",
            part=context.current_part,
        )
        try:
            plan_reply = await self._bus.request(
                AgentMessage(
                    message_id=f"msg_{uuid4().hex}",
                    run_id=run_id,
                    session_id=session_id,
                    source_agent="exam_director",
                    target_agent="question_strategist",
                    message_type=TASK_PLAN_QUESTIONS,
                    payload={"plan_request": request.model_dump(mode="json")},
                    context=context,
                ),
                timeout=self._agent_timeout,
            )
            question_plan = plan_reply.payload["question_plan"]
            validate_question_plan(context, question_plan)
        except (MessageBusTimeoutError, ExamConstraintViolation, KeyError):
            question_plan = build_fallback_question_plan(request)

        context = context.model_copy(update={"question_plan": question_plan})
        first_question = question_plan["parts"][0]["questions"][0]
        part_plan = question_plan["parts"][0]
        self._publish_route(
            run_id=run_id,
            session_id=session_id,
            target_agent="live_examiner",
            route="deliver_question",
            part=1,
        )
        utterance_reply = await self._bus.request(
            AgentMessage(
                message_id=f"msg_{uuid4().hex}",
                run_id=run_id,
                session_id=session_id,
                source_agent="exam_director",
                target_agent="live_examiner",
                message_type=TASK_DELIVER_QUESTION,
                payload={
                    "question": first_question,
                    "part": 1,
                    "question_index": 0,
                },
                context=context,
            ),
            timeout=self._agent_timeout,
        )
        examiner_text = utterance_reply.payload["text"]
        now = datetime.now(UTC)
        events = [
            build_session_event(
                event_type="session.started",
                session_id=session_id,
                run_id=run_id,
                payload={"mode": request.mode},
                created_at=now,
            ),
            *self._build_delivery_events(
                session_id=session_id,
                run_id=run_id,
                part=1,
                question=first_question,
                part_plan=part_plan,
                examiner_text=examiner_text,
                source=utterance_reply.payload.get("source", "live_examiner"),
                include_part_started=True,
                created_at=now,
            ),
        ]
        return AgentResponse(
            run_id=run_id,
            events=events,
            state=_initial_state(session_id, request, question_plan),
            next_action="wait_for_user_answer",
        )

    async def handle_consume_asr(self, session_id: str, request: ConsumeAsrRequest, *, run_id: str) -> AgentResponse:
        state = dict(request.session_state)
        state.setdefault("answers", []).append(
            {
                "turn_id": request.turn_id,
                "asr_text": request.asr_text,
                "audio_asset_id": request.audio_asset_id,
                "asr_confidence": request.asr_confidence,
            }
        )
        context = _session_context_from_state(session_id, state)
        part = int(state.get("current_part") or 1)
        followup_count = int(state.get("followup_count") or 0)

        self._publish_route(
            run_id=run_id,
            session_id=session_id,
            target_agent="response_analyzer",
            route="analyze_response",
            part=part,
        )
        analyze_reply = await self._bus.request(
            AgentMessage(
                message_id=f"msg_{uuid4().hex}",
                run_id=run_id,
                session_id=session_id,
                source_agent="exam_director",
                target_agent="response_analyzer",
                message_type=TASK_ANALYZE_RESPONSE,
                payload={"asr_text": request.asr_text, "part": part, "turn_id": request.turn_id},
                context=context,
            ),
            timeout=self._agent_timeout,
        )
        interim = analyze_reply.payload.get("assessment") or {}

        self._publish_route(
            run_id=run_id,
            session_id=session_id,
            target_agent="live_examiner",
            route="decide_followup",
            part=part,
        )
        followup_reply = await self._bus.request(
            AgentMessage(
                message_id=f"msg_{uuid4().hex}",
                run_id=run_id,
                session_id=session_id,
                source_agent="exam_director",
                target_agent="live_examiner",
                message_type=TASK_DECIDE_FOLLOWUP,
                payload={
                    "asr_text": request.asr_text,
                    "part": part,
                    "followup_count": followup_count,
                    "interim_assessment": interim,
                },
                context=context,
            ),
            timeout=self._agent_timeout,
        )

        now = datetime.now(UTC)
        events = [
            build_session_event(
                event_type="user.answer_committed",
                session_id=session_id,
                run_id=run_id,
                payload={"turn_id": request.turn_id, "asr_text": request.asr_text},
                created_at=now,
            ),
            build_session_event(
                event_type="asr.final",
                session_id=session_id,
                run_id=run_id,
                payload={"turn_id": request.turn_id, "text": request.asr_text},
                created_at=now,
            ),
        ]

        ask_followup = bool(followup_reply.payload.get("ask_followup"))
        followup_text = followup_reply.payload.get("followup_text")
        next_action: NextAction = "ask_next_question"

        if ask_followup and followup_text:
            try:
                validate_followup(context, followup_count + 1)
                state["followup_count"] = followup_count + 1
                events.extend(
                    [
                        build_session_event(
                            event_type="agent.followup_planned",
                            session_id=session_id,
                            run_id=run_id,
                            payload={"text": followup_text},
                            created_at=now,
                        ),
                        build_session_event(
                            event_type="examiner.message",
                            session_id=session_id,
                            run_id=run_id,
                            payload={
                                "part": part,
                                "question_id": state.get("current_question_id"),
                                "text": followup_text,
                                "is_followup": True,
                            },
                            created_at=now,
                        ),
                    ]
                )
                next_action = "wait_for_user_answer"
            except ExamConstraintViolation:
                state["followup_count"] = 0
        else:
            state["followup_count"] = 0

        state["status"] = "in_progress"
        state["last_interim_assessment"] = interim
        return AgentResponse(run_id=run_id, events=events, state=state, next_action=next_action)

    async def handle_next_turn(self, session_id: str, request: NextTurnRequest, *, run_id: str) -> AgentResponse:
        state = dict(request.session_state)
        question_plan = state.get("question_plan") or {}
        parts = question_plan.get("parts") or []
        current_part = int(state.get("current_part") or 1)
        question_index = int(state.get("question_index") or 0) + 1
        context = _session_context_from_state(session_id, state)

        part_entry = next((item for item in parts if item.get("part") == current_part), None)
        questions = (part_entry or {}).get("questions") or []
        if question_index >= len(questions):
            if current_part >= 3 or len(parts) <= 1:
                state["status"] = "ready_to_score"
                return AgentResponse(
                    run_id=run_id,
                    events=[
                        build_session_event(
                            event_type="part.completed",
                            session_id=session_id,
                            run_id=run_id,
                            payload={"part": current_part},
                        )
                    ],
                    state=state,
                    next_action="score_session",
                )
            current_part += 1
            question_index = 0
            part_entry = next((item for item in parts if item.get("part") == current_part), parts[-1])
            questions = part_entry.get("questions") or []

        question = questions[question_index]
        context = context.model_copy(update={"current_part": current_part, "question_index": question_index})
        self._publish_route(
            run_id=run_id,
            session_id=session_id,
            target_agent="live_examiner",
            route="deliver_question",
            part=current_part,
        )
        utterance_reply = await self._bus.request(
            AgentMessage(
                message_id=f"msg_{uuid4().hex}",
                run_id=run_id,
                session_id=session_id,
                source_agent="exam_director",
                target_agent="live_examiner",
                message_type=TASK_DELIVER_QUESTION,
                payload={
                    "question": question,
                    "part": current_part,
                    "question_index": question_index,
                },
                context=context,
            ),
            timeout=self._agent_timeout,
        )
        examiner_text = utterance_reply.payload["text"]
        state.update(
            {
                "current_part": current_part,
                "question_index": question_index,
                "current_question_id": question.get("question_id"),
                "current_question_text": examiner_text,
                "followup_count": 0,
                "status": "in_progress",
            }
        )
        now = datetime.now(UTC)
        events = self._build_delivery_events(
            session_id=session_id,
            run_id=run_id,
            part=current_part,
            question=question,
            part_plan=part_entry,
            examiner_text=examiner_text,
            source=utterance_reply.payload.get("source", "live_examiner"),
            include_part_started=question_index == 0,
            created_at=now,
        )
        return AgentResponse(run_id=run_id, events=events, state=state, next_action="wait_for_user_answer")

    async def handle_score(self, session_id: str, request: ScoreSessionRequest, *, run_id: str) -> AgentResponse:
        state = dict(request.session_state)
        context = _session_context_from_state(session_id, state)
        score_reply = await self._bus.request(
            AgentMessage(
                message_id=f"msg_{uuid4().hex}",
                run_id=run_id,
                session_id=session_id,
                source_agent="exam_director",
                target_agent="response_analyzer",
                message_type=TASK_SCORE_SESSION,
                payload={"session_state": state},
                context=context,
            ),
            timeout=self._agent_timeout,
        )
        report = score_reply.payload.get("report") or {}
        state["status"] = "completed"
        state["score_report"] = report
        events = [
            build_session_event(
                event_type="scoring.started",
                session_id=session_id,
                run_id=run_id,
                payload={},
            ),
            build_session_event(
                event_type="report.ready",
                session_id=session_id,
                run_id=run_id,
                payload={"report": report},
            ),
            build_session_event(
                event_type="session.completed",
                session_id=session_id,
                run_id=run_id,
                payload={"overall_band": report.get("overall_band")},
            ),
        ]
        return AgentResponse(run_id=run_id, events=events, state=state, next_action="finish_session")


def _session_context_from_state(session_id: str, state: dict[str, Any]) -> SessionContext:
    return SessionContext(
        session_id=session_id,
        mode=state.get("mode") or "full_exam",
        current_part=int(state.get("current_part") or 1),
        question_index=int(state.get("question_index") or 0),
        user_profile=dict(state.get("user_profile") or {}),
        question_plan=state.get("question_plan"),
        exam_constraints=default_exam_constraints(),
    )
