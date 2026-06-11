from copy import deepcopy
from typing import Any

from app.agents.examiner_agent import ExaminerAgent, ExaminerTurnInput
from app.agents.followup_planner_agent import FollowupPlannerAgent, FollowupPlannerInput
from app.agents.question_planner_agent import QuestionSetPlannerAgent
from app.protocols.ag_ui_events import build_event, new_run_id
from app.protocols.schemas import AgentResponse, ConsumeAsrRequest, NextTurnRequest, PlanRequest
from app.workflows.exam_workflow import PART2_WARNING_SECONDS, PART_CONFIG
from app.workflows.mode_policy import allows_practice_hints, mode_policy_for, mode_policy_payload


TOPIC_GUIDANCE_CATALOG: dict[str, dict[str, list[str]]] = {
    "technology": {
        "vocabulary": ["digital tools", "online services", "privacy", "convenience"],
        "useful_expressions": ["It has changed the way people...", "One clear downside is..."],
        "feedback_focus": ["use precise tech nouns", "compare benefits and risks"],
    },
    "travel": {
        "vocabulary": ["itinerary", "local culture", "accommodation", "memorable experience"],
        "useful_expressions": ["What made the trip special was...", "It gave me a chance to..."],
        "feedback_focus": ["add concrete place details", "explain feelings and reasons"],
    },
    "hometown": {
        "vocabulary": ["neighbourhood", "local community", "public facilities", "pace of life"],
        "useful_expressions": ["What I like most about it is...", "Compared with larger cities..."],
        "feedback_focus": ["avoid generic place descriptions", "include personal examples"],
    },
    "city": {
        "vocabulary": ["public transport", "green spaces", "urban planning", "quality of life"],
        "useful_expressions": ["For city residents, this means...", "A practical improvement would be..."],
        "feedback_focus": ["connect personal examples to social discussion", "use topic-specific city vocabulary"],
    },
    "work": {
        "vocabulary": ["workload", "career path", "teamwork", "work-life balance"],
        "useful_expressions": ["In a professional setting...", "This skill is valuable because..."],
        "feedback_focus": ["separate work and study examples clearly", "explain responsibilities with detail"],
    },
}

DEFAULT_TOPIC_GUIDANCE = {
    "vocabulary": ["personal experience", "common situation", "long-term change", "different views"],
    "useful_expressions": ["From my experience...", "People may see this differently because..."],
    "feedback_focus": ["use one concrete example", "extend answers with reasons and comparisons"],
}


PRACTICE_HINTS: dict[int, list[str]] = {
    1: [
        "Answer in two or three natural sentences.",
        "Add one concrete personal detail instead of listing ideas.",
    ],
    2: [
        "Use the preparation minute to choose one clear story.",
        "Cover the cue-card points first, then add feelings or reasons.",
    ],
    3: [
        "Give a clear opinion, one reason, and one example.",
        "Compare two perspectives when the question asks about society or change.",
    ],
}

TOPIC_PRACTICE_QUESTIONS: dict[int, list[str]] = {
    1: [
        "Let's practise your selected topic. How often does this topic come up in your daily life?",
        "What personal experience can you connect with this topic?",
    ],
    2: [
        "Describe an experience related to your selected topic.",
    ],
    3: [
        "Why do people have different opinions about this topic?",
        "How might this topic change in the future?",
    ],
}


class PracticeWorkflow:
    def __init__(
        self,
        question_planner: QuestionSetPlannerAgent | None = None,
        examiner_agent: ExaminerAgent | None = None,
        followup_planner: FollowupPlannerAgent | None = None,
    ) -> None:
        self.question_planner = question_planner or QuestionSetPlannerAgent()
        self.examiner_agent = examiner_agent or ExaminerAgent()
        self.followup_planner = followup_planner or FollowupPlannerAgent()

    def plan(self, session_id: str, request: PlanRequest) -> AgentResponse:
        run_id = request.run_id_override or new_run_id()
        question_plan = self.question_planner.plan(request)
        target_parts = question_plan.target_parts
        first_part = target_parts[0]
        topic_guidance = build_topic_guidance(request.topic_ids, request.topic_labels) if request.mode == "topic_practice" else None
        state = {
            "session_id": session_id,
            "mode": request.mode,
            "status": "in_progress",
            "mode_policy": mode_policy_for(request.mode),
            "practice_mode": True,
            "user_id": request.user_id,
            "season_id": request.season_id,
            "topic_ids": request.topic_ids,
            "topic_labels": request.topic_labels,
            "session_seed": request.session_seed,
            "user_background": request.user_background,
            **({"topic_guidance": topic_guidance} if topic_guidance else {}),
            "question_plan": question_plan.model_dump(mode="json"),
            "target_parts": target_parts,
            "current_part": first_part,
            "question_index": 0,
            "part_elapsed_seconds": 0,
            "completed_parts": [],
            "answers": [],
        }

        events = [
            build_event(
                "session.started",
                session_id,
                run_id,
                {
                    "mode": request.mode,
                    "practice_mode": True,
                    **mode_policy_payload(state),
                    **self._topic_payload(state),
                },
            ),
            self._part_started_event(session_id, run_id, first_part, state),
        ]
        response = self._ask_current_question(session_id, run_id, state)
        response.events[0:0] = events
        return response

    def consume_asr(self, session_id: str, request: ConsumeAsrRequest) -> AgentResponse:
        run_id = request.run_id_override or new_run_id()
        state = self._state_for_asr(session_id, request)
        followup_plan = self._plan_followup(state, request)
        events = [
            build_event(
                "asr.final",
                session_id,
                run_id,
                {
                    "turn_id": request.turn_id,
                    "text": request.asr_text,
                    "audio_asset_id": request.audio_asset_id,
                    "confidence": request.asr_confidence,
                },
            ),
            build_event(
                "agent.followup_planned",
                session_id,
                run_id,
                {
                    "turn_id": request.turn_id,
                    "decision": followup_plan.decision.decision,
                    "reason": followup_plan.decision.reason,
                    "confidence": followup_plan.decision.confidence,
                    "word_count": followup_plan.word_count,
                    "privacy_guarded": followup_plan.privacy_guarded,
                    "practice_mode": True,
                    **mode_policy_payload(state),
                    **(
                        {"suggested_question": followup_plan.decision.suggested_question}
                        if followup_plan.decision.suggested_question
                        else {}
                    ),
                },
            ),
        ]
        state["last_turn_id"] = request.turn_id
        state["last_asr_text"] = request.asr_text
        state["last_followup_decision"] = followup_plan.decision.model_dump(mode="json", exclude_none=True)
        state["followup_count"] = int(state.get("followup_count") or 0)
        self._append_answer_record(state, request, followup_plan)

        if followup_plan.decision.decision == "ask_followup" and followup_plan.decision.suggested_question:
            state["followup_count"] += 1
            events.extend(self._followup_question_events(session_id, run_id, state, followup_plan.decision.suggested_question))

        return AgentResponse(run_id=run_id, events=events, state=state, next_action=followup_plan.next_action)

    def next_turn(self, session_id: str, request: NextTurnRequest) -> AgentResponse:
        run_id = request.run_id_override or new_run_id()
        state = deepcopy(request.session_state)
        self._ensure_state_defaults(state)
        state["question_index"] += 1
        state["followup_count"] = 0

        current_part = int(state["current_part"])
        if state["question_index"] < len(self._questions_for_state(state)):
            return self._ask_current_question(session_id, run_id, state)

        completed_parts = list(state.get("completed_parts") or [])
        completed_parts.append(current_part)
        state["completed_parts"] = completed_parts

        next_part = self._next_target_part(state)
        if next_part is None:
            state["status"] = "scoring"
            events = [
                build_event("part.completed", session_id, run_id, {"part": current_part}),
                build_event(
                    "session.completed",
                    session_id,
                    run_id,
                    {
                        "completed_parts": state["completed_parts"],
                        "practice_mode": True,
                        "status": "scoring",
                        **mode_policy_payload(state),
                        **self._topic_payload(state),
                    },
                ),
                build_event(
                    "scoring.started",
                    session_id,
                    run_id,
                    {
                        "run_reason": "practice_completed",
                        "completed_parts": state["completed_parts"],
                        "practice_mode": True,
                        "answer_count": len(state.get("answers") or []),
                        **mode_policy_payload(state),
                        **self._topic_payload(state),
                    },
                ),
            ]
            return AgentResponse(run_id=run_id, events=events, state=state, next_action="score_session")

        state["current_part"] = next_part
        state["question_index"] = 0
        state["part_elapsed_seconds"] = 0
        state["followup_count"] = 0
        events = [
            build_event("part.completed", session_id, run_id, {"part": current_part}),
            self._part_started_event(session_id, run_id, next_part, state),
        ]
        response = self._ask_current_question(session_id, run_id, state)
        response.events[0:0] = events
        return response

    def _ask_current_question(self, session_id: str, run_id: str, state: dict[str, Any]) -> AgentResponse:
        current_part = int(state["current_part"])
        suggested_seconds = self._suggested_seconds(state, current_part)
        utterance = self._build_examiner_utterance(state)
        payload: dict[str, Any] = {
            "part": current_part,
            "question_id": utterance.question_id,
            "text": utterance.text,
            "timer_policy": self._timer_policy_payload(state, current_part, suggested_seconds),
            "style_tags": utterance.style_tags,
            "practice_mode": True,
            "part_timebox_seconds": self._timebox_seconds(state, current_part),
            **mode_policy_payload(state),
            **self._part3_discussion_payload(self._current_planned_question(state)),
            **self._topic_payload(state),
        }
        if allows_practice_hints(state):
            payload["practice_hints"] = PRACTICE_HINTS[current_part]
        if current_part == 2:
            payload["cue_card"] = self._cue_card_payload(state)

        events = []
        if utterance.reasoning_text:
            events.append(
                build_event(
                    "examiner.thinking",
                    session_id,
                    run_id,
                    {
                        "part": utterance.part,
                        "question_id": utterance.question_id,
                        "text": utterance.reasoning_text,
                        "generated_by": utterance.generated_by,
                    },
                )
            )
        events.extend(
            [
                build_event("examiner.message", session_id, run_id, payload),
                build_event(
                    "timer.started",
                    session_id,
                    run_id,
                    {
                        "part": current_part,
                        "suggested_seconds": suggested_seconds,
                        "timebox_seconds": self._timebox_seconds(state, current_part),
                        "practice_mode": True,
                        **mode_policy_payload(state),
                        **self._part2_timer_fields(state, current_part),
                    },
                ),
            ]
        )
        return AgentResponse(run_id=run_id, events=events, state=state, next_action="wait_for_user_answer")

    def _build_examiner_utterance(self, state: dict[str, Any]):
        current_part = int(state["current_part"])
        questions = self._questions_for_state(state)
        question_index = int(state["question_index"])
        question = questions[question_index]
        return self.examiner_agent.build_turn(
            ExaminerTurnInput(
                mode=state.get("mode", "part_practice"),
                part=current_part,
                question_id=question["question_id"],
                question_text=question["text"],
                question_index=question_index,
                total_questions=len(questions),
                practice_mode=True,
            )
        )

    def _part_started_event(self, session_id: str, run_id: str, part: int, state: dict[str, Any]):
        part_plan = self._part_plan(state, part)
        payload: dict[str, Any] = {
            "part": part,
            "title": part_plan.get("title", PART_CONFIG[part]["title"]),
            "timebox_seconds": self._timebox_seconds(state, part),
            "practice_mode": True,
            **mode_policy_payload(state),
            **self._part2_part_fields(state, part),
            **self._topic_payload(state),
        }
        if allows_practice_hints(state):
            payload["practice_hints"] = PRACTICE_HINTS[part]
        if part == 3:
            questions = part_plan.get("questions") or []
            if questions:
                payload.update(self._part3_discussion_payload(questions[0]))
        return build_event("part.started", session_id, run_id, payload)

    def _target_parts(self, request: PlanRequest) -> list[int]:
        if request.mode == "part_practice":
            return [request.part or 1]
        if request.mode == "topic_practice" and request.part:
            return [request.part]
        return [1, 2, 3]

    def _ensure_state_defaults(self, state: dict[str, Any]) -> None:
        current_part = int(state.get("current_part") or 1)
        state.setdefault("mode", "part_practice")
        state.setdefault("mode_policy", mode_policy_for(str(state.get("mode") or "part_practice")))
        state.setdefault("practice_mode", True)
        state.setdefault("target_parts", [current_part])
        state.setdefault("question_index", 0)
        state.setdefault("completed_parts", [])
        state.setdefault("topic_ids", [])
        if state.get("mode") == "topic_practice" and "topic_guidance" not in state:
            state["topic_guidance"] = build_topic_guidance(list(state.get("topic_ids") or []))
        state.setdefault("part_elapsed_seconds", 0)
        state.setdefault("followup_count", 0)
        state.setdefault("answers", [])
        state.setdefault("status", "in_progress")

    def _next_target_part(self, state: dict[str, Any]) -> int | None:
        target_parts = [int(part) for part in state.get("target_parts", [])]
        completed = {int(part) for part in state.get("completed_parts", [])}
        for part in target_parts:
            if part not in completed:
                return part
        return None

    def _questions_for_state(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        current_part = int(state["current_part"])
        return list(self._part_plan(state, current_part)["questions"])

    def _current_planned_question(self, state: dict[str, Any]) -> dict[str, Any]:
        index = int(state["question_index"])
        return self._questions_for_state(state)[index]

    def _current_question(self, state: dict[str, Any]) -> str:
        index = int(state["question_index"])
        return self._questions_for_state(state)[index]["text"]

    def _question_id(self, state: dict[str, Any]) -> str:
        index = int(state["question_index"])
        return self._questions_for_state(state)[index]["question_id"]

    def _cue_card_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        index = int(state["question_index"])
        planned = self._questions_for_state(state)[index]
        cue_card = planned.get("cue_card")
        if isinstance(cue_card, dict):
            return cue_card
        return {
            "prompt": planned["text"],
            "bullet_points": ["what it is", "when or where it happened", "who was involved", "why it was important to you"],
            "preparation_seconds": 60,
            "speaking_seconds": self._suggested_seconds(state, 2),
        }

    def _timer_policy_payload(self, state: dict[str, Any], part: int, suggested_seconds: int) -> dict[str, Any]:
        payload: dict[str, Any] = {"suggested_seconds": suggested_seconds}
        if part == 2:
            payload.update(self._part2_timer_fields(state, part, include_phase=False))
        return payload

    def _part2_part_fields(self, state: dict[str, Any], part: int) -> dict[str, Any]:
        if part != 2:
            return {}
        cue_card = self._cue_card_payload(state)
        return {
            "preparation_seconds": int(cue_card.get("preparation_seconds") or 60),
            "speaking_seconds": int(cue_card.get("speaking_seconds") or self._suggested_seconds(state, 2)),
            "warning_seconds": PART2_WARNING_SECONDS,
        }

    def _part2_timer_fields(self, state: dict[str, Any], part: int, *, include_phase: bool = True) -> dict[str, Any]:
        if part != 2:
            return {}
        fields = dict(self._part2_part_fields(state, part))
        if include_phase:
            fields["phase"] = "prepare_then_speak"
        return fields

    def _part3_discussion_payload(self, question: dict[str, Any]) -> dict[str, Any]:
        if int(question.get("part") or 0) != 3:
            return {}
        payload: dict[str, Any] = {
            "discussion_level": question.get("discussion_level") or "abstract",
            "discussion_focus": question.get("discussion_focus") or "social_change",
        }
        if question.get("linked_part2_question_id"):
            payload["linked_part2_question_id"] = question["linked_part2_question_id"]
        if question.get("linked_part2_topic"):
            payload["linked_part2_topic"] = question["linked_part2_topic"]
        return payload

    def _suggested_seconds(self, state: dict[str, Any], part: int) -> int:
        part_plan = self._part_plan(state, part)
        return int(part_plan.get("suggested_seconds") or PART_CONFIG[part]["suggested_seconds"])

    def _timebox_seconds(self, state: dict[str, Any], part: int) -> int:
        part_plan = self._part_plan(state, part)
        return int(part_plan.get("timebox_seconds") or (300 if part in {1, 3} else 180))

    def _part_plan(self, state: dict[str, Any], part: int) -> dict[str, Any]:
        question_plan = state.get("question_plan")
        if isinstance(question_plan, dict):
            for item in question_plan.get("parts", []):
                if int(item.get("part") or 0) == part:
                    return item
        questions = TOPIC_PRACTICE_QUESTIONS[part] if state.get("mode") == "topic_practice" else PART_CONFIG[part]["questions"]
        prefix = "topic" if state.get("mode") == "topic_practice" else "part"
        return {
            "part": part,
            "title": PART_CONFIG[part]["title"],
            "suggested_seconds": PART_CONFIG[part]["suggested_seconds"],
            "timebox_seconds": 300 if part in {1, 3} else 180,
            "questions": [
                {
                    "question_id": f"practice_{prefix}_p{part}_q{index + 1}",
                    "part": part,
                    "text": question,
                    "timer_policy": {"suggested_seconds": PART_CONFIG[part]["suggested_seconds"]},
                }
                for index, question in enumerate(questions)
            ],
        }

    def _state_for_asr(self, session_id: str, request: ConsumeAsrRequest) -> dict[str, Any]:
        state = deepcopy(request.session_state)
        state.setdefault("session_id", session_id)
        state.setdefault("mode", "part_practice")
        state.setdefault("mode_policy", mode_policy_for(str(state.get("mode") or "part_practice")))
        state.setdefault("practice_mode", True)
        state.setdefault("current_part", 1)
        state.setdefault("question_index", 0)
        state.setdefault("completed_parts", [])
        state.setdefault("topic_ids", [])
        if state.get("mode") == "topic_practice" and "topic_guidance" not in state:
            state["topic_guidance"] = build_topic_guidance(list(state.get("topic_ids") or []))
        state.setdefault("followup_count", 0)
        state.setdefault("part_elapsed_seconds", 0)
        state.setdefault("answers", [])
        state.setdefault("status", "in_progress")
        return state

    def _plan_followup(self, state: dict[str, Any], request: ConsumeAsrRequest):
        current_part = int(state.get("current_part") or 1)
        question_text = None
        try:
            question_text = self._current_question(state)
        except (KeyError, IndexError, TypeError, ValueError):
            question_text = None
        return self.followup_planner.plan(
            FollowupPlannerInput(
                mode=state.get("mode", "part_practice"),
                part=current_part,
                asr_text=request.asr_text,
                question_text=question_text,
                question_index=int(state.get("question_index") or 0),
                followup_count=int(state.get("followup_count") or 0),
            )
        )

    def _append_answer_record(self, state: dict[str, Any], request: ConsumeAsrRequest, followup_plan) -> None:
        answers = list(state.get("answers") or [])
        current_part = int(state.get("current_part") or 1)
        question_index = int(state.get("question_index") or 0)
        try:
            question = self._questions_for_state(state)[question_index]
        except (KeyError, IndexError, TypeError, ValueError):
            question = {}
        answers.append(
            {
                "turn_id": request.turn_id,
                "part": current_part,
                "question_index": question_index,
                "question_id": question.get("question_id"),
                "question_text": question.get("text"),
                "asr_text": request.asr_text,
                "audio_asset_id": request.audio_asset_id,
                "asr_confidence": request.asr_confidence,
                "followup_decision": followup_plan.decision.decision,
                "practice_mode": True,
                "mode_policy": state.get("mode_policy"),
                **self._topic_payload(state),
            }
        )
        state["answers"] = answers

    def _followup_question_events(self, session_id: str, run_id: str, state: dict[str, Any], suggested_question: str):
        current_part = int(state.get("current_part") or 1)
        question_id = f"followup_{state.get('last_turn_id', 'turn')}_{state['followup_count']}"
        payload: dict[str, Any] = {
            "part": current_part,
            "question_id": question_id,
            "text": suggested_question,
            "timer_policy": {"suggested_seconds": self._suggested_seconds(state, current_part)},
            "style_tags": ["followup", f"part_{current_part}", "practice"],
            "practice_mode": True,
            "part_timebox_seconds": self._timebox_seconds(state, current_part),
            **mode_policy_payload(state),
            **self._part3_discussion_payload(self._current_planned_question(state)),
            **self._topic_payload(state),
        }
        if allows_practice_hints(state):
            payload["practice_hints"] = PRACTICE_HINTS[current_part]
        return [
            build_event("examiner.message", session_id, run_id, payload),
            build_event(
                "timer.started",
                session_id,
                run_id,
                {
                    "part": current_part,
                    "suggested_seconds": self._suggested_seconds(state, current_part),
                    "timebox_seconds": self._timebox_seconds(state, current_part),
                    "practice_mode": True,
                    **mode_policy_payload(state),
                    **self._part2_timer_fields(state, current_part),
                },
            ),
        ]

    def _topic_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("mode") != "topic_practice":
            return {}
        topic_ids = list(state.get("topic_ids") or [])
        payload: dict[str, Any] = {"topic_ids": topic_ids}
        guidance = state.get("topic_guidance")
        if isinstance(guidance, dict):
            payload["topic_guidance"] = guidance
        return payload


def build_topic_guidance(topic_ids: list[str], topic_labels: list[str] | None = None) -> dict[str, Any]:
    primary_topic = (topic_labels or topic_ids or ["general_life"])[0]
    key = normalize_topic_key(primary_topic)
    catalog = TOPIC_GUIDANCE_CATALOG.get(key, DEFAULT_TOPIC_GUIDANCE)
    return {
        "topic_ids": list(topic_ids),
        "topic_labels": list(topic_labels or []),
        "primary_topic": primary_topic,
        "topic_label": readable_topic_label(primary_topic),
        "vocabulary": catalog["vocabulary"],
        "useful_expressions": catalog["useful_expressions"],
        "feedback_focus": catalog["feedback_focus"],
    }


def normalize_topic_key(topic: str) -> str:
    normalized = readable_topic_label(topic).lower()
    if any(word in normalized for word in ("tech", "internet", "online", "digital")):
        return "technology"
    if any(word in normalized for word in ("travel", "trip", "journey")):
        return "travel"
    if any(word in normalized for word in ("hometown", "home town")):
        return "hometown"
    if any(word in normalized for word in ("city", "urban", "place")):
        return "city"
    if any(word in normalized for word in ("work", "job", "career", "study", "school")):
        return "work"
    return normalized


def readable_topic_label(topic: str) -> str:
    cleaned = topic.removeprefix("topic_").replace("_", " ").strip()
    return cleaned or "general life"
