from __future__ import annotations

from typing import Any

from app.protocols.schemas import SessionMode


MODE_POLICY_VERSION = "mode_policy.v1"


def mode_policy_for(mode: SessionMode | str) -> dict[str, Any]:
    if mode == "full_exam":
        return {
            "policy_version": MODE_POLICY_VERSION,
            "mode": "full_exam",
            "prompt_profile": "examiner_exam",
            "ui_profile": "exam",
            "allow_practice_hints": False,
            "allow_structure_suggestions": False,
            "allow_reference_answer": False,
            "allow_topic_guidance": False,
            "allow_chinese_strategy_hints": False,
            "scoring_strictness": "exam_like",
        }

    return {
        "policy_version": MODE_POLICY_VERSION,
        "mode": mode,
        "prompt_profile": "coach_practice",
        "ui_profile": "practice",
        "allow_practice_hints": True,
        "allow_structure_suggestions": True,
        "allow_reference_answer": True,
        "allow_topic_guidance": mode == "topic_practice",
        "allow_chinese_strategy_hints": True,
        "scoring_strictness": "diagnostic",
    }


def mode_policy_payload(state: dict[str, Any]) -> dict[str, Any]:
    policy = state.get("mode_policy")
    if not isinstance(policy, dict):
        policy = mode_policy_for(str(state.get("mode") or "full_exam"))
        state["mode_policy"] = policy
    return {"mode_policy": policy}


def allows_practice_hints(state: dict[str, Any]) -> bool:
    policy = state.get("mode_policy")
    if not isinstance(policy, dict):
        policy = mode_policy_for(str(state.get("mode") or "full_exam"))
        state["mode_policy"] = policy
    return bool(policy.get("allow_practice_hints"))
