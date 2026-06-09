import base64
import json
import wave
from io import BytesIO

import pytest

from app.audio.tts_service import TTS_MODEL, TTSService, TTSUpstreamError, parse_tts_provider_response
from app.core.config import Settings
from app.protocols.schemas import SynthesizeSpeechRequest, SynthesizeSpeechResponse


@pytest.mark.asyncio
async def test_mock_tts_synthesizes_examiner_audio() -> None:
    service = TTSService(Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=True))

    result = await service.synthesize(
        SynthesizeSpeechRequest(
            text="Let's talk about your hometown.",
            voice_id="examiner_voice_a",
            speaking_rate=1.1,
            emotion="calm",
            style="examiner",
        )
    )

    assert result.text == "Let's talk about your hometown."
    assert result.provider == "mock_tts"
    assert result.model == TTS_MODEL
    assert result.voice_id == "examiner_voice_a"
    assert result.mime_type == "audio/wav"
    assert result.duration_ms is not None
    assert result.metadata["mock"] is True
    audio = base64.b64decode(result.audio_base64)
    with wave.open(BytesIO(audio), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 8000


@pytest.mark.asyncio
async def test_tts_fails_when_planned_model_is_not_available() -> None:
    settings = Settings(
        MIMO_API_KEY="test-key",
        MOCK_MODEL_ENABLED=True,
        MIMO_AVAILABLE_MODELS_JSON=json.dumps(["mimo-v2.5-pro"]),
    )
    service = TTSService(settings)

    with pytest.raises(TTSUpstreamError) as exc:
        await service.synthesize(SynthesizeSpeechRequest(text="Where do you live?"))

    assert exc.value.code == "tts_model_unavailable"
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_tts_service_can_use_injected_provider_for_real_boundary() -> None:
    provider = FakeTTSProvider()
    service = TTSService(Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=False), provider=provider)

    result = await service.synthesize(SynthesizeSpeechRequest(text="What do you do?", voice_id="voice_real"))

    assert provider.calls == [("What do you do?", "voice_real", TTS_MODEL)]
    assert result.provider == "fake_mimo_tts"
    assert result.audio_base64 == "UklGRg=="


def test_parse_tts_provider_response_accepts_openai_and_anthropic_json() -> None:
    openai_data = {
        "model": TTS_MODEL,
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"audio_base64": "UklGRg==", "mime_type": "audio/wav", "duration_ms": 900}
                    )
                }
            }
        ],
    }
    anthropic_data = {
        "model": TTS_MODEL,
        "content": [{"type": "text", "text": json.dumps({"audio_base64": "UklGRg==", "mime_type": "audio/wav"})}],
    }

    assert parse_tts_provider_response(openai_data, api_format="openai") == {
        "audio_base64": "UklGRg==",
        "mime_type": "audio/wav",
        "duration_ms": 900,
        "model": TTS_MODEL,
    }
    assert parse_tts_provider_response(anthropic_data, api_format="anthropic")["audio_base64"] == "UklGRg=="


def test_parse_tts_provider_response_accepts_openai_audio_payload() -> None:
    openai_audio_data = {
        "model": TTS_MODEL,
        "choices": [
            {
                "message": {
                    "content": "",
                    "role": "assistant",
                    "audio": {"id": "audio_001", "data": "UklGRg=="},
                }
            }
        ],
    }

    assert parse_tts_provider_response(openai_audio_data, api_format="openai") == {
        "audio_base64": "UklGRg==",
        "mime_type": "audio/wav",
        "duration_ms": None,
        "model": TTS_MODEL,
    }


class FakeTTSProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def synthesize(self, request: SynthesizeSpeechRequest, *, model: str) -> SynthesizeSpeechResponse:
        self.calls.append((request.text, request.voice_id, model))
        return SynthesizeSpeechResponse(
            text=request.text,
            audio_base64="UklGRg==",
            mime_type="audio/wav",
            provider="fake_mimo_tts",
            model=model,
            voice_id=request.voice_id,
            duration_ms=1000,
            metadata={"mock": False},
        )
