from app.rules.scoring_rules import IELTS_DISCLAIMER, REQUIRED_CRITERIA, build_score_report


def test_build_score_report_matches_api_go_shape() -> None:
    report = build_score_report(
        [
            {"turn_id": "turn_1", "asr_text": "I like my hometown because it is peaceful and convenient."},
            {"turn_id": "turn_2", "asr_text": "It is a library near my home and I visit it every weekend."},
        ]
    )
    assert report["disclaimer"] == IELTS_DISCLAIMER
    assert report["confidence"] >= 0
    assert report["overall_band"] >= 5.5
    assert set(report["criteria"]) == set(REQUIRED_CRITERIA)
    for criterion in REQUIRED_CRITERIA:
        entry = report["criteria"][criterion]
        assert isinstance(entry["band"], float)
        assert isinstance(entry["confidence"], float)
        assert entry["band"] * 2 == int(entry["band"] * 2)
        assert isinstance(entry["evidence"], list)
        assert isinstance(entry["suggestions"], list)
        assert isinstance(entry["raw_output"], dict)
