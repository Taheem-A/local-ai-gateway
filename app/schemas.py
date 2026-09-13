from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.routing import Quality, ReasoningEffort


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    system: str | None = None
    quality: Quality = "default"
    reasoning: ReasoningEffort | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192)


class GenerateResponse(BaseModel):
    text: str
    model: str
    profile: str
    quality: Quality
    reasoning: ReasoningEffort | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    tokens_per_second: float | None = None
    time_to_first_token_seconds: float | None = None
    model_load_time_seconds: float | None = None
    request_id: str


class ExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    prompt: str = Field(min_length=1)
    schema_: dict[str, Any] = Field(alias="schema")
    system: str | None = None
    quality: Quality = "default"
    reasoning: ReasoningEffort | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192)
    max_attempts: int = Field(default=2, ge=1, le=3)


class ExtractResponse(BaseModel):
    data: Any
    model: str
    profile: str
    reasoning: ReasoningEffort | None = None
    attempts: int
    validated: bool = True
    request_id: str


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=1)
    labels: list[str] = Field(min_length=2, max_length=100)
    system: str | None = None
    quality: Quality = "default"
    reasoning: ReasoningEffort | None = None
    # 128 tokens was too small for a reasoning model: GPT-OSS could consume the
    # budget in reasoning and leave message.content empty. 512 remains a small
    # ceiling for a one-label answer while leaving enough room for hidden reasoning.
    max_output_tokens: int = Field(default=512, ge=128, le=4096)
    max_attempts: int = Field(default=2, ge=1, le=3)

    @field_validator("labels")
    @classmethod
    def labels_must_be_unique(cls, labels: list[str]) -> list[str]:
        if len(labels) != len(set(labels)):
            raise ValueError("labels must be unique")
        if any(not label.strip() for label in labels):
            raise ValueError("labels cannot be blank")
        return labels


class ClassifyResponse(BaseModel):
    label: str
    model: str
    profile: str
    reasoning: ReasoningEffort | None = None
    attempts: int
    request_id: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class StatusResponse(BaseModel):
    gateway: Literal["ok"] = "ok"
    lmstudio: str
    loaded_models: list[str]
    profiles: dict[str, dict[str, str | None]]
