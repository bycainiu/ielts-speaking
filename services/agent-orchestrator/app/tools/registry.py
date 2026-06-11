from __future__ import annotations

from time import perf_counter
from typing import Any, Awaitable, Callable

from app.protocols.agent_message import SessionContext
from app.rules.fallback_plan import FALLBACK_CATALOG
from app.rules.scoring_rules import analyze_response_quality
from app.tools.types import ToolResult


ToolExecutor = Callable[[dict[str, Any], SessionContext], Awaitable[ToolResult] | ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}
        self._executors: dict[str, ToolExecutor] = {}
        self._register_builtin_tools()

    def register(self, name: str, schema: dict[str, Any], executor: ToolExecutor) -> None:
        self._schemas[name] = schema
        self._executors[name] = executor

    def schemas_for(self, tool_names: list[str]) -> list[dict[str, Any]]:
        return [self._schemas[name] for name in tool_names if name in self._schemas]

    async def execute(self, name: str, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        executor = self._executors.get(name)
        if executor is None:
            return ToolResult(name=name, status="failed", error_code="unknown_tool")
        started = perf_counter()
        result = executor(arguments, context)
        if hasattr(result, "__await__"):
            result = await result
        result.latency_ms = int((perf_counter() - started) * 1000)
        return result

    def _register_builtin_tools(self) -> None:
        self.register(
            "search_questions",
            {
                "type": "function",
                "function": {
                    "name": "search_questions",
                    "description": "Search IELTS speaking questions by query and part.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "part": {"type": "integer", "minimum": 1, "maximum": 3},
                        },
                        "required": ["query", "part"],
                    },
                },
            },
            self._search_questions,
        )
        self.register(
            "get_cue_card",
            {
                "type": "function",
                "function": {
                    "name": "get_cue_card",
                    "description": "Get cue card details for a question id.",
                    "parameters": {
                        "type": "object",
                        "properties": {"question_id": {"type": "string"}},
                        "required": ["question_id"],
                    },
                },
            },
            self._get_cue_card,
        )
        self.register(
            "get_followup_templates",
            {
                "type": "function",
                "function": {
                    "name": "get_followup_templates",
                    "description": "Get follow-up templates for a question.",
                    "parameters": {
                        "type": "object",
                        "properties": {"question_id": {"type": "string"}, "part": {"type": "integer"}},
                        "required": ["question_id"],
                    },
                },
            },
            self._get_followup_templates,
        )
        self.register(
            "get_user_background",
            {
                "type": "function",
                "function": {
                    "name": "get_user_background",
                    "description": "Get candidate background aspects.",
                    "parameters": {
                        "type": "object",
                        "properties": {"aspects": {"type": "array", "items": {"type": "string"}}},
                    },
                },
            },
            self._get_user_background,
        )
        self.register(
            "get_session_history",
            {
                "type": "function",
                "function": {
                    "name": "get_session_history",
                    "description": "Get recent session history summary.",
                    "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
                },
            },
            self._get_session_history,
        )
        self.register(
            "analyze_response_quality",
            {
                "type": "function",
                "function": {
                    "name": "analyze_response_quality",
                    "description": "Analyze candidate response quality.",
                    "parameters": {
                        "type": "object",
                        "properties": {"asr_text": {"type": "string"}, "part": {"type": "integer"}},
                        "required": ["asr_text", "part"],
                    },
                },
            },
            self._analyze_response_quality,
        )
        self.register(
            "compute_wpm",
            {
                "type": "function",
                "function": {
                    "name": "compute_wpm",
                    "description": "Compute words per minute.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "words_count": {"type": "integer"},
                            "duration_ms": {"type": "integer"},
                        },
                        "required": ["words_count", "duration_ms"],
                    },
                },
            },
            self._compute_wpm,
        )
        self.register(
            "detect_long_pauses",
            {
                "type": "function",
                "function": {
                    "name": "detect_long_pauses",
                    "description": "Detect long pauses count.",
                    "parameters": {
                        "type": "object",
                        "properties": {"long_pause_count": {"type": "integer"}},
                    },
                },
            },
            self._detect_long_pauses,
        )
        self.register(
            "estimate_filler_ratio",
            {
                "type": "function",
                "function": {
                    "name": "estimate_filler_ratio",
                    "description": "Estimate filler word ratio.",
                    "parameters": {
                        "type": "object",
                        "properties": {"filler_ratio": {"type": "number"}},
                    },
                },
            },
            self._estimate_filler_ratio,
        )
        self.register(
            "get_rubric_descriptor",
            {
                "type": "function",
                "function": {
                    "name": "get_rubric_descriptor",
                    "description": "Get band descriptor for a criterion.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "criterion": {"type": "string"},
                            "band": {"type": "number"},
                        },
                        "required": ["criterion"],
                    },
                },
            },
            self._get_rubric_descriptor,
        )
        self.register(
            "get_anchor_samples",
            {
                "type": "function",
                "function": {
                    "name": "get_anchor_samples",
                    "description": "Get anchor samples for calibration.",
                    "parameters": {
                        "type": "object",
                        "properties": {"criterion": {"type": "string"}},
                    },
                },
            },
            self._get_anchor_samples,
        )

    def _search_questions(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        part = int(arguments.get("part") or context.current_part or 1)
        query = str(arguments.get("query") or "").lower()
        catalog = FALLBACK_CATALOG.get(part, [])
        results = [
            {
                "question_id": f"search_p{part}_q{index + 1}",
                "part": part,
                "text": item["text"],
                "topic": item.get("topic"),
                "score": 0.8 if query in item["text"].lower() or query in item.get("topic", "").lower() else 0.5,
            }
            for index, item in enumerate(catalog)
        ]
        return ToolResult(name="search_questions", status="completed", output={"results": results, "count": len(results)})

    def _get_cue_card(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        question_id = str(arguments.get("question_id") or "")
        part2 = FALLBACK_CATALOG.get(2, [{}])[0]
        return ToolResult(
            name="get_cue_card",
            status="completed",
            output={
                "question_id": question_id,
                "prompt": part2.get("text", "Describe a place you enjoy visiting."),
                "bullet_points": ["where it is", "how often you go", "what you do there", "why you like it"],
            },
        )

    def _get_followup_templates(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        return ToolResult(
            name="get_followup_templates",
            status="completed",
            output={
                "templates": [
                    {"text": "Could you tell me a little more about that?"},
                    {"text": "Why is that important to you?"},
                ]
            },
        )

    def _get_user_background(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        profile = dict(context.user_profile)
        aspects = arguments.get("aspects") or list(profile.keys())
        return ToolResult(
            name="get_user_background",
            status="completed",
            output={"aspects": aspects, "profile": profile},
        )

    def _get_session_history(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        limit = int(arguments.get("limit") or 5)
        turns = context.conversation_history[-limit:]
        return ToolResult(
            name="get_session_history",
            status="completed",
            output={"turns": [turn.model_dump(mode="json") for turn in turns]},
        )

    def _analyze_response_quality(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        asr_text = str(arguments.get("asr_text") or "")
        part = int(arguments.get("part") or context.current_part or 1)
        return ToolResult(
            name="analyze_response_quality",
            status="completed",
            output=analyze_response_quality(asr_text=asr_text, part=part),
        )

    def _compute_wpm(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        words = int(arguments.get("words_count") or 0)
        duration_ms = max(1, int(arguments.get("duration_ms") or 1))
        wpm = round(words / (duration_ms / 60000), 1)
        return ToolResult(name="compute_wpm", status="completed", output={"wpm": wpm})

    def _detect_long_pauses(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        count = int(arguments.get("long_pause_count") or 0)
        return ToolResult(name="detect_long_pauses", status="completed", output={"long_pause_count": count})

    def _estimate_filler_ratio(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        ratio = float(arguments.get("filler_ratio") or 0.0)
        return ToolResult(name="estimate_filler_ratio", status="completed", output={"filler_ratio": ratio})

    def _get_rubric_descriptor(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        criterion = str(arguments.get("criterion") or "fluency_coherence")
        band = float(arguments.get("band") or 6.0)
        return ToolResult(
            name="get_rubric_descriptor",
            status="completed",
            output={"criterion": criterion, "band": band, "descriptor": f"Band {band} descriptor for {criterion}."},
        )

    def _get_anchor_samples(self, arguments: dict[str, Any], context: SessionContext) -> ToolResult:
        criterion = str(arguments.get("criterion") or "fluency_coherence")
        return ToolResult(
            name="get_anchor_samples",
            status="completed",
            output={"criterion": criterion, "samples": [{"band": 6.0, "excerpt": "Sample response at band 6."}]},
        )
