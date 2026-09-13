from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    lm_base_url: str = "http://127.0.0.1:1234"
    lm_api_token: str
    gateway_api_key: str

    model_default: str = "google/gemma-4-12b-qat"
    model_deep: str = "openai/gpt-oss-20b"

    default_context_length: int = 16384
    lm_timeout_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


settings = Settings() # pyright: ignore[reportCallIssue]