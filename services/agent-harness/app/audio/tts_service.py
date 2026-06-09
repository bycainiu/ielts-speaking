import asyncio
import base64
import json
import math
import struct
import wave
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.protocols.schemas import SynthesizeSpeechRequest, SynthesizeSpeechResponse


TTS_MODEL = "mimo-v2.5-tts"
DEFAULT_TTS_MIME_TYPE = "audio/wav"


class TTSServiceError(Exception):
    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class TTSUpstreamError(TTSServiceError):
    def __init__(self, message: str, *, code: str = "tts_upstream_error", retryable: bool = True) -> None:
        super().__init__(message, code=code, retryable=retryable)


class TTSProvider(Protocol):
    async def synthesize(self, request: SynthesizeSpeechRequest, *, model: str) -> SynthesizeSpeechResponse:
        ...


class TTSService:
    def __init__(self, settings: Settings, provider: TTSProvider | None = None) -> None:
        self._settings = settings
        self._model = TTS_MODEL
        self._provider = provider or self._provider_from_settings(settings)

    async def synthesize(self, request: SynthesizeSpeechRequest) -> SynthesizeSpeechResponse:
        if self._model not in self._settings.mimo_available_models():
            raise TTSUpstreamError(
                f"{self._model} 未配置在 MIMO_AVAILABLE_MODELS_JSON 中",
                code="tts_model_unavailable",
                retryable=False,
            )
        return await self._provider.synthesize(request, model=self._model)

    def _provider_from_settings(self, settings: Settings) -> TTSProvider:
        if settings.mock_model_enabled:
            return MockTTSProvider()
        return MiMoTTSProvider(
            config=MiMoTTSConfig(
                api_key=settings.mimo_api_key,
                base_url=settings.mimo_base_url,
                api_format=settings.mimo_api_format,
                timeout_seconds=settings.mimo_timeout_seconds,
                max_retries=settings.mimo_max_retries,
            )
        )


class MockTTSProvider:
    async def synthesize(self, request: SynthesizeSpeechRequest, *, model: str) -> SynthesizeSpeechResponse:
        duration_ms = estimate_tts_duration_ms(request.text, request.speaking_rate)
        audio = generate_mock_wav(duration_ms=duration_ms)
        return SynthesizeSpeechResponse(
            text=request.text,
            audio_base64=base64.b64encode(audio).decode("ascii"),
            mime_type=DEFAULT_TTS_MIME_TYPE,
            provider="mock_tts",
            model=model,
            voice_id=request.voice_id,
            duration_ms=duration_ms,
            metadata={
                "mock": True,
                "speaking_rate": request.speaking_rate,
                "emotion": request.emotion,
                "style": request.style,
                "format_strategy": "provider_compatible",
            },
        )


@dataclass(frozen=True)
class MiMoTTSConfig:
    api_key: str
    base_url: str
    api_format: str
    timeout_seconds: float
    max_retries: int
    retry_base_seconds: float = 0.2


class MiMoTTSProvider:
    def __init__(self, config: MiMoTTSConfig, http_client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=config.timeout_seconds)

    async def synthesize(self, request: SynthesizeSpeechRequest, *, model: str) -> SynthesizeSpeechResponse:
        payload = self._build_payload(request, model=model)
        data = await self._post_json(self._endpoint(), payload)
        parsed = parse_tts_provider_response(data, api_format=self._config.api_format)
        return SynthesizeSpeechResponse(
            text=request.text,
            audio_base64=parsed["audio_base64"],
            mime_type=parsed.get("mime_type") or DEFAULT_TTS_MIME_TYPE,
            provider="mimo_tts",
            model=str(parsed.get("model") or model),
            voice_id=request.voice_id,
            duration_ms=parsed.get("duration_ms"),
            metadata={
                "mock": False,
                "speaking_rate": request.speaking_rate,
                "emotion": request.emotion,
                "style": request.style,
                "format_strategy": "provider_compatible",
                "retryable_on_failure": True,
            },
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _endpoint(self) -> str:
        base_url = self._config.base_url.rstrip("/")
        if self._config.api_format == "anthropic":
            return f"{base_url}/messages"
        return f"{base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        if self._config.api_format == "anthropic":
            headers["x-api-key"] = self._config.api_key
            headers["anthropic-version"] = "2023-06-01"
        return headers

    def _build_payload(self, request: SynthesizeSpeechRequest, *, model: str) -> dict[str, Any]:
        instruction = (
            "Synthesize IELTS examiner speech for the given text. Return compact JSON with "
            "audio_base64, mime_type, and duration_ms. Do not include API keys or prompt text."
        )
        content = {
            "text": request.text,
            "voice_id": request.voice_id,
            "speaking_rate": request.speaking_rate,
            "emotion": request.emotion,
            "style": request.style,
            "output_format": "wav",
        }
        if self._config.api_format == "anthropic":
            return {
                "model": model,
                "max_tokens": 1600,
                "messages": [{"role": "user", "content": f"{instruction}\n\n{json.dumps(content, ensure_ascii=False)}"}],
            }
        return {
            "model": model,
            "messages": [{"role": "assistant", "content": request.text}],
            "temperature": 0,
        }

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async def operation() -> dict[str, Any]:
            response = await self._client.post(url, headers=self._headers(), json=payload)
            if response.status_code >= 400:
                raise tts_error_from_response(response)
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise TTSUpstreamError(str(exc), code="invalid_tts_response", retryable=False) from exc

        return await self._with_retries(operation)

    async def _with_retries(self, operation: Any) -> Any:
        last_error: TTSServiceError | None = None
        attempts = self._config.max_retries + 1
        for attempt in range(attempts):
            try:
                return await operation()
            except httpx.TimeoutException as exc:
                last_error = TTSUpstreamError(str(exc) or "TTS request timed out", code="timeout", retryable=True)
            except httpx.TransportError as exc:
                last_error = TTSUpstreamError(str(exc), code="network_error", retryable=True)
            except TTSServiceError as exc:
                last_error = exc

            if not last_error.retryable or attempt == attempts - 1:
                raise last_error
            await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))

        raise last_error or TTSUpstreamError("TTS request failed", retryable=False)


def estimate_tts_duration_ms(text: str, speaking_rate: float) -> int:
    words = max(1, len(text.split()))
    words_per_minute = max(80.0, min(210.0, 145.0 * speaking_rate))
    return max(600, int(words / words_per_minute * 60_000))


def generate_mock_wav(*, duration_ms: int) -> bytes:
    sample_rate = 8000
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(frame_count):
            sample = int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            wav.writeframesraw(struct.pack("<h", sample))
    return buffer.getvalue()


def parse_tts_provider_response(data: dict[str, Any], *, api_format: str) -> dict[str, Any]:
    model = data.get("model")
    if api_format == "openai":
        audio_payload = parse_openai_audio_payload(data)
        if audio_payload is not None:
            return {
                "audio_base64": audio_payload["audio_base64"],
                "mime_type": audio_payload.get("mime_type"),
                "duration_ms": audio_payload.get("duration_ms"),
                "model": model,
            }
    text = parse_anthropic_text(data) if api_format == "anthropic" else parse_openai_text(data)
    parsed = parse_json_object_from_text(text)
    if parsed is None:
        raise TTSUpstreamError("TTS response did not include JSON audio payload", code="invalid_tts_response", retryable=False)
    audio_base64 = str(parsed.get("audio_base64") or parsed.get("audio") or "").strip()
    if not audio_base64:
        raise TTSUpstreamError("TTS response did not include audio_base64", code="invalid_tts_response", retryable=False)
    duration_ms = parsed.get("duration_ms")
    return {
        "audio_base64": audio_base64,
        "mime_type": parsed.get("mime_type"),
        "duration_ms": duration_ms if isinstance(duration_ms, int) and duration_ms > 0 else None,
        "model": model,
    }


def parse_openai_audio_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TTSUpstreamError("OpenAI-compatible TTS response shape is invalid", code="invalid_tts_response", retryable=False) from exc
    audio = message.get("audio")
    if not isinstance(audio, dict):
        return None
    audio_base64 = str(audio.get("data") or "").strip()
    if not audio_base64:
        raise TTSUpstreamError("OpenAI-compatible TTS audio payload is empty", code="invalid_tts_response", retryable=False)
    duration_ms = audio.get("duration_ms")
    return {
        "audio_base64": audio_base64,
        "mime_type": audio.get("mime_type") or DEFAULT_TTS_MIME_TYPE,
        "duration_ms": duration_ms if isinstance(duration_ms, int) and duration_ms > 0 else None,
    }


def parse_openai_text(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise TTSUpstreamError("OpenAI-compatible TTS response shape is invalid", code="invalid_tts_response", retryable=False) from exc
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise TTSUpstreamError("OpenAI-compatible TTS content is invalid", code="invalid_tts_response", retryable=False)
    return content


def parse_anthropic_text(data: dict[str, Any]) -> str:
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise TTSUpstreamError("Anthropic-compatible TTS response shape is invalid", code="invalid_tts_response", retryable=False)
    return "".join(str(block.get("text") or "") for block in blocks if isinstance(block, dict) and block.get("type") == "text")


def parse_json_object_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def tts_error_from_response(response: httpx.Response) -> TTSUpstreamError:
    message = response.text
    try:
        body = response.json()
        error = body.get("error", body)
        if isinstance(error, dict):
            message = str(error.get("message") or message)
    except json.JSONDecodeError:
        pass
    if response.status_code in {401, 403}:
        return TTSUpstreamError(message or "TTS authentication failed", code="auth_error", retryable=False)
    if response.status_code == 429 or response.status_code >= 500:
        return TTSUpstreamError(message or "TTS upstream error", retryable=True)
    return TTSUpstreamError(message or "TTS request failed", retryable=False)
