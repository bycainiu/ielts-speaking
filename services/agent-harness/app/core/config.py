import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MIMO_AVAILABLE_MODELS = [
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2.5-asr",
    "mimo-v2.5-tts-voiceclone",
    "mimo-v2.5-tts-voicedesign",
    "mimo-v2.5-tts",
    "mimo-v2-pro",
    "mimo-v2-omni",
    "mimo-v2-tts",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    mock_model_enabled: bool = Field(default=True, alias="MOCK_MODEL_ENABLED")
    mimo_api_key: str = Field(default="change-me", alias="MIMO_API_KEY")
    mimo_base_url: str = Field(default="https://api.mimo.example/v1", alias="MIMO_BASE_URL")
    mimo_default_model: str = Field(default="mimo-v2.5-pro", alias="MIMO_DEFAULT_MODEL")
    mimo_api_format: str = Field(default="openai", alias="MIMO_API_FORMAT")
    mimo_timeout_seconds: float = Field(default=30.0, alias="MIMO_TIMEOUT_SECONDS")
    mimo_max_retries: int = Field(default=2, alias="MIMO_MAX_RETRIES")
    mimo_model_routes_json: str = Field(default="{}", alias="MIMO_MODEL_ROUTES_JSON")
    mimo_input_cost_usd_per_1k_tokens: float = Field(default=0.0, alias="MIMO_INPUT_COST_USD_PER_1K_TOKENS")
    mimo_output_cost_usd_per_1k_tokens: float = Field(default=0.0, alias="MIMO_OUTPUT_COST_USD_PER_1K_TOKENS")
    mimo_available_models_json: str = Field(
        default=json.dumps(DEFAULT_MIMO_AVAILABLE_MODELS),
        alias="MIMO_AVAILABLE_MODELS_JSON",
    )
    langfuse_enabled: bool = Field(default=False, alias="LANGFUSE_ENABLED")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://langfuse:3000", alias="LANGFUSE_HOST")
    langfuse_timeout_seconds: float = Field(default=3.0, alias="LANGFUSE_TIMEOUT_SECONDS")
    trace_user_hash_salt: str = Field(default="local-trace-salt-change-me", alias="TRACE_USER_HASH_SALT")
    trace_store_limit: int = Field(default=500, alias="TRACE_STORE_LIMIT")
    trace_persistence_enabled: bool = Field(default=False, alias="TRACE_PERSISTENCE_ENABLED")
    trace_database_url: str = Field(default="", alias="TRACE_DATABASE_URL")
    trace_reasoning_retention: str = Field(default="full", alias="TRACE_REASONING_RETENTION")
    agent_stream_buffer_limit: int = Field(default=1000, alias="AGENT_STREAM_BUFFER_LIMIT")
    agent_stream_heartbeat_seconds: float = Field(default=15.0, alias="AGENT_STREAM_HEARTBEAT_SECONDS")
    agent_stream_max_clients_per_run: int = Field(default=8, alias="AGENT_STREAM_MAX_CLIENTS_PER_RUN")
    observability_error_rate_alert_threshold: float = Field(default=0.1, alias="OBSERVABILITY_ERROR_RATE_ALERT_THRESHOLD")
    observability_latency_p95_alert_ms: int = Field(default=5000, alias="OBSERVABILITY_LATENCY_P95_ALERT_MS")
    knowledge_store_backend: str = Field(default="memory", alias="KNOWLEDGE_STORE_BACKEND")
    knowledge_database_url: str = Field(default="", alias="KNOWLEDGE_DATABASE_URL")
    knowledge_embedding_model: str = Field(default="hash-embedding-v1", alias="KNOWLEDGE_EMBEDDING_MODEL")
    knowledge_embedding_dimension: int = Field(default=1536, alias="KNOWLEDGE_EMBEDDING_DIMENSION")
    knowledge_chunk_max_chars: int = Field(default=1200, alias="KNOWLEDGE_CHUNK_MAX_CHARS")
    knowledge_chunk_overlap_chars: int = Field(default=120, alias="KNOWLEDGE_CHUNK_OVERLAP_CHARS")
    document_ingestion_enabled: bool = Field(default=True, alias="DOCUMENT_INGESTION_ENABLED")
    document_ingestion_poll_interval_seconds: float = Field(default=2.0, alias="DOCUMENT_INGESTION_POLL_INTERVAL_SECONDS")
    document_ingestion_worker_id: str = Field(default="", alias="DOCUMENT_INGESTION_WORKER_ID")
    document_ingestion_max_inline_artifact_chars: int = Field(default=16000, alias="DOCUMENT_INGESTION_MAX_INLINE_ARTIFACT_CHARS")
    s3_endpoint: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT")
    s3_region: str = Field(default="local", alias="S3_REGION")
    s3_bucket: str = Field(default="ielts-speaking-local", alias="MINIO_BUCKET")
    s3_access_key: str = Field(default="minioadmin", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="minioadmin", alias="S3_SECRET_KEY")
    s3_use_ssl: bool = Field(default=False, alias="S3_USE_SSL")

    def validate_runtime(self) -> None:
        if self.app_env == "prod" and not self.mock_model_enabled and self.mimo_api_key in {"", "change-me"}:
            raise RuntimeError("生产环境必须配置有效的 MIMO_API_KEY")
        if self.mimo_api_format not in {"openai", "anthropic"}:
            raise RuntimeError("MIMO_API_FORMAT 只能是 openai 或 anthropic")
        if self.mimo_timeout_seconds <= 0:
            raise RuntimeError("MIMO_TIMEOUT_SECONDS 必须大于 0")
        if self.mimo_max_retries < 0:
            raise RuntimeError("MIMO_MAX_RETRIES 不能小于 0")
        if self.mimo_input_cost_usd_per_1k_tokens < 0 or self.mimo_output_cost_usd_per_1k_tokens < 0:
            raise RuntimeError("MIMO token 成本配置不能小于 0")
        try:
            model_routes = json.loads(self.mimo_model_routes_json or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("MIMO_MODEL_ROUTES_JSON 必须是合法 JSON") from exc
        if not isinstance(model_routes, dict):
            raise RuntimeError("MIMO_MODEL_ROUTES_JSON 必须是 JSON 对象")
        available_models = parse_mimo_available_models(self.mimo_available_models_json)
        if self.mimo_default_model not in available_models:
            raise RuntimeError("MIMO_DEFAULT_MODEL 必须存在于 MIMO_AVAILABLE_MODELS_JSON")
        if self.langfuse_enabled and (not self.langfuse_public_key or not self.langfuse_secret_key):
            raise RuntimeError("LANGFUSE_ENABLED=true 时必须配置 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY")
        if self.langfuse_timeout_seconds <= 0:
            raise RuntimeError("LANGFUSE_TIMEOUT_SECONDS 必须大于 0")
        if self.trace_store_limit <= 0:
            raise RuntimeError("TRACE_STORE_LIMIT 必须大于 0")
        if self.trace_persistence_enabled and not (self.trace_database_url or self.knowledge_database_url):
            raise RuntimeError("TRACE_PERSISTENCE_ENABLED=true 时必须配置 TRACE_DATABASE_URL 或 KNOWLEDGE_DATABASE_URL")
        if self.trace_reasoning_retention not in {"full", "summary", "none"}:
            raise RuntimeError("TRACE_REASONING_RETENTION 只能是 full、summary 或 none")
        if self.agent_stream_buffer_limit < 20:
            raise RuntimeError("AGENT_STREAM_BUFFER_LIMIT 必须大于等于 20")
        if self.agent_stream_heartbeat_seconds <= 0:
            raise RuntimeError("AGENT_STREAM_HEARTBEAT_SECONDS 必须大于 0")
        if self.agent_stream_max_clients_per_run <= 0:
            raise RuntimeError("AGENT_STREAM_MAX_CLIENTS_PER_RUN 必须大于 0")
        if self.observability_error_rate_alert_threshold <= 0 or self.observability_error_rate_alert_threshold > 1:
            raise RuntimeError("OBSERVABILITY_ERROR_RATE_ALERT_THRESHOLD 必须在 (0, 1] 范围内")
        if self.observability_latency_p95_alert_ms <= 0:
            raise RuntimeError("OBSERVABILITY_LATENCY_P95_ALERT_MS 必须大于 0")
        if self.app_env == "prod" and self.trace_user_hash_salt == "local-trace-salt-change-me":
            raise RuntimeError("生产环境必须配置 TRACE_USER_HASH_SALT")
        if self.knowledge_store_backend not in {"memory", "pgvector"}:
            raise RuntimeError("KNOWLEDGE_STORE_BACKEND 只能是 memory 或 pgvector")
        if self.knowledge_store_backend == "pgvector" and not self.knowledge_database_url:
            raise RuntimeError("KNOWLEDGE_STORE_BACKEND=pgvector 时必须配置 KNOWLEDGE_DATABASE_URL")
        if self.knowledge_store_backend == "pgvector" and self.knowledge_embedding_dimension != 1536:
            raise RuntimeError("pgvector knowledge_chunks.embedding 当前要求 KNOWLEDGE_EMBEDDING_DIMENSION=1536")
        if self.knowledge_embedding_dimension <= 0:
            raise RuntimeError("KNOWLEDGE_EMBEDDING_DIMENSION 必须大于 0")
        if self.knowledge_chunk_max_chars <= 0:
            raise RuntimeError("KNOWLEDGE_CHUNK_MAX_CHARS 必须大于 0")
        if self.knowledge_chunk_overlap_chars < 0 or self.knowledge_chunk_overlap_chars >= self.knowledge_chunk_max_chars:
            raise RuntimeError("KNOWLEDGE_CHUNK_OVERLAP_CHARS 必须大于等于 0 且小于 KNOWLEDGE_CHUNK_MAX_CHARS")
        if self.document_ingestion_poll_interval_seconds <= 0:
            raise RuntimeError("DOCUMENT_INGESTION_POLL_INTERVAL_SECONDS 必须大于 0")
        if self.document_ingestion_max_inline_artifact_chars < 2000:
            raise RuntimeError("DOCUMENT_INGESTION_MAX_INLINE_ARTIFACT_CHARS 必须大于等于 2000")
        if self.document_ingestion_enabled and self.knowledge_database_url:
            if not self.s3_endpoint:
                raise RuntimeError("DOCUMENT_INGESTION_ENABLED=true 时必须配置 S3_ENDPOINT")
            if not self.s3_access_key or not self.s3_secret_key:
                raise RuntimeError("DOCUMENT_INGESTION_ENABLED=true 时必须配置 S3_ACCESS_KEY/S3_SECRET_KEY")

    def mimo_available_models(self) -> list[str]:
        return parse_mimo_available_models(self.mimo_available_models_json)


def parse_mimo_available_models(raw_value: str) -> list[str]:
    try:
        parsed = json.loads(raw_value or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("MIMO_AVAILABLE_MODELS_JSON 必须是合法 JSON") from exc
    if not isinstance(parsed, list):
        raise RuntimeError("MIMO_AVAILABLE_MODELS_JSON 必须是 JSON 数组")

    models: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError("MIMO_AVAILABLE_MODELS_JSON 只能包含非空模型名字符串")
        model = item.strip()
        if model not in models:
            models.append(model)
    if not models:
        raise RuntimeError("MIMO_AVAILABLE_MODELS_JSON 至少需要包含一个模型")
    return models


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
