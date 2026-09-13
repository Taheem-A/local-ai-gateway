from app.routing import choose_profile, public_profiles


def test_balanced_is_backwards_compatible_alias_for_default():
    balanced = choose_profile("balanced")
    default = choose_profile("default")
    assert balanced.model == default.model
    assert balanced.reasoning == default.reasoning
    assert balanced.name == "default"


def test_reasoning_override_is_explicit():
    profile = choose_profile("default", "low")
    assert profile.reasoning == "low"


def test_public_profiles_hide_balanced_alias():
    profiles = public_profiles()
    assert set(profiles) == {"fast", "default", "deep"}
