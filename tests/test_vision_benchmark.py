"""Offline tests for deterministic Stage 5 vision benchmark fixtures and grading."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from benchmarks.run_vision_benchmarks import build_fixture, grade_text


def test_vision_benchmark_builds_static_png_fixtures():
    fixture_names = (
        "shapes",
        "text_reading",
        "table_reading",
        "spatial_relation",
        "multi_image",
        "ui_error",
    )
    for name in fixture_names:
        images = build_fixture(name)
        assert images
        for raw in images:
            with Image.open(BytesIO(raw)) as image:
                assert image.format == "PNG"
                assert image.width > 0
                assert image.height > 0

    assert len(build_fixture("multi_image")) == 2


def test_vision_benchmark_grader_is_case_insensitive_and_requires_every_fact():
    passing = grade_text(
        "CIV100 | sf1105 | 14:30",
        ["CIV100", "SF1105", "14:30"],
    )
    assert passing["fact_correct"] is True
    assert passing["missing_terms"] == []

    failing = grade_text(
        "CIV100 | SF1105",
        ["CIV100", "SF1105", "14:30"],
    )
    assert failing["fact_correct"] is False
    assert failing["missing_terms"] == ["14:30"]
