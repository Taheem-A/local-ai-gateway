"""Pydantic request and response models for the public gateway API."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings
from app.routing import Quality, ReasoningEffort

JsonScalar = str | int | float | bool | None
EmbeddingPurpose = Literal["raw", "query", "document"]
ToolChoice = Literal["auto", "none", "required"]
ToolRisk = Literal["read", "write", "destructive"]


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


class ToolDefinition(BaseModel):
    """Caller-advertised function signature plus local execution-risk metadata."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=2000)
    parameters: dict[str, Any]
    risk: ToolRisk = "read"


class ToolHistoryCall(BaseModel):
    """Normalized tool call stored in stateless conversation history."""

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    arguments: dict[str, Any]


class ToolUserMessage(BaseModel):
    """User-authored message in a tool-capable stateless conversation."""

    role: Literal["user"] = "user"
    content: str = Field(min_length=1, max_length=50000)


class ToolAssistantMessage(BaseModel):
    """Assistant text and/or tool calls that can be appended to the next turn."""

    role: Literal["assistant"] = "assistant"
    content: str | None = Field(default=None, max_length=50000)
    tool_calls: list[ToolHistoryCall] = Field(
        default_factory=list,
        max_length=settings.tool_max_calls_per_turn,
    )

    @model_validator(mode="after")
    def require_content_or_calls(self) -> "ToolAssistantMessage":
        """Reject empty assistant messages that cannot advance a conversation."""

        if not self.tool_calls and not (self.content and self.content.strip()):
            raise ValueError("assistant message must contain text or at least one tool call")
        return self


class ToolResultMessage(BaseModel):
    """Application-provided result for one previously requested tool call."""

    role: Literal["tool"] = "tool"
    tool_call_id: str = Field(min_length=1, max_length=128)
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    content: Any


ToolConversationMessage = Annotated[
    ToolUserMessage | ToolAssistantMessage | ToolResultMessage,
    Field(discriminator="role"),
]


class ToolTurnRequest(BaseModel):
    """One stateless model turn with caller-owned tool definitions."""

    messages: list[ToolConversationMessage] = Field(
        min_length=1,
        max_length=settings.tool_max_history_messages,
    )
    tools: list[ToolDefinition] = Field(
        min_length=1,
        max_length=settings.tool_max_definitions,
    )
    system: str | None = Field(default=None, max_length=20000)
    quality: Quality = "default"
    reasoning: ReasoningEffort | None = None
    tool_choice: ToolChoice = "auto"
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=2048, ge=128, le=8192)

    @model_validator(mode="after")
    def unique_tool_names(self) -> "ToolTurnRequest":
        """Keep provider name normalization from creating ambiguous dispatch."""

        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("tool names must be unique")
        return self


class RequestedToolCall(ToolHistoryCall):
    """Validated model request annotated with the caller-declared risk level."""

    risk: ToolRisk


class ToolTurnResponse(BaseModel):
    """Normalized result of exactly one model tool-planning/synthesis turn."""

    status: Literal["completed", "tool_calls"]
    text: str | None = None
    tool_calls: list[RequestedToolCall]
    assistant_message: ToolAssistantMessage
    model: str
    profile: str
    reasoning: ReasoningEffort | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    finish_reason: str | None = None
    request_id: str


class EmbeddingRequest(BaseModel):
    """Generate dense vectors independently of the RAG index."""

    input: str | list[str]
    purpose: EmbeddingPurpose = "raw"

    @field_validator("input")
    @classmethod
    def validate_inputs(cls, value: str | list[str]) -> str | list[str]:
        inputs = [value] if isinstance(value, str) else value
        if not inputs or len(inputs) > 128:
            raise ValueError("input must contain between 1 and 128 strings")
        if any(not isinstance(item, str) or not item.strip() for item in inputs):
            raise ValueError("embedding inputs cannot be blank")
        return value


class EmbeddingResponse(BaseModel):
    """Dense embedding vectors plus provider metadata."""

    embeddings: list[list[float]]
    model: str
    dimensions: int
    input_tokens: int | None = None
    request_id: str


class RagDocument(BaseModel):
    """A logical source document to chunk and index."""

    id: str | None = None
    text: str = Field(min_length=1, max_length=2_000_000)
    source: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def nonblank_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("document id cannot be blank")
        return value


class RagIndexRequest(BaseModel):
    """Chunk and replace one or more documents inside a named collection."""

    collection: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    documents: list[RagDocument] = Field(min_length=1, max_length=100)
    chunk_size_chars: int | None = Field(default=None, ge=200, le=8000)
    chunk_overlap_chars: int | None = Field(default=None, ge=0, le=4000)

    @model_validator(mode="after")
    def validate_chunking(self) -> "RagIndexRequest":
        size = self.chunk_size_chars or settings.rag_chunk_size_chars
        overlap = (
            self.chunk_overlap_chars
            if self.chunk_overlap_chars is not None
            else settings.rag_chunk_overlap_chars
        )
        if overlap >= size:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_size_chars")
        return self


class RagIndexResponse(BaseModel):
    """Indexing counts and embedding signature for a collection update."""

    collection: str
    documents: int
    chunks: int
    embedding_model: str
    embedding_dimensions: int
    request_id: str


class RagSearchRequest(BaseModel):
    """Semantic-search request over one collection."""

    collection: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    query: str = Field(min_length=1, max_length=24000)
    top_k: int = Field(default_factory=lambda: settings.rag_default_top_k, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    metadata_filter: dict[str, JsonScalar] | None = None


class RagSearchHit(BaseModel):
    """One ranked chunk returned from semantic retrieval."""

    rank: int
    score: float
    document_id: str
    chunk_index: int
    source: str | None = None
    text: str
    metadata: dict[str, JsonScalar]


class RagSearchResponse(BaseModel):
    """Semantic retrieval results and the embedding model used for the query."""

    collection: str
    hits: list[RagSearchHit]
    embedding_model: str
    request_id: str


class RagAnswerRequest(RagSearchRequest):
    """Retrieve relevant chunks and answer using only those sources."""

    quality: Quality = "default"
    reasoning: ReasoningEffort | None = None
    system: str | None = None
    max_output_tokens: int = Field(default=2048, ge=128, le=8192)


class RagCitation(BaseModel):
    """A retrieved chunk explicitly cited by the generated answer."""

    label: str
    document_id: str
    chunk_index: int
    source: str | None = None
    score: float
    metadata: dict[str, JsonScalar]


class RagAnswerResponse(BaseModel):
    """Grounded answer, verified citation identifiers, and routing metadata."""

    answer: str
    citations: list[RagCitation]
    retrieved: list[RagSearchHit]
    model: str | None = None
    profile: str
    reasoning: ReasoningEffort | None = None
    attempts: int
    request_id: str


class RagCollectionInfo(BaseModel):
    """Persistent collection statistics."""

    collection: str
    chunks: int
    documents: int
    embedding_model: str
    embedding_dim: int


class RagCollectionsResponse(BaseModel):
    """All currently indexed collections."""

    collections: list[RagCollectionInfo]


class RagDeleteResponse(BaseModel):
    """Number of vector chunks removed by a delete operation."""

    deleted_chunks: int


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
    embedding_model: str
