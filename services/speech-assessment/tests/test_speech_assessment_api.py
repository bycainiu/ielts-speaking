import sys
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.main import app  # noqa: E402


client = TestClient(app)


def test_healthz_exposes_evidence_policy() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "speech-assessment-service"
    assert body["features"]["fluency_metrics"] is True
    assert body["features"]["word_timestamps"] is True
    assert body["features"]["faster_whisper"] == "optional"
    assert body["features"]["gopt"] == "deterministic_gopt"
    assert body["features"]["mfa_kaldi_gop_drill"] == "deterministic_adapter_boundary"
    assert body["timestamp_provider"] == "deterministic"
    assert body["policy"]["ielts_band_output_allowed"] is False
    assert body["policy"]["mock_exam_and_pronunciation_drill_separated"] is True


def test_mock_exam_assessment_returns_evidence_without_ielts_band() -> None:
    response = client.post(
        "/speech/assess",
        json={
            "audio_asset_id": "audio_001",
            "session_id": "session_001",
            "turn_id": "turn_001",
            "mode": "mock_exam",
            "duration_ms": 12000,
            "transcript": "Um I I think public transport is useful because it is cheaper and cleaner.",
            "word_timestamps": [
                {"word": "Um", "start_ms": 100, "end_ms": 250, "confidence": 0.72},
                {"word": "I", "start_ms": 300, "end_ms": 360, "confidence": 0.88},
                {"word": "I", "start_ms": 900, "end_ms": 960, "confidence": 0.86},
                {"word": "think", "start_ms": 1800, "end_ms": 2100, "confidence": 0.9},
            ],
            "vad_segments": [
                {"start_ms": 100, "end_ms": 250, "speech_probability": 0.85},
                {"start_ms": 300, "end_ms": 960, "speech_probability": 0.9},
                {"start_ms": 1800, "end_ms": 2100, "speech_probability": 0.88},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mock_exam"
    assert body["audio_quality"]["quality_label"] == "usable"
    assert body["fluency"]["duration_sec"] == 12
    assert body["fluency"]["filler_count"] == 1
    assert body["fluency"]["repetition_count"] == 1
    assert body["fluency"]["long_pause_count"] >= 1
    assert body["pronunciation"]["evidence_level"] == "sentence"
    assert body["pronunciation"]["gopt"]["provider"] == "deterministic_gopt"
    assert body["pronunciation"]["gopt"]["model"] == "gopt-evidence-v0"
    assert 0 <= body["pronunciation"]["gopt"]["accuracy"] <= 1
    assert 0 <= body["pronunciation"]["gopt"]["prosody"] <= 1
    assert body["policy"]["ielts_band_output_allowed"] is False
    assert "overall_band" not in body
    assert "predicted_band" not in body["pronunciation"]
    assert "band" not in body["pronunciation"]


def test_pronunciation_drill_requires_target_text() -> None:
    response = client.post(
        "/speech/assess",
        json={"audio_asset_id": "audio_002", "mode": "pronunciation_drill", "transcript": "hello"},
    )

    assert response.status_code == 422


def test_pronunciation_drill_returns_word_and_phoneme_feedback() -> None:
    response = client.post(
        "/speech/assess",
        json={
            "audio_asset_id": "audio_003",
            "mode": "pronunciation_drill",
            "duration_ms": 5000,
            "target_text": "Technology improves education",
            "transcript": "Technology improves education",
            "word_timestamps": [
                {"word": "Technology", "start_ms": 0, "end_ms": 800, "confidence": 0.82},
                {"word": "improves", "start_ms": 900, "end_ms": 1500, "confidence": 0.75},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "pronunciation_drill"
    assert body["pronunciation"]["evidence_level"] == "phoneme"
    assert body["pronunciation"]["gopt"]["sentence_score"] == body["pronunciation"]["sentence_score"]
    assert body["pronunciation"]["word_feedback"][0]["word"] == "technology"
    assert body["pronunciation"]["word_feedback"][2]["stress"] == "needs_review"


def test_dedicated_pronunciation_drill_api_returns_mfa_kaldi_gop_feedback() -> None:
    response = client.post(
        "/speech/pronunciation-drill",
        json={
            "audio_asset_id": "audio_drill_001",
            "target_text": "Technology improves education",
            "transcript": "Technology improve education",
            "duration_ms": 3600,
            "word_timestamps": [
                {"word": "Technology", "start_ms": 0, "end_ms": 850, "confidence": 0.84},
                {"word": "improve", "start_ms": 900, "end_ms": 1420, "confidence": 0.68},
                {"word": "education", "start_ms": 1700, "end_ms": 2860, "confidence": 0.79},
            ],
            "phoneme_hints": [
                {"word": "technology", "phonemes": ["T", "EH", "K", "N", "AA", "L", "AH", "JH", "IY"]},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "pronunciation_drill"
    assert body["provider"] == "deterministic_mfa_kaldi_gop"
    assert body["model"] == "mfa-kaldi-gop-drill-v0"
    assert body["alignment"]["target_word_count"] == 3
    assert body["alignment"]["substituted_word_count"] == 1
    assert body["word_feedback"][0]["target_word"] == "technology"
    assert body["word_feedback"][1]["status"] == "substituted"
    assert body["phoneme_feedback"][0]["phoneme"] == "T"
    assert body["policy"]["ielts_band_output_allowed"] is False
    assert "overall_band" not in body


def test_dedicated_pronunciation_drill_rejects_mock_exam_band_semantics() -> None:
    response = client.post(
        "/speech/pronunciation-drill",
        json={
            "audio_asset_id": "audio_drill_002",
            "target_text": "Clear speech matters",
            "transcript": "Clear speech matters",
            "provider": "mfa_adapter",
        },
    )

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "pronunciation_drill_adapter_error"
    assert body["detail"]["retryable"] is True


def test_vad_segments_drive_fluency_metrics() -> None:
    response = client.post(
        "/speech/assess",
        json={
            "audio_asset_id": "audio_vad_001",
            "mode": "mock_exam",
            "duration_ms": 10000,
            "transcript": "Um I mean I like like studying online because it is flexible.",
            "word_timestamps": [
                {"word": "I", "start_ms": 0, "end_ms": 100, "confidence": 0.82},
                {"word": "mean", "start_ms": 120, "end_ms": 400, "confidence": 0.8},
                {"word": "I", "start_ms": 1800, "end_ms": 1900, "confidence": 0.82},
                {"word": "like", "start_ms": 1920, "end_ms": 2200, "confidence": 0.76},
                {"word": "like", "start_ms": 3000, "end_ms": 3280, "confidence": 0.74},
            ],
            "vad_segments": [
                {"start_ms": 0, "end_ms": 500, "speech_probability": 0.82},
                {"start_ms": 1800, "end_ms": 2300, "speech_probability": 0.84},
                {"start_ms": 3000, "end_ms": 3600, "speech_probability": 0.78},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fluency"]["speech_duration_sec"] == 1.6
    assert body["fluency"]["silence_ratio"] == 0.84
    assert body["fluency"]["long_pause_count"] == 2
    assert body["fluency"]["mean_pause_ms"] == 1000
    assert body["fluency"]["filler_count"] == 3
    assert body["fluency"]["repetition_count"] == 1
    assert body["fluency"]["self_correction_count"] == 1
    assert body["pronunciation"]["gopt"]["calibration_note"].endswith("do not map directly to IELTS band.")


def test_deterministic_timestamp_transcription_returns_word_timestamps() -> None:
    response = client.post(
        "/speech/transcribe-timestamps",
        json={
            "audio_asset_id": "audio_ts_001",
            "provider": "deterministic",
            "language_hint": "en",
            "duration_ms": 6000,
            "expected_transcript": "Technology helps students learn faster.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "deterministic"
    assert body["model"] == "deterministic-word-timestamp-v0"
    assert body["transcript"] == "Technology helps students learn faster."
    assert len(body["word_timestamps"]) == 5
    assert body["word_timestamps"][0]["word"] == "technology"
    assert body["word_timestamps"][0]["start_ms"] == 0
    assert body["segments"][0]["words"][1]["word"] == "helps"
    assert body["asr_confidence"] >= 0.8
    assert body["alignment_confidence"] >= 0.8
    assert body["downstream_confidence"] >= 0.75
    assert body["audio_quality_label"] == "usable"


def test_timestamp_transcription_lowers_downstream_confidence_for_short_audio() -> None:
    response = client.post(
        "/speech/transcribe-timestamps",
        json={
            "audio_asset_id": "audio_ts_short",
            "provider": "deterministic",
            "duration_ms": 1200,
            "expected_transcript": "short answer",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["downstream_confidence"] < body["asr_confidence"]
    assert body["audio_quality_label"] in {"unknown", "usable"}


def test_timestamp_transcription_rejects_missing_transcript_for_deterministic_provider() -> None:
    response = client.post(
        "/speech/transcribe-timestamps",
        json={"audio_asset_id": "audio_ts_bad", "provider": "deterministic"},
    )

    assert response.status_code == 422
