import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MIMO_AVAILABLE_MODELS = [
    "mimo-v2.5-pro",
    "mimo-v2.5",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    agent_orchestrator_port: int = Field(default=8100, alias="AGENT_ORCHESTRATOR_PORT")
    agent_harness_fallback_url: str = Field(
        default="http://agent-harness:8000",
        alias="AGENT_HARNESS_FALLBACK_URL",
    )
    mock_model_enabled: bool = Field(default=True, alias="MOCK_MODEL_ENABLED")
    mimo_api_key: str = Field(default="change-me", alias="MIMO_API_KEY")
    mimo_base_url: str = Field(default="https://api.mimo.example/v1", alias="MIMO_BASE_URL")
    mimo_default_model: str = Field(default="mimo-v2.5-pro", alias="MIMO_DEFAULT_MODEL")
    mimo_api_format: str = Field(default="openai", alias="MIMO_API_FORMAT")
    mimo_timeout_seconds: float = Field(default=30.0, alias="MIMO_TIMEOUT_SECONDS")
    mimo_max_retries: int = Field(default=2, alias="MIMO_MAX_RETRIES")
    mimo_model_routes_json: str = Field(default="{}", alias="MIMO_MODEL_ROUTES_JSON")
    trace_user_hash_salt: str = Field(default="local-trace-salt-change-me", alias="TRACE_USER_HASH_SALT")
    trace_store_limit: int = Field(default=500, alias="TRACE_STORE_LIMIT")
    trace_persistence_enabled: bool = Field(default=False, alias="TRACE_PERSISTENCE_ENABLED")
    trace_database_url: str = Field(default="", alias="TRACE_DATABASE_URL")
    trace_reasoning_retention: str = Field(default="full", alias="TRACE_REASONING_RETENTION")
    agent_stream_buffer_limit: int = Field(default=1000, alias="AGENT_STREAM_BUFFER_LIMIT")
    agent_stream_heartbeat_seconds: float = Field(default=15.0, alias="AGENT_STREAM_HEARTBEAT_SECONDS")
    agent_stream_max_clients_per_run: int = Field(default=8, alias="AGENT_STREAM_MAX_CLIENTS_PER_RUN")
    orchestrator_tool_loop_max_iterations: int = Field(default=5, alias="ORCHESTRATOR_TOOL_LOOP_MAX_ITERATIONS")
    orchestrator_agent_timeout_seconds: float = Field(default=30.0, alias="ORCHESTRATOR_AGENT_TIMEOUT_SECONDS")
    knowledge_store_backend: str = Field(default="memory", alias="KNOWLEDGE_STORE_BACKEND")
    knowledge_database_url: str = Field(default="", alias="KNOWLEDGE_DATABASE_URL")

    def validate_runtime(self) -> None:
        if self.app_env == "prod" and not self.mock_model_enabled and self.mimo_api_key in {"", "change-me"}:
            raise RuntimeError("生产环境必须配置有效的 MIMO_API_KEY")
        if self.mimo_api_format not in {"openai", "anthropic"}:
            raise RuntimeError("MIMO_API_FORMAT 只能是 openai 或 anthropic")
        if self.trace_reasoning_retention not in {"full", "summary", "none"}:
            raise RuntimeError("TRACE_REASONING_RETENTION 只能是 full、summary 或 none")

    def mimo_available_models(self) -> list[str]:
        try:
            parsed = json.loads(self.mimo_model_routes_json or "{}")
            if isinstance(parsed, dict):
                models = {self.mimo_default_model}
                for route in parsed.values():
                    if isinstance(route, dict) and route.get("model"):
                        models.add(str(route["model"]))
                return sorted(models)
        except json.JSONDecodeError:
            pass
        return list(DEFAULT_MIMO_AVAILABLE_MODELS)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
