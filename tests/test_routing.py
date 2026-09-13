from app.config import settings
from app.routing import choose_profile, public_profiles


def test_balanced_preserves_historical_gemma_mapping():
    balanced = choose_profile("balanced")
    assert balanced.model == settings.model_balanced
    assert balanced.name == "balanced"


def test_default_is_separate_from_balanced():
    default = choose_profile("default")
    assert default.model == settings.model_default
    assert default.name == "default"


def test_reasoning_override_is_explicit():
    profile = choose_profile("default", "low")
    assert profile.reasoning == "low"


def test_public_profiles_are_explicit():
    profiles = public_profiles()
    assert set(profiles) == {"fast", "balanced", "default", "deep"}
