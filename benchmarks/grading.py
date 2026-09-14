"""Deterministic benchmark grading with independent semantic and format scores."""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

GRADING_VERSION = 3
_SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")


def outcome(
    semantic: bool | None,
    format_ok: bool | None,
    instruction: bool | None,
    **details: Any,
) -> dict[str, Any]:
    """Build a grading result without collapsing distinct failure dimensions."""

    if semantic is None:
        status = "manual"
    elif not semantic:
        status = "fail"
    elif format_ok is True and instruction is True:
        status = "pass"
    else:
        status = "pass_with_format_issue"

    return {
        "version": GRADING_VERSION,
        "status": status,
        "passed": semantic,
        "semantic_correct": semantic,
        "format_correct": format_ok,
        "instruction_following": instruction,
        **details,
    }


def normalize(value: Any, rule: str) -> Any:
    """Normalize only representations explicitly allowed by a benchmark rule."""

    if rule == "enabled_state":
        if type(value) is bool:
            return value
        if isinstance(value, str) and value.strip().casefold() in ("enabled", "disabled"):
            return value.strip().casefold() == "enabled"
        raise ValueError("Expected boolean or explicit enabled/disabled state")

    if rule == "number":
        if isinstance(value, bool):
            raise ValueError("Boolean is not a number")
        text = str(value).strip()
        number_pattern = (
            r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?(?:[eE][+-]?\d+)?"
            r"|[+-]?\.\d+"
        )
        if not re.fullmatch(number_pattern, text):
            raise ValueError("Invalid finite number")
        return Decimal(text.replace(",", ""))

    if not isinstance(value, str):
        raise ValueError("Expected text")

    text = " ".join(value.split())
    if rule == "case_insensitive":
        return text.casefold()
    if rule == "text":
        return re.sub(r"#\s*(?=\d)", "", text).casefold()
    if rule == "date":
        text = re.sub(r"^\w+day,?\s+", "", text, flags=re.I)
        text = re.sub(r"\bSept\b", "Sep", text, flags=re.I)
        formats = (
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%B %d %Y",
            "%b %d %Y",
            "%d %B %Y",
            "%d %b %Y",
        )
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        raise ValueError("Unrecognized or incomplete date")
    if rule == "time":
        text = text.upper().replace(" ", "")
        for fmt in ("%H:%M", "%I:%M%p", "%I%p"):
            try:
                return datetime.strptime(text, fmt).strftime("%H:%M")
            except ValueError:
                pass
        raise ValueError("Unrecognized time")
    if rule == "timezone":
        # Generic Eastern time is deliberately distinct from EST and EDT.
        aliases = {
            "et": "eastern",
            "eastern time": "eastern",
            "est": "est",
            "eastern standard time": "est",
            "edt": "edt",
            "eastern daylight time": "edt",
            "utc": "utc",
            "coordinated universal time": "utc",
            "z": "utc",
        }
        return aliases.get(text.casefold(), text.casefold())
    raise ValueError(f"Unknown normalization: {rule}")


def _canonical_label(text: str) -> str:
    """Canonicalize harmless Unicode variants used in short label answers."""

    return text.translate(_SUPERSCRIPT_TRANSLATION).casefold()


def strict_load(text: str) -> Any:
    """Parse strict JSON while rejecting duplicate keys and non-finite numbers."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate key: {key}")
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise ValueError(f"Non-finite JSON: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def parse_json(text: str) -> tuple[Any, bool]:
    """Parse JSON and report whether it was the complete bare model response."""

    try:
        return strict_load(text), True
    except ValueError:
        pass

    # Recovery accepts one complete outer object/array for semantic grading, but
    # marks formatting as incorrect so prose/fences are never silently rewarded.
    starts = [match.start() for match in re.finditer(r"[\[{]", text)]
    if not starts:
        raise ValueError("No complete JSON answer; semantic review required")

    start = starts[0]
    decoder = json.JSONDecoder()
    try:
        _, end = decoder.raw_decode(text[start:])
        actual = strict_load(text[start : start + end])
    except ValueError as error:
        raise ValueError("Incomplete or invalid JSON answer") from error

    if re.search(r"[\[{]", text[start + end :]):
        raise ValueError("Multiple JSON candidates; semantic review required")
    return actual, False


def compare_json(
    actual: Any,
    wanted: Any,
    rules: dict[str, str],
    aliases: dict[str, dict[str, str]],
    path: str = "",
) -> tuple[list[dict[str, Any]], bool, bool]:
    """Return semantic differences, schema validity, and canonical-format validity."""

    differences: list[dict[str, Any]] = []

    if isinstance(wanted, dict):
        if not isinstance(actual, dict):
            return [{"path": path, "reason": "Expected object"}], False, False

        mapped: dict[str, Any] = {}
        for key, value in actual.items():
            target = aliases.get(path, {}).get(key, key)
            if target in mapped:
                return [{"path": path, "reason": "Conflicting alias keys"}], False, False
            mapped[target] = value

        schema = set(actual) == set(wanted)
        canonical = schema
        if set(mapped) != set(wanted):
            differences.append(
                {
                    "path": path,
                    "reason": "Missing or extra fields",
                    "missing": sorted(set(wanted) - set(mapped)),
                    "extra": sorted(set(mapped) - set(wanted)),
                }
            )

        for key in wanted.keys() & mapped.keys():
            nested_path = f"{path}.{key}".lstrip(".")
            nested_differences, nested_schema, nested_canonical = compare_json(
                mapped[key],
                wanted[key],
                rules,
                aliases,
                nested_path,
            )
            differences += nested_differences
            schema &= nested_schema
            canonical &= nested_canonical
        return differences, schema, canonical

    if isinstance(wanted, list):
        if not isinstance(actual, list):
            return [{"path": path, "reason": "Expected array"}], False, False
        if len(actual) != len(wanted):
            differences.append({"path": path, "reason": "Array length differs"})

        schema = canonical = True
        for actual_item, wanted_item in zip(actual, wanted):
            nested_path = f"{path}.*".lstrip(".")
            nested_differences, nested_schema, nested_canonical = compare_json(
                actual_item,
                wanted_item,
                rules,
                aliases,
                nested_path,
            )
            differences += nested_differences
            schema &= nested_schema
            canonical &= nested_canonical
        return differences, schema, canonical

    if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
        schema = isinstance(actual, (int, float)) and not isinstance(actual, bool)
    else:
        schema = type(actual) is type(wanted)

    rule = rules.get(path)
    try:
        equal = (
            normalize(actual, rule) == normalize(wanted, rule)
            if rule
            else schema and actual == wanted
        )
    except (ValueError, InvalidOperation):
        equal = False

    canonical = schema
    if rule == "date":
        canonical &= isinstance(actual, str) and bool(
            re.fullmatch(r"\d{4}-\d{2}-\d{2}", actual)
        )
    if rule == "time":
        canonical &= isinstance(actual, str) and bool(
            re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", actual)
        )

    if not equal:
        differences.append(
            {
                "path": path,
                "actual": actual,
                "expected": wanted,
                "reason": "Value differs",
            }
        )
    return differences, schema, canonical


def _grade_json(case: dict[str, Any], text: str) -> dict[str, Any]:
    expected = case["expected"]
    try:
        actual, bare = parse_json(text)
    except ValueError as error:
        return outcome(None, False, False, reason=str(error))

    differences, schema, canonical = compare_json(
        actual,
        expected["value"],
        expected.get("normalize", {}),
        expected.get("key_aliases", {}),
    )
    instruction = bare and schema
    if expected.get("require_canonical"):
        instruction &= canonical
    if "key_order" in expected:
        instruction &= isinstance(actual, dict) and list(actual) == expected["key_order"]
    if case["id"] == "instruction_001":
        instruction &= not differences
    if case["id"] == "instruction_002":
        instruction &= (
            isinstance(actual, list)
            and all(isinstance(item, str) for item in actual)
            and actual == sorted(actual)
        )
    if case["id"] == "instruction_005" and schema:
        instruction &= all(
            isinstance(value, list)
            and all(type(item) is int for item in value)
            and value == sorted(set(value))
            for value in actual.values()
        )
        instruction &= all(item % 2 == 0 for item in actual["even"])
        instruction &= all(item % 2 for item in actual["odd"])

    semantic: bool | None = not differences
    if differences and all(
        difference["path"] in expected.get("review_paths", [])
        for difference in differences
    ):
        semantic = None

    return outcome(
        semantic,
        bare and schema and canonical,
        bool(instruction),
        schema_correct=schema,
        differences=differences,
        actual=actual,
        expected=expected["value"],
    )


def _grade_label(expected: dict[str, Any], text: str) -> dict[str, Any]:
    labels = expected["labels"]
    exact = text in labels
    candidate = re.sub(
        r"^(?:the\s+)?(?:correct\s+)?(?:classification|label|answer|time complexity)"
        r"\s*(?:is|:)\s*",
        "",
        text,
        flags=re.I,
    )
    candidate = candidate.strip(" .`*\"'")

    canonical_candidate = _canonical_label(candidate)
    matches = [
        label for label in labels if canonical_candidate == _canonical_label(label)
    ]
    semantic = matches[0] == expected["value"] if len(matches) == 1 else None
    return outcome(
        semantic,
        exact,
        exact,
        actual=matches[0] if matches else None,
        reason="Unambiguous label" if matches else "Ambiguous prose requires review",
    )


def grade(case: dict[str, Any], text: str, execute_code: bool = True) -> dict[str, Any]:
    """Grade one model response using the case's explicit grading policy."""

    expected = case["expected"]
    mode = expected["mode"]
    text = text.strip()

    if mode in ("exact_json", "semantic_json"):
        return _grade_json(case, text)

    if mode == "label":
        return _grade_label(expected, text)

    if mode == "numeric":
        pattern = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        exact = bool(re.fullmatch(pattern, text))
        candidate = re.sub(
            r"^(?:(?:the\s+)?(?:answer|value|probability)\s*(?:is|:)\s*|x\s*=\s*)",
            "",
            text,
            flags=re.I,
        ).strip()
        if candidate.endswith(".") and re.fullmatch(pattern, candidate[:-1]):
            candidate = candidate[:-1]
        if not re.fullmatch(pattern, candidate):
            return outcome(
                None,
                exact,
                exact,
                reason="No unambiguous numeric answer; review required",
            )

        actual = Decimal(candidate)
        passed = abs(actual - Decimal(str(expected["value"]))) <= Decimal(
            str(expected.get("tolerance", 0))
        )
        return outcome(
            passed,
            exact,
            exact,
            actual=str(actual),
            expected=expected["value"],
        )

    if mode == "exact_text":
        wanted = expected["value"]
        if case["id"] == "instruction_003":
            semantic = re.split(r"[\s-]+", text.casefold()) == wanted.split("-")
            format_ok = bool(re.fullmatch(r"[a-z]+(?:-[a-z]+)*", text))
        elif case["id"] == "instruction_004":
            semantic = text.casefold().split() == wanted.casefold().split()
            format_ok = bool(re.fullmatch(r"[A-Z]+\n[A-Z]+\n[A-Z]+", text))
        else:
            semantic = text == wanted
            format_ok = text == wanted
        return outcome(semantic, format_ok, text == wanted, actual=text, expected=wanted)

    if mode == "code_tests":
        from code_execution import run_code_tests

        try:
            ast.parse(text)
            format_ok = bool(text)
        except SyntaxError:
            format_ok = False

        if not execute_code:
            return outcome(None, format_ok, format_ok, reason="Code execution disabled")

        code = text
        blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S | re.I)
        if len(blocks) == 1:
            code = blocks[0]
        result = run_code_tests(code, expected["tests"])
        return outcome(
            result["passed"],
            format_ok,
            format_ok,
            tests=result.get("tests", []),
            reason=result.get("reason"),
        )

    if mode == "summary_rubric":
        checks = {"nonempty": bool(text)}
        counts: dict[str, int] = {}
        if "max_words" in expected:
            counts["words"] = len(re.findall(r"\b[\w'-]+\b", text))
            checks["word_limit"] = counts["words"] <= expected["max_words"]
        if "sentence_count" in expected:
            sentences = [
                sentence
                for sentence in re.split(r"(?<=[.!?])\s+", text)
                if sentence.strip()
            ]
            counts["sentences"] = len(sentences)
            checks["sentence_count"] = counts["sentences"] == expected["sentence_count"]
        if "max_bullets" in expected:
            lines = [line for line in text.splitlines() if line.strip()]
            counts["bullets"] = sum(
                bool(re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", line)) for line in lines
            )
            checks["bullet_limit"] = 1 <= counts["bullets"] <= expected["max_bullets"]
            checks["bullet_format"] = counts["bullets"] == len(lines)

        return outcome(
            None,
            all(checks.values()),
            all(checks.values()),
            mechanical_checks=checks,
            counts=counts,
            rubric=expected,
            reason=(
                "Manual semantic review: accuracy, coverage, unsupported claims. "
                "Sentence counting is heuristic."
            ),
        )

    raise ValueError(f"Unknown grading mode: {mode}")
