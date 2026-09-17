"""Public exports for the Local AI Gateway Python SDK."""

from taheem_ai.async_client import AsyncAI as _AsyncAI
from taheem_ai.client import AI as _AI
from taheem_ai.errors import AIError
from taheem_ai.tools import (
    ToolExecutionError,
    ToolPermissionError,
    ToolRegistry,
    ToolRegistryError,
    ToolRunResult,
    ToolSpec,
)
from taheem_ai.vision import VisionAsyncMixin, VisionSyncMixin


class AI(VisionSyncMixin, _AI):
    """Public synchronous gateway client including Stage 5 vision methods."""


class AsyncAI(VisionAsyncMixin, _AsyncAI):
    """Public asynchronous gateway client including Stage 5 vision methods."""


__all__ = [
    "AI",
    "AsyncAI",
    "AIError",
    "ToolExecutionError",
    "ToolPermissionError",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolRunResult",
    "ToolSpec",
]
