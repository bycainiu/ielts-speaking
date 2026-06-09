import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.protocols.schemas import TranscribeAudioRequest, TranscribeAudioResponse


ASR_MODEL = "mimo-v2.5-asr"
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/aac",
    "audio/m4a",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "audio/x-m4a",
}


class AsrServiceError(Exception):
    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class UnsupportedAudioFormatError(AsrServiceError):
    def __init__(self, mime_type: str) -> None:
        super().__init__(
            f"不支持的音频格式：{mime_type}",
            code="unsupported_audio_format",
            retryable=False,
        )
        self.mime_type = mime_type


class MissingAudioSourceError(AsrServiceError):
    def __init__(self) -> None:
        super().__init__(
            "真实 ASR 调用需要 audio_url 或 audio_base64",
            code="missing_audio_source",
            retryable=False,
        )


class AsrUpstreamError(AsrServiceError):
    def __init__(self, message: str, *, code: str = "asr_upstream_error", retryable: bool = True) -> None:
        super().__init__(message, code=code, retryable=retryable)


class AsrProvider(Protocol):
    async def transcribe(self, request: TranscribeAudioRequest, *, mime_type: str, model: str) -> TranscribeAudioResponse:
        ...


class AsrService:
    def __init__(self, settings: Settings, provider: AsrProvider | None = None) -> None:
        self._settings = settings
        self._model = ASR_MODEL
        self._provider = provider or self._provider_from_settings(settings)

    async def transcribe(self, request: TranscribeAudioRequest) -> TranscribeAudioResponse:
        mime_type = normalize_mime_type(request.mime_type)
        if mime_type not in SUPPORTED_AUDIO_MIME_TYPES:
            raise UnsupportedAudioFormatError(request.mime_type)
        if self._model not in self._settings.mimo_available_models():
            raise AsrUpstreamError(
                f"{self._model} 未配置在 MIMO_AVAILABLE_MODELS_JSON 中",
                code="asr_model_unavailable",
                retryable=False,
            )
        if not self._settings.mock_model_enabled and not (request.audio_url or request.audio_base64):
            raise MissingAudioSourceError()
        try:
            return await self._provider.transcribe(request, mime_type=mime_type, model=self._model)
        except AsrUpstreamError as exc:
            if self._settings.app_env != "prod" and not self._settings.mock_model_enabled:
                return await MockAsrProvider(
                    provider="fallback_mock_asr",
                    metadata_extra={
                        "fallback": True,
                        "fallback_reason": exc.code,
                        "upstream_retryable": exc.retryable,
                    },
                ).transcribe(request, mime_type=mime_type, model=self._model)
            raise

    def _provider_from_settings(self, settings: Settings) -> AsrProvider:
        if settings.mock_model_enabled:
            return MockAsrProvider()
        return MiMoAsrProvider(
            config=MiMoAsrConfig(
                api_key=settings.mimo_api_key,
                base_url=settings.mimo_base_url,
                api_format=settings.mimo_api_format,
                timeout_seconds=settings.mimo_timeout_seconds,
                max_retries=settings.mimo_max_retries,
            )
        )


class MockAsrProvider:
    def __init__(self, *, provider: str = "mock_asr", metadata_extra: dict[str, Any] | None = None) -> None:
        self._provider = provider
        self._metadata_extra = metadata_extra or {}

    async def transcribe(self, request: TranscribeAudioRequest, *, mime_type: str, model: str) -> TranscribeAudioResponse:
        confidence = stable_mock_confidence(request.audio_asset_id)
        language = request.language_hint or "en"
        return TranscribeAudioResponse(
            audio_asset_id=request.audio_asset_id,
            asr_text=f"Mock IELTS speaking transcript for audio asset {request.audio_asset_id}.",
            language=language,
            confidence=confidence,
            provider=self._provider,
            model=model,
            duration_ms=request.duration_ms,
            metadata={
                "mock": True,
                "mime_type": mime_type,
                "format_strategy": "provider_compatible",
                "source_type": source_type_for(request),
                **self._metadata_extra,
            },
        )


@dataclass(frozen=True)
class MiMoAsrConfig:
    api_key: str
    base_url: str
    api_format: str
    timeout_seconds: float
    max_retries: int
    retry_base_seconds: float = 0.2


class MiMoAsrProvider:
    def __init__(self, config: MiMoAsrConfig, http_client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=config.timeout_seconds)

    async def transcribe(self, request: TranscribeAudioRequest, *, mime_type: str, model: str) -> TranscribeAudioResponse:
        payload = self._build_payload(request, mime_type=mime_type, model=model)
        data = await self._post_json(self._endpoint(), payload)
        parsed = parse_provider_transcript(data, api_format=self._config.api_format)
        return TranscribeAudioResponse(
            audio_asset_id=request.audio_asset_id,
            asr_text=parsed["asr_text"],
            language=parsed.get("language") or request.language_hint or "en",
            confidence=parsed.get("confidence"),
            provider="mimo_asr",
            model=str(parsed.get("model") or model),
            duration_ms=request.duration_ms,
            metadata={
                "mock": False,
                "mime_type": mime_type,
                "format_strategy": "provider_compatible",
                "source_type": source_type_for(request),
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

    def _build_payload(self, request: TranscribeAudioRequest, *, mime_type: str, model: str) -> dict[str, Any]:
        instruction = (
            "Transcribe this IELTS Speaking answer. Return compact JSON with keys "
            "asr_text, language, and confidence. Do not add feedback or scoring."
        )
        if self._config.api_format == "anthropic":
            return {
                "model": model,
                "max_tokens": 1200,
                "messages": [
                    {
                        "role": "user",
                        "content": build_anthropic_audio_content(
                            instruction,
                            request=request,
                            mime_type=mime_type,
                        ),
                    }
                ],
            }
        return {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": build_openai_audio_content(
                        instruction,
                        request=request,
                        mime_type=mime_type,
                        include_instruction=False,
                    ),
                }
            ],
            "temperature": 0,
        }

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async def operation() -> dict[str, Any]:
            response = await self._client.post(url, headers=self._headers(), json=payload)
            if response.status_code >= 400:
                raise asr_error_from_response(response)
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise AsrUpstreamError(str(exc), code="invalid_asr_response", retryable=False) from exc

        return await self._with_retries(operation)

    async def _with_retries(self, operation: Any) -> Any:
        last_error: AsrServiceError | None = None
        attempts = self._config.max_retries + 1
        for attempt in range(attempts):
            try:
                return await operation()
            except httpx.TimeoutException as exc:
                last_error = AsrUpstreamError(str(exc) or "ASR request timed out", code="timeout", retryable=True)
            except httpx.TransportError as exc:
                last_error = AsrUpstreamError(str(exc), code="network_error", retryable=True)
            except AsrServiceError as exc:
                last_error = exc

            if not last_error.retryable or attempt == attempts - 1:
                raise last_error
            await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))

        raise last_error or AsrUpstreamError("ASR request failed", retryable=False)


def normalize_mime_type(mime_type: str) -> str:
    return mime_type.split(";", 1)[0].strip().lower()


def source_type_for(request: TranscribeAudioRequest) -> str:
    if request.audio_base64:
        return "base64"
    if request.audio_url:
        return "url"
    return "asset_reference"


def stable_mock_confidence(audio_asset_id: str) -> float:
    digest = hashlib.sha256(audio_asset_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:2], 16) / 255
    return round(0.82 + bucket * 0.12, 2)


def audio_format_for(mime_type: str) -> str:
    if mime_type in {"audio/mp4", "audio/m4a", "audio/x-m4a"}:
        return "mp4"
    if mime_type == "audio/aac":
        return "aac"
    if mime_type in {"audio/wav", "audio/x-wav"}:
        return "wav"
    if mime_type in {"audio/mpeg", "audio/mp3"}:
        return "mp3"
    if mime_type == "audio/webm":
        return "webm"
    return "audio"


def build_openai_audio_content(
    instruction: str,
    *,
    request: TranscribeAudioRequest,
    mime_type: str,
    include_instruction: bool = True,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if include_instruction:
        content.append({"type": "text", "text": instruction})
    if request.audio_base64:
        content.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": audio_data_url(request.audio_base64, mime_type),
                    "format": audio_format_for(mime_type),
                },
            }
        )
    elif request.audio_url:
        content.append({"type": "audio_url", "audio_url": {"url": request.audio_url}})
    return content


def audio_data_url(audio_base64: str, mime_type: str) -> str:
    stripped = audio_base64.strip()
    if stripped.startswith("data:"):
        return stripped
    return f"data:{mime_type};base64,{stripped}"


def build_anthropic_audio_content(
    instruction: str,
    *,
    request: TranscribeAudioRequest,
    mime_type: str,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": instruction}]
    if request.audio_base64:
        content.append(
            {
                "type": "audio",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": request.audio_base64,
                },
            }
        )
    elif request.audio_url:
        content.append({"type": "audio", "source": {"type": "url", "url": request.audio_url}})
    return content


def parse_provider_transcript(data: dict[str, Any], *, api_format: str) -> dict[str, Any]:
    model = data.get("model")
    if api_format == "anthropic":
        text = parse_anthropic_text(data)
    else:
        text = parse_openai_text(data)
    parsed = parse_json_object_from_text(text)
    if parsed is None:
        asr_text = text.strip()
        parsed = {}
    else:
        asr_text = str(parsed.get("asr_text") or parsed.get("transcript") or "").strip()
    if not asr_text:
        raise AsrUpstreamError("ASR response did not include transcript text", code="invalid_asr_response", retryable=False)
    confidence = parsed.get("confidence")
    return {
        "asr_text": asr_text,
        "language": parsed.get("language"),
        "confidence": confidence if isinstance(confidence, (int, float)) else None,
        "model": model,
    }


def parse_openai_text(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AsrUpstreamError("OpenAI-compatible ASR response shape is invalid", code="invalid_asr_response", retryable=False) from exc
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise AsrUpstreamError("OpenAI-compatible ASR content is invalid", code="invalid_asr_response", retryable=False)
    return content


def parse_anthropic_text(data: dict[str, Any]) -> str:
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise AsrUpstreamError("Anthropic-compatible ASR response shape is invalid", code="invalid_asr_response", retryable=False)
    parts = [str(block.get("text") or "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
    return "".join(parts)


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


def asr_error_from_response(response: httpx.Response) -> AsrUpstreamError:
    message = response.text
    try:
        body = response.json()
        error = body.get("error", body)
        if isinstance(error, dict):
            message = str(error.get("message") or message)
    except json.JSONDecodeError:
        pass
    if response.status_code in {401, 403}:
        return AsrUpstreamError(message or "ASR authentication failed", code="auth_error", retryable=False)
    if response.status_code == 429 or response.status_code >= 500:
        return AsrUpstreamError(message or "ASR upstream error", retryable=True)
    return AsrUpstreamError(message or "ASR request failed", retryable=False)
