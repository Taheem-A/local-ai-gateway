from dataclasses import dataclass
from typing import Literal

from app.config import settings

Quality = Literal["fast", "balanced", "default", "deep"]
ReasoningEffort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model: str
    reasoning: ReasoningEffort | None


def choose_profile(
    quality: Quality,
    reasoning_override: ReasoningEffort | None = None,
) -> ModelProfile:
    # `balanced` is kept for backwards compatibility with the benchmark runner.
    normalized = "default" if quality == "balanced" else quality

    if normalized == "fast":
        model = settings.model_fast
        reasoning = settings.reasoning_fast
    elif normalized == "deep":
        model = settings.model_deep
        reasoning = settings.reasoning_deep
    else:
        model = settings.model_default
        reasoning = settings.reasoning_default

    if reasoning_override is not None:
        reasoning = reasoning_override

    if reasoning not in {None, "low", "medium", "high"}:
        raise ValueError(f"Unsupported reasoning effort: {reasoning}")

    return ModelProfile(
        name=normalized,
        model=model,
        reasoning=reasoning,  # type: ignore[arg-type]
    )


def choose_model(quality: Quality) -> str:
    """Backwards-compatible helper used by older code/tests."""
    return choose_profile(quality).model


def public_profiles() -> dict[str, dict[str, str | None]]:
    return {
        quality: {
            "model": choose_profile(quality).model,
            "reasoning": choose_profile(quality).reasoning,
        }
        for quality in ("fast", "default", "deep")
    }
