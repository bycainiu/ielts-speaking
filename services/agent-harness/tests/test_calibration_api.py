from fastapi.testclient import TestClient

from app.evals.multipa_open_response import build_contract_multipa_outputs
from app.main import app


client = TestClient(app)


def test_calibration_anchor_samples_endpoint_returns_audited_dataset() -> None:
    response = client.get("/agent/calibration/anchor-samples", params={"include_samples": "false"})

    assert response.status_code == 200
    body = response.json()
    assert body["audit"]["passed"] is True
    assert body["audit"]["covered_bands"] == [4.0, 5.0, 6.0, 7.0, 8.0]
    assert body["calibration_anchor_count"] == 20
    assert body["samples"] == []


def test_calibration_score_endpoint_applies_anchor_adjustment() -> None:
    response = client.post(
        "/agent/calibration/score",
        json={
            "session_id": "sess_calibration_api",
            "criteria": {
                "fluency_coherence": criterion_payload(6.5),
                "lexical_resource": criterion_payload(6.5),
                "grammatical_range_accuracy": criterion_payload(6.5),
                "pronunciation": criterion_payload(7.5),
            },
            "anchor_samples": [
                {
                    "anchor_sample_id": "anchor_pronunciation_6",
                    "criterion": "pronunciation",
                    "band": 6.0,
                    "score": 0.92,
                    "rationale": "Similar intelligibility and prosody evidence.",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "calibrated"
    assert body["calibrated_criteria"]["pronunciation"]["band"] == 7.0
    pronunciation_adjustment = next(item for item in body["adjustments"] if item["criterion"] == "pronunciation")
    assert pronunciation_adjustment["before_band"] == 7.5
    assert pronunciation_adjustment["after_band"] == 7.0


def test_speech_calibration_regression_endpoint_runs_contract_gate() -> None:
    response = client.post(
        "/agent/calibration/speech-regression",
        json={
            "use_contract_samples": True,
            "allow_synthetic_contract": True,
            "min_production_samples": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["audit"]["passed"] is True
    assert body["mean_absolute_error"] <= 0.75
    assert body["max_absolute_error"] <= 1.0
    assert "direct IELTS band" in body["calibration_note"]
    first_case = body["eval_report"]["results"][0]
    assert first_case["metadata"]["accent_group"]
    assert first_case["metadata"]["recording_quality"]
    assert "transcript_excerpt" in first_case["metadata"]


def test_multipa_experiment_endpoint_runs_contract_outputs() -> None:
    response = client.post(
        "/agent/calibration/multipa-experiment",
        json={
            "use_contract_samples": True,
            "multipa_outputs": [item.model_dump(mode="json") for item in build_contract_multipa_outputs()],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["benchmark_sample_count"] == 12
    assert {item["provider"] for item in body["comparisons"]} == {"gopt_baseline", "multipa_adapter"}


def test_calibration_quality_gate_endpoint_aggregates_backend_checks() -> None:
    response = client.post(
        "/agent/calibration/quality-gate",
        json={
            "include_deepeval_regression": False,
            "include_ragas_rag": False,
            "include_promptfoo_redteam": False,
            "include_performance_baseline": False,
            "include_speech_calibration_contract": True,
            "include_multipa_contract": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert {check["name"] for check in body["checks"]} == {
        "anchor_samples",
        "speech_calibration_contract",
        "multipa_contract",
    }
    assert body["speech_calibration_report"]["audit"]["passed"] is True
    assert body["multipa_experiment_report"]["status"] == "passed"


def criterion_payload(band: float) -> dict[str, object]:
    return {
        "band": band,
        "confidence": 0.8,
        "evidence": [
            {
                "turn_id": "turn_1",
                "quote": "WPM and pause evidence",
                "reason": "Dimension-specific evidence is available.",
            }
        ],
        "suggestions": ["Keep feedback specific."],
        "raw_output": {},
    }
