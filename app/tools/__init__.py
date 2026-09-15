"""Tool-calling primitives with caller-owned execution and gateway validation."""

from app.tools.service import ToolTurnResult, run_tool_turn

__all__ = ["ToolTurnResult", "run_tool_turn"]
