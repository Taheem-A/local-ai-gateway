"""Model-profile routing for gateway quality tiers and reasoning overrides."""

from dataclasses import dataclass
from typing import Literal, cast

from app.config import settings

Quality = Literal["fast", "balanced", "default", "deep"]
ReasoningEffort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ModelProfile:
    """Resolved model and reasoning configuration for a public quality profile."""

    name: str
    model: str
    reasoning: ReasoningEffort | None


def choose_profile(
    quality: Quality,
    reasoning_override: ReasoningEffort | None = None,
) -> ModelProfile:
    """Resolve a public quality name into a concrete local model configuration."""

    if quality == "fast":
        model = settings.model_fast
        reasoning = settings.reasoning_fast
    elif quality == "balanced":
        # Historical Gemma benchmark mapping. Keep this stable until a deliberate
        # benchmark-version migration retires it.
        model = settings.model_balanced
        reasoning = settings.reasoning_balanced
    elif quality == "deep":
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
        name=quality,
        model=model,
        reasoning=cast(ReasoningEffort | None, reasoning),
    )


def choose_model(quality: Quality) -> str:
    """Return only the model ID for older callers that do not need the profile."""

    return choose_profile(quality).model


def public_profiles() -> dict[str, dict[str, str | None]]:
    """Return the configured public profile map exposed by the status API."""

    return {
        quality: {
            "model": choose_profile(quality).model,
            "reasoning": choose_profile(quality).reasoning,
        }
        for quality in ("fast", "balanced", "default", "deep")
    }
