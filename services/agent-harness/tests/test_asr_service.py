import json

import pytest

from app.audio.asr_service import (
    ASR_MODEL,
    AsrService,
    AsrUpstreamError,
    MissingAudioSourceError,
    UnsupportedAudioFormatError,
    audio_format_for,
    build_anthropic_audio_content,
    build_openai_audio_content,
    normalize_mime_type,
    parse_provider_transcript,
)
from app.core.config import Settings
from app.protocols.schemas import TranscribeAudioRequest, TranscribeAudioResponse


@pytest.mark.asyncio
async def test_mock_asr_transcribes_supported_audio_reference_without_real_call() -> None:
    settings = Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=True)
    service = AsrService(settings)

    result = await service.transcribe(
        TranscribeAudioRequest(
            audio_asset_id="audio_001",
            mime_type="audio/webm;codecs=opus",
            duration_ms=12000,
            language_hint="en",
        )
    )

    assert result.audio_asset_id == "audio_001"
    assert result.asr_text == "Mock IELTS speaking transcript for audio asset audio_001."
    assert result.language == "en"
    assert result.confidence is not None
    assert 0.82 <= result.confidence <= 0.94
    assert result.provider == "mock_asr"
    assert result.model == ASR_MODEL
    assert result.duration_ms == 12000
    assert result.metadata["mock"] is True
    assert result.metadata["mime_type"] == "audio/webm"
    assert result.metadata["source_type"] == "asset_reference"


@pytest.mark.asyncio
async def test_asr_accepts_wav_mp3_and_webm_mime_types() -> None:
    settings = Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=True)
    service = AsrService(settings)

    for mime_type in ["audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/webm", "audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac"]:
        result = await service.transcribe(
            TranscribeAudioRequest(audio_asset_id=f"asset_{mime_type.replace('/', '_')}", mime_type=mime_type)
        )
        assert result.metadata["mime_type"] == normalize_mime_type(mime_type)


@pytest.mark.asyncio
async def test_asr_rejects_unsupported_audio_format() -> None:
    settings = Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=True)
    service = AsrService(settings)

    with pytest.raises(UnsupportedAudioFormatError) as exc:
        await service.transcribe(TranscribeAudioRequest(audio_asset_id="audio_bad", mime_type="video/mp4"))

    assert exc.value.code == "unsupported_audio_format"
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_real_asr_requires_audio_url_or_base64_source() -> None:
    settings = Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=False)
    service = AsrService(settings)

    with pytest.raises(MissingAudioSourceError) as exc:
        await service.transcribe(TranscribeAudioRequest(audio_asset_id="audio_001", mime_type="audio/webm"))

    assert exc.value.code == "missing_audio_source"
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_asr_fails_when_planned_model_is_not_available() -> None:
    settings = Settings(
        MIMO_API_KEY="test-key",
        MOCK_MODEL_ENABLED=True,
        MIMO_AVAILABLE_MODELS_JSON=json.dumps(["mimo-v2.5-pro"]),
    )
    service = AsrService(settings)

    with pytest.raises(AsrUpstreamError) as exc:
        await service.transcribe(TranscribeAudioRequest(audio_asset_id="audio_001", mime_type="audio/webm"))

    assert exc.value.code == "asr_model_unavailable"
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_asr_service_can_use_injected_provider_for_real_boundary() -> None:
    settings = Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=False)
    provider = FakeAsrProvider()
    service = AsrService(settings, provider=provider)

    result = await service.transcribe(
        TranscribeAudioRequest(
            audio_asset_id="audio_real",
            mime_type="audio/wav",
            audio_base64="UklGRg==",
            duration_ms=8000,
        )
    )

    assert provider.calls == [("audio_real", "audio/wav", ASR_MODEL)]
    assert result.asr_text == "I live near a quiet library."
    assert result.provider == "fake_mimo_asr"
    assert result.confidence == 0.91


@pytest.mark.asyncio
async def test_real_asr_uses_local_fallback_when_upstream_rejects_audio_payload() -> None:
    settings = Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=False, APP_ENV="local")
    service = AsrService(settings, provider=FailingAsrProvider())

    result = await service.transcribe(
        TranscribeAudioRequest(
            audio_asset_id="audio_mobile_mp4",
            mime_type="audio/mp4",
            audio_base64="AAAA",
            duration_ms=1800,
            language_hint="en",
        )
    )

    assert result.provider == "fallback_mock_asr"
    assert result.metadata["fallback"] is True
    assert result.metadata["fallback_reason"] == "asr_upstream_error"
    assert result.metadata["mime_type"] == "audio/mp4"
    assert result.metadata["source_type"] == "base64"


@pytest.mark.asyncio
async def test_real_asr_does_not_fallback_in_production() -> None:
    settings = Settings(MIMO_API_KEY="test-key", MOCK_MODEL_ENABLED=False, APP_ENV="prod")
    service = AsrService(settings, provider=FailingAsrProvider())

    with pytest.raises(AsrUpstreamError) as exc:
        await service.transcribe(
            TranscribeAudioRequest(audio_asset_id="audio_prod", mime_type="audio/webm", audio_base64="AAAA")
        )

    assert exc.value.code == "asr_upstream_error"


def test_openai_audio_payload_uses_input_audio_for_base64() -> None:
    content = build_openai_audio_content(
        "Transcribe",
        request=TranscribeAudioRequest(audio_asset_id="audio_001", mime_type="audio/mp3", audio_base64="abc"),
        mime_type="audio/mp3",
    )

    assert content[0]["type"] == "text"
    assert content[1]["type"] == "input_audio"
    assert content[1]["input_audio"]["format"] == "mp3"
    assert content[1]["input_audio"]["data"] == "data:audio/mp3;base64,abc"


def test_openai_audio_payload_maps_mobile_mp4_format() -> None:
    assert audio_format_for("audio/mp4") == "mp4"
    assert audio_format_for("audio/m4a") == "mp4"
    assert audio_format_for("audio/aac") == "aac"


def test_openai_audio_payload_can_omit_text_prompt_for_asr_gateway() -> None:
    content = build_openai_audio_content(
        "Transcribe",
        request=TranscribeAudioRequest(audio_asset_id="audio_001", mime_type="audio/wav", audio_base64="abc"),
        mime_type="audio/wav",
        include_instruction=False,
    )

    assert content == [{"type": "input_audio", "input_audio": {"data": "data:audio/wav;base64,abc", "format": "wav"}}]


def test_anthropic_audio_payload_keeps_media_type_for_base64() -> None:
    content = build_anthropic_audio_content(
        "Transcribe",
        request=TranscribeAudioRequest(audio_asset_id="audio_001", mime_type="audio/webm", audio_base64="abc"),
        mime_type="audio/webm",
    )

    assert content[1]["type"] == "audio"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["media_type"] == "audio/webm"
    assert content[1]["source"]["data"] == "abc"


def test_parse_provider_transcript_accepts_json_and_plain_text() -> None:
    openai_data = {
        "model": ASR_MODEL,
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"asr_text": "I prefer studying in the morning.", "language": "en", "confidence": 0.88}
                    )
                }
            }
        ],
    }
    anthropic_data = {
        "model": ASR_MODEL,
        "content": [{"type": "text", "text": "I usually practise speaking after dinner."}],
    }

    assert parse_provider_transcript(openai_data, api_format="openai") == {
        "asr_text": "I prefer studying in the morning.",
        "language": "en",
        "confidence": 0.88,
        "model": ASR_MODEL,
    }
    assert parse_provider_transcript(anthropic_data, api_format="anthropic")["asr_text"] == (
        "I usually practise speaking after dinner."
    )


class FakeAsrProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def transcribe(
        self,
        request: TranscribeAudioRequest,
        *,
        mime_type: str,
        model: str,
    ) -> TranscribeAudioResponse:
        self.calls.append((request.audio_asset_id, mime_type, model))
        return TranscribeAudioResponse(
            audio_asset_id=request.audio_asset_id,
            asr_text="I live near a quiet library.",
            language="en",
            confidence=0.91,
            provider="fake_mimo_asr",
            model=model,
            duration_ms=request.duration_ms,
            metadata={"mock": False},
        )


class FailingAsrProvider:
    async def transcribe(
        self,
        request: TranscribeAudioRequest,
        *,
        mime_type: str,
        model: str,
    ) -> TranscribeAudioResponse:
        raise AsrUpstreamError("upstream rejected audio payload", code="asr_upstream_error", retryable=False)
