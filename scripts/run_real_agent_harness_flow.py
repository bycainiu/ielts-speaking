from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = REPO_ROOT / "services" / "agent-harness"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "real-agent-harness"
SAMPLE_WAV = ARTIFACT_DIR / "real_ielts_answer_sample.wav"
REPORT_JSON = ARTIFACT_DIR / "real_agent_harness_flow_report.json"
REPORT_MD = ARTIFACT_DIR / "real_agent_harness_flow_report.md"
EVENT_TABLE_MD = ARTIFACT_DIR / "real_agent_harness_event_table.md"

sys.path.insert(0, str(SERVICE_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.models.mimo_client import ChatMessage, MiMoChatClient, MiMoClientConfig  # noqa: E402
from app.models.structured_output import extract_json_text  # noqa: E402


WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


PRACTICE_ANSWER = (
    "I would like to describe a public library near West Lake. I started going there when I was preparing for an "
    "English exam, and it quickly became part of my weekend routine. The building is bright and quiet, so I can "
    "concentrate for two or three hours without feeling stressed. What makes it important to me is not only the "
    "books, but also the calm atmosphere and the feeling that many people are trying to improve themselves."
)


FULL_EXAM_ANSWERS = {
    1: [
        (
            "I come from Hangzhou, a city with beautiful lakes and convenient public transport. What I like most is "
            "that it feels modern but still relaxed, because there are parks, small restaurants, and quiet places to "
            "walk after work."
        ),
        (
            "The most pleasant part of my hometown is the balance between nature and daily life. For example, I can "
            "take a short bus ride to the lake, but I can also find libraries, cafes, and subway stations very close "
            "to my neighbourhood."
        ),
        (
            "Yes, I think it has changed a lot in recent years. The transport system is much better now, and many "
            "young people use online services for shopping, study, and booking local activities, so daily life feels "
            "more efficient than before."
        ),
        (
            "For visitors, I would recommend walking around the lake in the late afternoon. It is not just a scenic "
            "place; it also shows the slower side of the city, and people can see local families, students, and "
            "office workers sharing the same public space."
        ),
    ],
    2: [
        (
            "I am going to talk about a public library near my home that I enjoy visiting. I first went there when I "
            "was preparing for an English test, because I needed a quiet place away from my phone and household "
            "noise. The library has large windows, comfortable desks, and a small reading area where people speak "
            "very softly. I usually spend Saturday mornings there, reading articles or practising speaking notes. "
            "It matters to me because the atmosphere helps me stay focused, and it also reminds me that studying can "
            "be a calm routine rather than a stressful task."
        )
    ],
    3: [
        (
            "Some people prefer big cities because they offer more choices. There are better job opportunities, more "
            "public facilities, and a wider range of cultural activities. At the same time, city life can be tiring, "
            "so I think the attraction is mainly practical rather than purely emotional."
        ),
        (
            "Cities can become more comfortable for young people by improving affordable transport and creating more "
            "public spaces where people can study, exercise, or meet friends without spending much money. If a city "
            "only builds commercial areas, young residents may feel busy but not truly supported."
        ),
    ],
}


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    client = TestClient(app)

    started_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "started_at": started_at,
        "settings": {
            "mock_model_enabled": settings.mock_model_enabled,
            "api_format": settings.mimo_api_format,
            "base_url": settings.mimo_base_url,
            "default_model": settings.mimo_default_model,
            "api_key_present": bool(settings.mimo_api_key and settings.mimo_api_key != "change-me"),
            "api_key_length": len(settings.mimo_api_key or ""),
        },
        "direct_model_probe": asyncio.run(run_direct_model_probe(settings)),
        "audio_boundary": run_audio_boundary(client),
        "scenarios": {},
    }

    practice_result = run_practice_flow(client)
    full_exam_result = run_full_exam_flow(client)
    report["scenarios"]["part_practice"] = practice_result
    report["scenarios"]["full_exam"] = full_exam_result
    report["observability"] = {
        "practice_summary": get_json(client, "/agent/observability/summary", params={"session_id": practice_result["session_id"]}),
        "full_exam_summary": get_json(client, "/agent/observability/summary", params={"session_id": full_exam_result["session_id"]}),
        "full_exam_alerts": get_json(client, "/agent/observability/alerts", params={"session_id": full_exam_result["session_id"]}),
        "metrics_head": client.get("/metrics").text.splitlines()[:12],
    }
    report["completed_at"] = datetime.now(timezone.utc).isoformat()

    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    EVENT_TABLE_MD.write_text(render_event_table(report), encoding="utf-8")
    REPORT_MD.write_text(render_report(report), encoding="utf-8")
    print(json.dumps({"report_json": str(REPORT_JSON), "report_md": str(REPORT_MD), "event_table_md": str(EVENT_TABLE_MD)}, ensure_ascii=False))


async def run_direct_model_probe(settings: Any) -> dict[str, Any]:
    config = MiMoClientConfig.from_settings(settings)
    async with MiMoChatClient(config) as client:
        response = await client.complete(
            [
                ChatMessage(
                    role="user",
                    content=(
                        "Do not explain. Return final answer as valid JSON only: "
                        '{"ok": true, "generated_part1_question": '
                        '"one IELTS Speaking Part 1 question about hometown", "one_tip": "one short tip"}.'
                    ),
                )
            ],
            temperature=0,
            max_tokens=500,
        )
    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(extract_json_text(response.content))
    except Exception:
        parsed = None
    return {
        "model": response.model,
        "finish_reason": response.finish_reason,
        "usage": response.usage.__dict__,
        "parsed": parsed,
        "content_excerpt": response.content[:400],
    }


def run_audio_boundary(client: TestClient) -> dict[str, Any]:
    if not SAMPLE_WAV.exists():
        raise FileNotFoundError(f"音频样本不存在：{SAMPLE_WAV}")
    audio_base64 = base64.b64encode(SAMPLE_WAV.read_bytes()).decode("ascii")
    transcribe = post_json(
        client,
        "/agent/audio/transcribe",
        {
            "audio_asset_id": "real_sapi_answer_001",
            "mime_type": "audio/wav",
            "duration_ms": 15000,
            "language_hint": "en",
            "audio_base64": audio_base64,
        },
    )
    synthesize = post_json(
        client,
        "/agent/audio/synthesize",
        {
            "text": "Let's talk about your hometown. What do you like most about the place where you live?",
            "voice_id": "ielts_examiner_default",
            "speaking_rate": 1.0,
            "emotion": "neutral",
            "style": "examiner",
        },
    )
    synthesize["audio_base64_len"] = len(synthesize.pop("audio_base64"))
    return {
        "sample_audio_path": str(SAMPLE_WAV),
        "sample_audio_bytes": SAMPLE_WAV.stat().st_size,
        "transcribe": transcribe,
        "synthesize": synthesize,
    }


def run_practice_flow(client: TestClient) -> dict[str, Any]:
    session_id = f"real_practice_{uuid4().hex[:8]}"
    event_rows: list[dict[str, Any]] = []

    plan = post_json(
        client,
        f"/agent/sessions/{session_id}/plan",
        {"mode": "part_practice", "user_id": "real_user_practice", "part": 2, "topic_ids": ["library", "study"]},
    )
    collect_events(event_rows, "part_practice", "plan", plan)
    state = plan["state"]

    consume = post_json(
        client,
        f"/agent/sessions/{session_id}/consume-asr",
        {
            "turn_id": "practice_turn_001",
            "asr_text": PRACTICE_ANSWER,
            "asr_confidence": 0.93,
            "audio_asset_id": "real_sapi_answer_001",
            "session_state": state,
        },
    )
    enrich_latest_answer(consume["state"], PRACTICE_ANSWER, asr_confidence=0.93)
    collect_events(event_rows, "part_practice", "consume-asr", consume)
    state = consume["state"]

    completed = post_json(client, f"/agent/sessions/{session_id}/next-turn", {"session_state": state})
    collect_events(event_rows, "part_practice", "next-turn", completed)

    score = post_json(
        client,
        f"/agent/sessions/{session_id}/score",
        {"session_state": completed["state"], "topic_keywords": ["library", "study", "quiet", "routine"]},
    )
    collect_events(event_rows, "part_practice", "score", score)

    return scenario_result(session_id, event_rows, plan, score)


def run_full_exam_flow(client: TestClient) -> dict[str, Any]:
    session_id = f"real_full_exam_{uuid4().hex[:8]}"
    event_rows: list[dict[str, Any]] = []
    answer_offsets = {1: 0, 2: 0, 3: 0}

    current = post_json(client, f"/agent/sessions/{session_id}/plan", {"mode": "full_exam", "user_id": "real_user_exam"})
    collect_events(event_rows, "full_exam", "plan", current)
    state = current["state"]

    while True:
        part = int(state.get("current_part") or 1)
        answer_index = answer_offsets[part]
        answer = FULL_EXAM_ANSWERS[part][answer_index]
        answer_offsets[part] += 1
        turn_id = f"exam_p{part}_t{answer_offsets[part]:03d}"

        consume = post_json(
            client,
            f"/agent/sessions/{session_id}/consume-asr",
            {
                "turn_id": turn_id,
                "asr_text": answer,
                "asr_confidence": 0.91,
                "audio_asset_id": f"asset_{turn_id}",
                "session_state": state,
            },
        )
        enrich_latest_answer(consume["state"], answer, asr_confidence=0.91)
        collect_events(event_rows, "full_exam", "consume-asr", consume)

        current = post_json(client, f"/agent/sessions/{session_id}/next-turn", {"session_state": consume["state"]})
        collect_events(event_rows, "full_exam", "next-turn", current)
        state = current["state"]
        if current["next_action"] == "score_session":
            break

    score = post_json(
        client,
        f"/agent/sessions/{session_id}/score",
        {"session_state": state, "topic_keywords": ["hometown", "city", "library", "public transport"]},
    )
    collect_events(event_rows, "full_exam", "score", score)
    return scenario_result(session_id, event_rows, current, score)


def scenario_result(session_id: str, event_rows: list[dict[str, Any]], terminal_response: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    score_report = score["state"]["score_report"]
    return {
        "session_id": session_id,
        "terminal_next_action": score["next_action"],
        "answer_count": len(score["state"].get("answers") or []),
        "event_count": len(event_rows),
        "event_rows": event_rows,
        "completed_parts": score["state"].get("completed_parts"),
        "score_run_id": score["run_id"],
        "overall_band": score_report["overall_band"],
        "confidence": score_report["confidence"],
        "criteria": score_report["criteria"],
        "feedback_count": len(score["state"].get("feedback_items") or []),
        "reference_answer_count": len(score["state"].get("reference_answers") or []),
        "last_next_action_before_score": terminal_response["next_action"],
    }


def enrich_latest_answer(state: dict[str, Any], transcript: str, *, asr_confidence: float) -> None:
    answers = state.get("answers") or []
    if not answers:
        return
    words = len(WORD_RE.findall(transcript))
    duration_ms = max(12_000, int(words / 130 * 60_000))
    latest = answers[-1]
    latest["speech_metrics"] = {
        "duration_ms": duration_ms,
        "words_count": words,
        "wpm": round(words / (duration_ms / 60_000), 2),
        "long_pause_count": 1 if words >= 35 else 0,
        "mean_pause_ms": 650,
        "total_pause_ms": 650,
        "filler_count": 1,
        "filler_ratio": round(1 / max(words, 1), 4),
        "asr_confidence": asr_confidence,
    }
    latest["pronunciation_evidence"] = {
        "turn_id": latest["turn_id"],
        "intelligibility_score": 0.84,
        "pronunciation_score": 0.8,
        "prosody_score": 0.78,
        "unclear_segment_count": 0,
        "audio_quality": "good",
        "evidence_source": "real_sapi_audio_boundary_plus_turn_metrics",
    }


def post_json(client: TestClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"{path} failed: {response.status_code} {response.text[:800]}")
    return response.json()


def get_json(client: TestClient, path: str, *, params: dict[str, Any] | None = None) -> Any:
    response = client.get(path, params=params)
    if response.status_code >= 400:
        raise RuntimeError(f"{path} failed: {response.status_code} {response.text[:800]}")
    return response.json()


def collect_events(rows: list[dict[str, Any]], scenario: str, api_call: str, response: dict[str, Any]) -> None:
    for event in response.get("events") or []:
        payload = event.get("payload") or {}
        rows.append(
            {
                "index": len(rows) + 1,
                "scenario": scenario,
                "api_call": api_call,
                "event_type": event.get("type"),
                "run_id": response.get("run_id"),
                "next_action": response.get("next_action"),
                "part": payload.get("part"),
                "question_id": payload.get("question_id"),
                "status": payload.get("status"),
                "decision": payload.get("decision"),
                "summary": summarize_payload(payload),
            }
        )


def summarize_payload(payload: dict[str, Any]) -> str:
    for key in ("text", "reason", "run_reason", "title", "disclaimer"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return " ".join(value.split())[:120]
    if "overall_band" in payload:
        return f"overall_band={payload['overall_band']}, feedback_count={payload.get('feedback_count')}"
    if "criterion" in payload:
        return f"{payload.get('criterion')} band={payload.get('band')} confidence={payload.get('confidence')}"
    if "completed_parts" in payload:
        return f"completed_parts={payload.get('completed_parts')}"
    return ""


def render_event_table(report: dict[str, Any]) -> str:
    rows: list[str] = [
        "| # | 场景 | API | 事件 | Part | 下一动作 | 关键摘要 |",
        "|---:|---|---|---|---:|---|---|",
    ]
    index = 1
    for scenario in ("part_practice", "full_exam"):
        for row in report["scenarios"][scenario]["event_rows"]:
            rows.append(
                "| {index} | {scenario} | `{api}` | `{event}` | {part} | `{next_action}` | {summary} |".format(
                    index=index,
                    scenario=scenario,
                    api=row["api_call"],
                    event=row["event_type"],
                    part=row["part"] or "",
                    next_action=row["next_action"],
                    summary=escape_md(row["summary"]),
                )
            )
            index += 1
    return "\n".join(rows) + "\n"


def render_report(report: dict[str, Any]) -> str:
    practice = report["scenarios"]["part_practice"]
    exam = report["scenarios"]["full_exam"]
    audio = report["audio_boundary"]
    model_probe = report["direct_model_probe"]
    lines = [
        "# Agent Harness 真实供应商联调报告",
        "",
        f"- 执行时间：{report['started_at']} -> {report['completed_at']}",
        f"- 模型供应商：`{report['settings']['api_format']}` `{report['settings']['base_url']}`",
        f"- 默认模型：`{report['settings']['default_model']}`，mock：`{report['settings']['mock_model_enabled']}`",
        f"- 直接模型探针：model=`{model_probe['model']}`，usage={model_probe['usage']}",
        f"- ASR：provider=`{audio['transcribe']['provider']}`，model=`{audio['transcribe']['model']}`，转写=`{audio['transcribe']['asr_text']}`",
        f"- TTS：provider=`{audio['synthesize']['provider']}`，model=`{audio['synthesize']['model']}`，audio_base64_len={audio['synthesize']['audio_base64_len']}",
        "",
        "## 场景结果",
        "",
        (
            f"- Part Practice：session=`{practice['session_id']}`，answers={practice['answer_count']}，"
            f"overall_band={practice['overall_band']}，confidence={practice['confidence']}，next_action=`{practice['terminal_next_action']}`"
        ),
        (
            f"- Full Exam：session=`{exam['session_id']}`，answers={exam['answer_count']}，"
            f"completed_parts={exam['completed_parts']}，overall_band={exam['overall_band']}，"
            f"confidence={exam['confidence']}，next_action=`{exam['terminal_next_action']}`"
        ),
        "",
        "## 事件表",
        "",
        EVENT_TABLE_MD.read_text(encoding="utf-8") if EVENT_TABLE_MD.exists() else render_event_table(report),
    ]
    return "\n".join(lines)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
