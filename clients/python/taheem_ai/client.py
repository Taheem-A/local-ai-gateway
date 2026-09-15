"""Synchronous Python client for the Local AI Gateway."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from taheem_ai.errors import AIError
from taheem_ai.streaming import SSEDecoder, raise_if_stream_error, response_error
from taheem_ai.tools import ToolExecutionError, ToolRegistry, ToolRisk, ToolRunResult

T = TypeVar("T", bound=BaseModel)
DEFAULT_GATEWAY_URL = "http://127.0.0.1:4812"


class AI:
    """Small synchronous SDK over the gateway's public HTTP endpoints."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        project: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        configured_url = base_url or os.getenv("LOCAL_AI_GATEWAY_URL") or DEFAULT_GATEWAY_URL
        self.base_url = configured_url.rstrip("/")
        self.api_key = (
            api_key
            or os.getenv("LOCAL_AI_GATEWAY_KEY")
            or os.getenv("GATEWAY_API_KEY")
        )
        self.project = project
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "No gateway API key provided. Pass api_key=... or set LOCAL_AI_GATEWAY_KEY."
            )

    def _headers(self) -> dict[str, str]:
        """Build authentication and optional project-attribution headers."""

        headers = {"X-Local-AI-Key": self.api_key}
        if self.project:
            headers["X-Project-ID"] = self.project
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send one authenticated request and translate gateway errors to AIError."""

        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                **kwargs,
            )

        if not response.is_success:
            raise response_error(response)
        return response.json()

    def health(self) -> dict[str, Any]:
        """Check the gateway process without invoking a model."""

        with httpx.Client(timeout=10) as client:
            response = client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

    def status(self) -> dict[str, Any]:
        """Return authenticated gateway/LM Studio status information."""

        return self._request("GET", "/v1/status")

    def ask(
        self,
        prompt: str,
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ) -> str:
        """Return free-form generated text using a public gateway profile."""

        payload = self._request(
            "POST",
            "/v1/generate",
            json={
                "prompt": prompt,
                "quality": quality,
                "reasoning": reasoning,
                "system": system,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
        )
        return payload["text"]

    def stream_events(
        self,
        prompt: str,
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ) -> Iterator[dict[str, Any]]:
        """Yield normalized start/progress/delta/completed events from one generation."""

        body = {
            "prompt": prompt,
            "quality": quality,
            "reasoning": reasoning,
            "system": system,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        decoder = SSEDecoder()
        completed = False

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/v1/generate/stream",
                headers=self._headers(),
                json=body,
            ) as response:
                if not response.is_success:
                    response.read()
                    raise response_error(response)

                for line in response.iter_lines():
                    event = decoder.feed_line(line)
                    if event is None:
                        continue
                    raise_if_stream_error(event)
                    if event.get("type") == "completed":
                        completed = True
                    yield event

                trailing = decoder.finish()
                if trailing is not None:
                    raise_if_stream_error(trailing)
                    if trailing.get("type") == "completed":
                        completed = True
                    yield trailing

        if not completed:
            raise AIError(
                "STREAM_PROTOCOL_ERROR",
                "Gateway stream ended without a completed event.",
            )

    def stream(
        self,
        prompt: str,
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ) -> Iterator[str]:
        """Yield only user-visible text fragments from a generation stream."""

        for event in self.stream_events(
            prompt,
            quality=quality,
            reasoning=reasoning,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ):
            if event.get("type") == "delta":
                text = event.get("text")
                if isinstance(text, str) and text:
                    yield text

    def extract(
        self,
        text: str,
        schema: type[T],
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        max_attempts: int = 2,
    ) -> T:
        """Extract validated structured data directly into a Pydantic model."""

        payload = self._request(
            "POST",
            "/v1/extract",
            json={
                "prompt": text,
                "schema": schema.model_json_schema(),
                "quality": quality,
                "reasoning": reasoning,
                "system": system,
                "max_attempts": max_attempts,
            },
        )
        return schema.model_validate(payload["data"])

    def classify(
        self,
        text: str,
        labels: list[str],
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
    ) -> str:
        """Return exactly one label from a caller-provided closed vocabulary."""

        payload = self._request(
            "POST",
            "/v1/classify",
            json={
                "text": text,
                "labels": labels,
                "quality": quality,
                "reasoning": reasoning,
                "system": system,
            },
        )
        return payload["label"]

    def tool_turn(
        self,
        messages: list[dict[str, Any]],
        tools: ToolRegistry | list[dict[str, Any]],
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.0,
        max_output_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Run one tool-capable model turn; no tool is executed by this method."""

        definitions = tools.definitions() if isinstance(tools, ToolRegistry) else tools
        return self._request(
            "POST",
            "/v1/tools/turn",
            json={
                "messages": messages,
                "tools": definitions,
                "quality": quality,
                "reasoning": reasoning,
                "system": system,
                "tool_choice": tool_choice,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
        )

    def run_tools_once(
        self,
        prompt: str,
        registry: ToolRegistry,
        *,
        allowed_risks: set[ToolRisk] | frozenset[ToolRisk] = frozenset({"read"}),
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int = 2048,
    ) -> ToolRunResult:
        """Execute at most one authorized tool round, then force a text-only synthesis turn."""

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        first = self.tool_turn(
            messages,
            registry,
            quality=quality,
            reasoning=reasoning,
            system=system,
            tool_choice="auto",
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        if first["status"] == "completed":
            return ToolRunResult(
                text=first.get("text") or "",
                tool_calls=[],
                tool_results=[],
                first_turn=first,
                final_turn=first,
            )

        registry.preflight(first["tool_calls"], allowed_risks=allowed_risks)
        messages.append(first["assistant_message"])
        tool_results: list[dict[str, Any]] = []
        for call in first["tool_calls"]:
            result = registry.execute(call, allowed_risks=allowed_risks)
            result_message = {
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": result,
            }
            tool_results.append(result_message)
            messages.append(result_message)

        final = self.tool_turn(
            messages,
            registry,
            quality=quality,
            reasoning=reasoning,
            system=system,
            tool_choice="none",
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        if final["status"] != "completed":
            raise ToolExecutionError(
                "The forced synthesis turn unexpectedly returned another tool call."
            )

        return ToolRunResult(
            text=final.get("text") or "",
            tool_calls=first["tool_calls"],
            tool_results=tool_results,
            first_turn=first,
            final_turn=final,
        )

    def embed(
        self,
        inputs: str | list[str],
        *,
        purpose: str = "raw",
    ) -> list[list[float]]:
        """Return dense vectors from the gateway's configured embedding model."""

        payload = self._request(
            "POST",
            "/v1/embeddings",
            json={"input": inputs, "purpose": purpose},
        )
        return payload["embeddings"]

    def index_documents(
        self,
        collection: str,
        documents: list[dict[str, Any]],
        *,
        chunk_size_chars: int | None = None,
        chunk_overlap_chars: int | None = None,
    ) -> dict[str, Any]:
        """Chunk and index documents into a persistent local RAG collection."""

        body: dict[str, Any] = {"collection": collection, "documents": documents}
        if chunk_size_chars is not None:
            body["chunk_size_chars"] = chunk_size_chars
        if chunk_overlap_chars is not None:
            body["chunk_overlap_chars"] = chunk_overlap_chars
        return self._request("POST", "/v1/rag/index", json=body)

    def search(
        self,
        collection: str,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return semantically similar indexed chunks without generation."""

        payload = self._request(
            "POST",
            "/v1/rag/search",
            json={
                "collection": collection,
                "query": query,
                "top_k": top_k,
                "min_score": min_score,
                "metadata_filter": metadata_filter,
            },
        )
        return payload["hits"]

    def answer_with_sources(
        self,
        collection: str,
        query: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
        metadata_filter: dict[str, Any] | None = None,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        max_output_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Return a grounded answer together with verifiable retrieved citations."""

        return self._request(
            "POST",
            "/v1/rag/answer",
            json={
                "collection": collection,
                "query": query,
                "top_k": top_k,
                "min_score": min_score,
                "metadata_filter": metadata_filter,
                "quality": quality,
                "reasoning": reasoning,
                "system": system,
                "max_output_tokens": max_output_tokens,
            },
        )

    def rag_collections(self) -> list[dict[str, Any]]:
        """List persistent RAG collections and their index signatures."""

        return self._request("GET", "/v1/rag/collections")["collections"]

    def delete_rag_collection(self, collection: str) -> int:
        """Delete a complete RAG collection and return removed chunk count."""

        payload = self._request("DELETE", f"/v1/rag/collections/{collection}")
        return int(payload["deleted_chunks"])

    def delete_rag_document(self, collection: str, document_id: str) -> int:
        """Delete one indexed document and return removed chunk count."""

        payload = self._request(
            "DELETE",
            f"/v1/rag/collections/{collection}/documents/{document_id}",
        )
        return int(payload["deleted_chunks"])
