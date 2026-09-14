"""Routing regression tests for public quality profiles and reasoning overrides."""

from app.config import settings
from app.routing import choose_profile, public_profiles


def test_balanced_preserves_historical_gemma_mapping():
    balanced = choose_profile("balanced")
    assert balanced.model == settings.model_balanced
    assert balanced.name == "balanced"


def test_default_uses_benchmarked_low_reasoning():
    default = choose_profile("default")
    assert default.model == settings.model_default
    assert default.reasoning == "low"


def test_deep_uses_benchmarked_high_reasoning():
    deep = choose_profile("deep")
    assert deep.model == settings.model_deep
    assert deep.reasoning == "high"


def test_reasoning_override_is_explicit():
    profile = choose_profile("default", "medium")
    assert profile.reasoning == "medium"


def test_public_profiles_are_explicit():
    profiles = public_profiles()
    assert set(profiles) == {"fast", "balanced", "default", "deep"}
    assert profiles["default"]["reasoning"] == "low"
    assert profiles["deep"]["reasoning"] == "high"
