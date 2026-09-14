"""Structured-generation orchestration with validation and bounded repair retries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import StructuredOutputError
from app.lmstudio import generate_structured
from app.structured.normalization import normalize_instance
from app.structured.schema_prep import add_generation_hints, prepare_generation_schema
from app.structured.validation import check_schema, parse_json, validation_errors


@dataclass(frozen=True)
class StructuredResult:
    """Validated structured data plus aggregate token/attempt diagnostics."""

    data: Any
    model: str
    attempts: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    finish_reason: str | None = None


def _retry_prompt(original_prompt: str, previous_text: str, errors: list[str]) -> str:
    """Build a repair prompt that exposes validation failures without changing facts."""

    error_lines = "\n".join(f"- {error}" for error in errors)
    return (
        f"{original_prompt}\n\n"
        "Your previous output failed validation. Correct it and return ONLY an object "
        "that conforms to the supplied JSON Schema and canonical output requirements.\n\n"
        f"Validation errors:\n{error_lines}\n\n"
        f"Previous output:\n{previous_text or '<empty>'}"
    )


async def run_structured(
    *,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    system: str | None,
    reasoning: str | None,
    temperature: float,
    max_output_tokens: int,
    max_attempts: int,
) -> StructuredResult:
    """Generate, normalize, validate, and if necessary repair structured output."""

    check_schema(schema)

    # The caller schema remains authoritative for local validation. A transformed
    # copy handles representation constraints that are narrower than standard JSON
    # Schema semantics, notably the gateway's local HH:MM interpretation of time.
    generation_schema = prepare_generation_schema(schema)
    canonical_prompt = add_generation_hints(prompt, schema)

    attempt_prompt = canonical_prompt
    last_errors: list[str] = []
    last_text = ""
    last_finish_reason: str | None = None
    final_model = model
    total_input_tokens = 0
    total_output_tokens = 0
    total_reasoning_tokens = 0

    for attempt in range(1, max_attempts + 1):
        response = await generate_structured(
            model=model,
            prompt=attempt_prompt,
            system=system,
            reasoning=reasoning,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            schema=generation_schema,
        )

        final_model = response.get("model", model)
        total_input_tokens += int(response.get("input_tokens") or 0)
        total_output_tokens += int(response.get("output_tokens") or 0)
        total_reasoning_tokens += int(response.get("reasoning_output_tokens") or 0)
        last_text = response.get("text", "")
        last_finish_reason = response.get("finish_reason")

        if not last_text.strip():
            if last_finish_reason == "length":
                last_errors = [
                    "Generation exhausted the output-token budget before producing final JSON."
                ]
            else:
                last_errors = ["The model returned an empty structured response."]
        else:
            try:
                data = parse_json(last_text)
            except (ValueError, TypeError) as exc:
                last_errors = [f"Response was not valid JSON: {exc}"]
            else:
                data = normalize_instance(data, schema)
                last_errors = validation_errors(data, schema)
                if not last_errors:
                    return StructuredResult(
                        data=data,
                        model=final_model,
                        attempts=attempt,
                        input_tokens=total_input_tokens or None,
                        output_tokens=total_output_tokens or None,
                        reasoning_output_tokens=total_reasoning_tokens or None,
                        finish_reason=last_finish_reason,
                    )

        if attempt < max_attempts:
            attempt_prompt = _retry_prompt(canonical_prompt, last_text, last_errors)

    raise StructuredOutputError(
        f"The model failed structured-output validation after {max_attempts} attempt(s).",
        details={
            "validation_errors": last_errors,
            "last_output": last_text,
            "finish_reason": last_finish_reason,
            "output_tokens": total_output_tokens or None,
            "reasoning_output_tokens": total_reasoning_tokens or None,
            "max_output_tokens_per_attempt": max_output_tokens,
        },
    )
