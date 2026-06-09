from copy import deepcopy

from app.agents.examiner_agent import ExaminerAgent, ExaminerTurnInput
from app.agents.followup_planner_agent import FollowupPlannerAgent, FollowupPlannerInput
from app.agents.question_planner_agent import QuestionSetPlannerAgent
from app.protocols.ag_ui_events import build_event, new_run_id
from app.protocols.schemas import AgentResponse, ConsumeAsrRequest, NextTurnRequest, PlanRequest
from app.workflows.mode_policy import mode_policy_for, mode_policy_payload


PART2_WARNING_SECONDS = [60, 30, 10]


PART_CONFIG = {
    1: {
        "title": "Part 1",
        "suggested_seconds": 30,
        "questions": [
            "Let's talk about your hometown. Where is your hometown?",
            "What do you like most about your hometown?",
        ],
    },
    2: {
        "title": "Part 2",
        "suggested_seconds": 120,
        "questions": [
            "Describe a place in your city that you enjoy visiting.",
        ],
    },
    3: {
        "title": "Part 3",
        "suggested_seconds": 45,
        "questions": [
            "Why do some people prefer living in big cities?",
            "How can cities become more comfortable for young people?",
        ],
    },
}


class ExamWorkflow:
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
        run_id = new_run_id()
        question_plan = self.question_planner.plan(request)
        first_part = question_plan.target_parts[0]
        state = {
            "session_id": session_id,
            "mode": request.mode,
            "status": "in_progress",
            "mode_policy": mode_policy_for(request.mode),
            "user_id": request.user_id,
            "session_seed": request.session_seed,
            "topic_ids": request.topic_ids,
            "topic_labels": request.topic_labels,
            "user_background": request.user_background,
            "question_plan": question_plan.model_dump(mode="json"),
            "target_parts": question_plan.target_parts,
            "current_part": first_part,
            "question_index": 0,
            "part_elapsed_seconds": 0,
            "completed_parts": [],
            "answers": [],
        }

        part_plan = self._part_plan(state, first_part)
        suggested_seconds = self._suggested_seconds(state, first_part)
        events = [
            build_event("session.started", session_id, run_id, {"mode": request.mode, **mode_policy_payload(state)}),
            build_event(
                "part.started",
                session_id,
                run_id,
                self._part_started_payload(state, first_part, part_plan),
            ),
            build_event(
                "examiner.message",
                session_id,
                run_id,
                self._examiner_payload(state),
            ),
            build_event(
                "timer.started",
                session_id,
                run_id,
                self._timer_started_payload(state, first_part, suggested_seconds),
            ),
        ]

        return AgentResponse(run_id=run_id, events=events, state=state, next_action="wait_for_user_answer")

    def consume_asr(self, session_id: str, request: ConsumeAsrRequest) -> AgentResponse:
        run_id = new_run_id()
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
        run_id = new_run_id()
        state = deepcopy(request.session_state)
        state.setdefault("current_part", 1)
        state.setdefault("question_index", 0)
        state.setdefault("completed_parts", [])
        state["question_index"] += 1
        state["followup_count"] = 0

        current_part = int(state["current_part"])
        if self._should_complete_current_part(state, current_part):
            return self._complete_or_transition_part(session_id, run_id, state, current_part)

        if state["question_index"] < len(self._questions_for_state(state)):
            return self._ask_current_question(session_id, run_id, state)

        return self._complete_or_transition_part(session_id, run_id, state, current_part)

    def _complete_or_transition_part(self, session_id: str, run_id: str, state: dict, current_part: int) -> AgentResponse:
        state["completed_parts"].append(current_part)
        completed_payload = self._part_completed_payload(state, current_part)
        if state.get("mode") == "part_practice" or current_part == 3:
            state["status"] = "scoring"
            events = [
                build_event("part.completed", session_id, run_id, completed_payload),
                build_event(
                    "session.completed",
                    session_id,
                    run_id,
                    {
                        "completed_parts": state["completed_parts"],
                        "status": "scoring",
                        **mode_policy_payload(state),
                    },
                ),
                build_event(
                    "scoring.started",
                    session_id,
                    run_id,
                    {
                        "run_reason": "session_completed",
                        "completed_parts": state["completed_parts"],
                        "answer_count": len(state.get("answers") or []),
                        **mode_policy_payload(state),
                    },
                ),
            ]
            return AgentResponse(run_id=run_id, events=events, state=state, next_action="score_session")

        state["current_part"] = current_part + 1
        state["question_index"] = 0
        state["part_elapsed_seconds"] = 0
        state["followup_count"] = 0
        part_plan = self._part_plan(state, state["current_part"])
        events = [
            build_event("part.completed", session_id, run_id, completed_payload),
            build_event(
                "part.started",
                session_id,
                run_id,
                self._part_started_payload(state, state["current_part"], part_plan),
            ),
        ]
        response = self._ask_current_question(session_id, run_id, state)
        response.events[0:0] = events
        return response

    def _ask_current_question(self, session_id: str, run_id: str, state: dict) -> AgentResponse:
        current_part = int(state["current_part"])
        suggested_seconds = self._suggested_seconds(state, current_part)
        events = [
            build_event(
                "examiner.message",
                session_id,
                run_id,
                self._examiner_payload(state),
            ),
            build_event(
                "timer.started",
                session_id,
                run_id,
                self._timer_started_payload(state, current_part, suggested_seconds),
            ),
        ]
        return AgentResponse(run_id=run_id, events=events, state=state, next_action="wait_for_user_answer")

    def _examiner_payload(self, state: dict) -> dict:
        current_part = int(state["current_part"])
        questions = self._questions_for_state(state)
        question_index = int(state["question_index"])
        question = questions[question_index]
        utterance = self.examiner_agent.build_turn(
            ExaminerTurnInput(
                mode=state.get("mode", "full_exam"),
                part=current_part,
                question_id=question["question_id"],
                question_text=question["text"],
                question_index=question_index,
                total_questions=len(questions),
                practice_mode=False,
            )
        )
        payload = {
            "part": utterance.part,
            "question_id": utterance.question_id,
            "text": utterance.text,
            "timer_policy": {"suggested_seconds": self._suggested_seconds(state, current_part)},
            "style_tags": utterance.style_tags,
            **({"topic": question.get("topic")} if question.get("topic") else {}),
            "part_timebox_seconds": self._timebox_seconds(state, current_part),
            **mode_policy_payload(state),
            **self._part3_discussion_payload(question),
        }
        if current_part == 2:
            payload["cue_card"] = self._cue_card_payload(state)
            payload["timer_policy"] = {
                "suggested_seconds": self._suggested_seconds(state, current_part),
                "preparation_seconds": self._part2_preparation_seconds(state),
                "speaking_seconds": self._part2_speaking_seconds(state),
                "warning_seconds": PART2_WARNING_SECONDS,
            }
        return payload

    def _current_question(self, state: dict) -> str:
        index = int(state["question_index"])
        return self._questions_for_state(state)[index]["text"]

    def _question_id(self, state: dict) -> str:
        index = int(state["question_index"])
        return self._questions_for_state(state)[index]["question_id"]

    def _suggested_seconds(self, state: dict, part: int) -> int:
        part_plan = self._part_plan(state, part)
        return int(part_plan.get("suggested_seconds") or PART_CONFIG[part]["suggested_seconds"])

    def _timebox_seconds(self, state: dict, part: int) -> int:
        part_plan = self._part_plan(state, part)
        return int(part_plan.get("timebox_seconds") or (300 if part in {1, 3} else 180))

    def _part_started_payload(self, state: dict, part: int, part_plan: dict) -> dict:
        payload = {
            "part": part,
            "title": part_plan.get("title", PART_CONFIG[part]["title"]),
            "timebox_seconds": self._timebox_seconds(state, part),
            **mode_policy_payload(state),
        }
        if part == 2:
            payload.update(
                {
                    "preparation_seconds": self._part2_preparation_seconds(state),
                    "speaking_seconds": self._part2_speaking_seconds(state),
                    "warning_seconds": PART2_WARNING_SECONDS,
                }
            )
        if part == 3:
            questions = part_plan.get("questions") or []
            if questions:
                payload.update(self._part3_discussion_payload(questions[0]))
        return payload

    def _timer_started_payload(self, state: dict, part: int, suggested_seconds: int) -> dict:
        payload = {
            "part": part,
            "suggested_seconds": suggested_seconds,
            "timebox_seconds": self._timebox_seconds(state, part),
            **mode_policy_payload(state),
        }
        if part == 2:
            payload.update(
                {
                    "phase": "prepare_then_speak",
                    "preparation_seconds": self._part2_preparation_seconds(state),
                    "speaking_seconds": self._part2_speaking_seconds(state),
                    "warning_seconds": PART2_WARNING_SECONDS,
                }
            )
        return payload

    def _cue_card_payload(self, state: dict) -> dict:
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

    def _part3_discussion_payload(self, question: dict) -> dict:
        if int(question.get("part") or 0) != 3:
            return {}
        payload = {
            "discussion_level": question.get("discussion_level") or "abstract",
            "discussion_focus": question.get("discussion_focus") or "social_change",
        }
        if question.get("linked_part2_question_id"):
            payload["linked_part2_question_id"] = question["linked_part2_question_id"]
        if question.get("linked_part2_topic"):
            payload["linked_part2_topic"] = question["linked_part2_topic"]
        return payload

    def _part2_preparation_seconds(self, state: dict) -> int:
        return int(self._cue_card_payload(state).get("preparation_seconds") or 60)

    def _part2_speaking_seconds(self, state: dict) -> int:
        return int(self._cue_card_payload(state).get("speaking_seconds") or self._suggested_seconds(state, 2))

    def _part_plan(self, state: dict, part: int) -> dict:
        question_plan = state.get("question_plan")
        if isinstance(question_plan, dict):
            for item in question_plan.get("parts", []):
                if int(item.get("part") or 0) == part:
                    return item
        return {
            "part": part,
            "title": PART_CONFIG[part]["title"],
            "suggested_seconds": PART_CONFIG[part]["suggested_seconds"],
            "timebox_seconds": 300 if part in {1, 3} else 180,
            "questions": [
                {
                    "question_id": f"mock_p{part}_q{index + 1}",
                    "part": part,
                    "text": question,
                    "timer_policy": {"suggested_seconds": PART_CONFIG[part]["suggested_seconds"]},
                }
                for index, question in enumerate(PART_CONFIG[part]["questions"])
            ],
        }

    def _questions_for_state(self, state: dict) -> list[dict]:
        part = int(state["current_part"])
        return list(self._part_plan(state, part)["questions"])

    def _state_for_asr(self, session_id: str, request: ConsumeAsrRequest) -> dict:
        state = deepcopy(request.session_state)
        state.setdefault("session_id", session_id)
        state.setdefault("mode", "full_exam")
        state.setdefault("mode_policy", mode_policy_for(str(state.get("mode") or "full_exam")))
        state.setdefault("current_part", 1)
        state.setdefault("question_index", 0)
        state.setdefault("completed_parts", [])
        state.setdefault("followup_count", 0)
        state.setdefault("part_elapsed_seconds", 0)
        return state

    def _plan_followup(self, state: dict, request: ConsumeAsrRequest):
        current_part = int(state.get("current_part") or 1)
        question_text = None
        try:
            question_text = self._current_question(state)
        except (KeyError, IndexError, TypeError, ValueError):
            question_text = None
        return self.followup_planner.plan(
            FollowupPlannerInput(
                mode=state.get("mode", "full_exam"),
                part=current_part,
                asr_text=request.asr_text,
                question_text=question_text,
                question_index=int(state.get("question_index") or 0),
                followup_count=int(state.get("followup_count") or 0),
            )
        )

    def _append_answer_record(self, state: dict, request: ConsumeAsrRequest, followup_plan) -> None:
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
                "mode_policy": state.get("mode_policy"),
            }
        )
        state["answers"] = answers

    def _followup_question_events(self, session_id: str, run_id: str, state: dict, suggested_question: str):
        current_part = int(state.get("current_part") or 1)
        question_id = f"followup_{state.get('last_turn_id', 'turn')}_{state['followup_count']}"
        payload = {
            "part": current_part,
            "question_id": question_id,
            "text": suggested_question,
            "timer_policy": {"suggested_seconds": self._suggested_seconds(state, current_part)},
            "style_tags": ["followup", f"part_{current_part}"],
            **mode_policy_payload(state),
            **self._part3_discussion_payload(self._questions_for_state(state)[int(state.get("question_index") or 0)]),
        }
        return [
            build_event("examiner.message", session_id, run_id, payload),
            build_event(
                "timer.started",
                session_id,
                run_id,
                self._timer_started_payload(state, current_part, self._suggested_seconds(state, current_part)),
            ),
        ]

    def _should_complete_current_part(self, state: dict, current_part: int) -> bool:
        elapsed = int(state.get("part_elapsed_seconds") or 0)
        return elapsed >= self._timebox_seconds(state, current_part)

    def _part_completed_payload(self, state: dict, current_part: int) -> dict:
        elapsed = int(state.get("part_elapsed_seconds") or 0)
        reason = "timebox_reached" if elapsed >= self._timebox_seconds(state, current_part) else "questions_completed"
        return {
            "part": current_part,
            "reason": reason,
            "elapsed_seconds": elapsed,
            "timebox_seconds": self._timebox_seconds(state, current_part),
        }
