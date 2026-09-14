"""Pydantic request and response models for the public gateway API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.routing import Quality, ReasoningEffort


class GenerateRequest(BaseModel):
    """Free-form generation request resolved through a public quality profile."""

    prompt: str = Field(min_length=1)
    system: str | None = None
    quality: Quality = "default"
    reasoning: ReasoningEffort | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192)


class GenerateResponse(BaseModel):
    """Free-form response plus operational metadata useful for diagnostics."""

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
    """Schema-constrained extraction request with bounded repair attempts."""

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
    """Validated structured data returned by `/v1/extract`."""

    data: Any
    model: str
    profile: str
    reasoning: ReasoningEffort | None = None
    attempts: int
    validated: bool = True
    request_id: str


class ClassifyRequest(BaseModel):
    """Closed-label classification request implemented with an enum JSON schema."""

    text: str = Field(min_length=1)
    labels: list[str] = Field(min_length=2, max_length=100)
    system: str | None = None
    quality: Quality = "default"
    reasoning: ReasoningEffort | None = None
    # A tiny visible answer can still require substantial hidden reasoning. The
    # 512-token floor leaves room for gpt-oss to emit the final constrained label.
    max_output_tokens: int = Field(default=512, ge=128, le=4096)
    max_attempts: int = Field(default=2, ge=1, le=3)

    @field_validator("labels")
    @classmethod
    def labels_must_be_unique(cls, labels: list[str]) -> list[str]:
        """Reject ambiguous label sets before any model request is made."""

        if len(labels) != len(set(labels)):
            raise ValueError("labels must be unique")
        if any(not label.strip() for label in labels):
            raise ValueError("labels cannot be blank")
        return labels


class ClassifyResponse(BaseModel):
    """One validated classification label plus routing metadata."""

    label: str
    model: str
    profile: str
    reasoning: ReasoningEffort | None = None
    attempts: int
    request_id: str


class ErrorBody(BaseModel):
    """Stable fields nested under the public `error` response object."""

    code: str
    message: str
    request_id: str | None = None
    details: Any | None = None


class ErrorResponse(BaseModel):
    """Standard gateway error envelope."""

    error: ErrorBody


class StatusResponse(BaseModel):
    """Gateway and LM Studio status returned by `/v1/status`."""

    gateway: Literal["ok"] = "ok"
    lmstudio: str
    loaded_models: list[str]
    profiles: dict[str, dict[str, str | None]]
