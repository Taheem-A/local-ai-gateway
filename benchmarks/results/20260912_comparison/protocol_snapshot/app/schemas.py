from typing import Literal
from pydantic import BaseModel, Field


Quality = Literal["fast", "balanced", "deep"]


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)

    system: str | None = None

    quality: Quality = "balanced"

    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
    )

    max_output_tokens: int = Field(
        default=1024,
        ge=1,
        le=8192,
    )


class GenerateResponse(BaseModel):
    text: str

    model: str

    quality: Quality

    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None

    tokens_per_second: float | None = None
    time_to_first_token_seconds: float | None = None
    model_load_time_seconds: float | None = None
