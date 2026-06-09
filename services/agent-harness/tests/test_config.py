import json

import pytest

from app.core.config import DEFAULT_MIMO_AVAILABLE_MODELS, Settings, parse_mimo_available_models


def test_default_mimo_available_models_include_planned_provider_models() -> None:
    settings = Settings(
        MIMO_API_KEY="test-key",
        MIMO_BASE_URL="https://api.mimo.example/anthropic",
        MIMO_API_FORMAT="anthropic",
    )

    assert settings.mimo_available_models() == DEFAULT_MIMO_AVAILABLE_MODELS
    assert {
        "mimo-v2.5-pro",
        "mimo-v2.5",
        "mimo-v2.5-asr",
        "mimo-v2.5-tts-voiceclone",
        "mimo-v2.5-tts-voicedesign",
        "mimo-v2.5-tts",
        "mimo-v2-pro",
        "mimo-v2-omni",
        "mimo-v2-tts",
    }.issubset(set(settings.mimo_available_models()))


def test_mimo_available_models_rejects_invalid_json() -> None:
    with pytest.raises(RuntimeError, match="MIMO_AVAILABLE_MODELS_JSON"):
        parse_mimo_available_models("{bad-json")


def test_validate_runtime_requires_default_model_to_be_available() -> None:
    settings = Settings(
        MIMO_API_KEY="test-key",
        MIMO_DEFAULT_MODEL="mimo-v2.5-pro",
        MIMO_AVAILABLE_MODELS_JSON=json.dumps(["mimo-v2.5"]),
    )

    with pytest.raises(RuntimeError, match="MIMO_DEFAULT_MODEL"):
        settings.validate_runtime()
