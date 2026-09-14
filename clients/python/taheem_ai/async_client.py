"""Asynchronous Python client for the Local AI Gateway."""

from __future__ import annotations

import os
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from taheem_ai.errors import AIError

T = TypeVar("T", bound=BaseModel)
DEFAULT_GATEWAY_URL = "http://127.0.0.1:4812"


class AsyncAI:
    """Async SDK for applications that must not block their event loop on inference."""

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

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send one authenticated async request and translate gateway errors."""

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                **kwargs,
            )

        if not response.is_success:
            try:
                payload = response.json()
                error = payload.get("error", {})
            except (ValueError, TypeError):
                error = {}
            raise AIError(
                error.get("code", f"HTTP_{response.status_code}"),
                error.get("message", response.text or "Gateway request failed."),
                error.get("details"),
            )
        return response.json()

    async def ask(
        self,
        prompt: str,
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ) -> str:
        """Return free-form generated text without blocking the caller's event loop."""

        payload = await self._request(
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

    async def extract(
        self,
        text: str,
        schema: type[T],
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
        max_attempts: int = 2,
    ) -> T:
        """Extract validated structured data into a Pydantic model asynchronously."""

        payload = await self._request(
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

    async def classify(
        self,
        text: str,
        labels: list[str],
        *,
        quality: str = "default",
        reasoning: str | None = None,
        system: str | None = None,
    ) -> str:
        """Return one validated label from a closed vocabulary asynchronously."""

        payload = await self._request(
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
