from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    lm_base_url: str = "http://127.0.0.1:1234"
    lm_api_token: str
    gateway_api_key: str

    # Profile mappings. `balanced` intentionally preserves the historical Gemma
    # benchmark mapping until that profile is explicitly retired in a future version.
    model_fast: str = "google/gemma-4-12b-qat"
    model_balanced: str = "google/gemma-4-12b-qat"
    model_default: str = "openai/gpt-oss-20b"
    model_deep: str = "openai/gpt-oss-20b"

    reasoning_fast: str | None = None
    reasoning_balanced: str | None = None
    reasoning_default: str | None = "medium"
    # Keep deep at the benchmarked medium setting until low/medium/high is measured.
    reasoning_deep: str | None = "medium"

    default_context_length: int = 16384
    default_max_output_tokens: int = 2048
    structured_max_attempts: int = 2
    lm_timeout_seconds: int = 300

    metrics_db_path: Path = Path("data/gateway.db")
    log_prompt_content: bool = False

    @field_validator(
        "reasoning_fast",
        "reasoning_balanced",
        "reasoning_default",
        "reasoning_deep",
        mode="before",
    )
    @classmethod
    def blank_reasoning_is_none(cls, value):
        if value == "":
            return None
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
