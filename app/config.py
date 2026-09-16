"""Application configuration loaded from environment variables and `.env`."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for generation, embeddings, retrieval, vision, tools, and persistence."""

    lm_base_url: str = "http://127.0.0.1:1234"
    lm_api_token: str
    gateway_api_key: str

    # `balanced` intentionally preserves the historical Gemma mapping so old
    # benchmark commands remain reproducible. New application code should use
    # `default` or `deep` rather than depending on this legacy profile.
    model_fast: str = "google/gemma-4-12b-qat"
    model_balanced: str = "google/gemma-4-12b-qat"
    model_default: str = "openai/gpt-oss-20b"
    model_deep: str = "openai/gpt-oss-20b"

    reasoning_fast: str | None = None
    reasoning_balanced: str | None = None
    # The September 2026 reasoning benchmark showed low reasoning to be the best
    # everyday latency/quality trade-off, while high is reserved for hard tasks.
    reasoning_default: str | None = "low"
    reasoning_deep: str | None = "high"

    # Stage 5 keeps vision as a separate capability instead of pretending every
    # text profile can accept images. Qwen3-VL-8B is the initial candidate and
    # must pass the committed live vision benchmark before it is called qualified.
    vision_model: str = "qwen/qwen3-vl-8b"
    vision_max_images: int = 4
    vision_max_image_bytes: int = 12 * 1024 * 1024
    vision_max_total_bytes: int = 24 * 1024 * 1024
    vision_max_pixels: int = 64_000_000
    vision_max_side: int = 2048

    # BGE-M3 is the preferred retrieval model because the gateway is intended to
    # handle multilingual personal data. LM Studio model keys can vary by install,
    # so this remains an environment override rather than an application concern.
    embedding_model: str = "text-embedding-bge-m3"
    # Some embedding families (notably Nomic) require task prefixes while BGE-M3
    # does not. Keeping these configurable avoids provider/model-specific logic in
    # the public API and preserves retrieval correctness when the model changes.
    embedding_query_prefix: str = ""
    embedding_document_prefix: str = ""
    embedding_batch_size: int = 16
    embedding_max_input_chars: int = 24000

    default_context_length: int = 16384
    default_max_output_tokens: int = 2048
    structured_max_attempts: int = 2
    lm_timeout_seconds: int = 300

    # Tool calls are deliberately bounded at the gateway boundary. The gateway
    # only validates/model-plans calls; real execution stays in the application.
    tool_max_definitions: int = 32
    tool_max_schema_chars: int = 30000
    tool_max_definitions_chars: int = 100000
    tool_max_calls_per_turn: int = 8
    tool_max_history_messages: int = 100
    tool_max_history_chars: int = 120000
    tool_max_result_chars: int = 50000

    metrics_db_path: Path = Path("data/gateway.db")
    rag_db_path: Path = Path("data/rag.db")
    rag_chunk_size_chars: int = 1200
    rag_chunk_overlap_chars: int = 180
    rag_default_top_k: int = 5
    rag_max_context_chars: int = 12000
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
        """Treat blank `.env` values as an intentionally disabled override."""

        if value == "":
            return None
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
