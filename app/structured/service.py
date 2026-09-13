from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.lmstudio import generate_structured
from app.structured.normalization import normalize_instance
from app.structured.validation import check_schema, parse_json, validation_errors


@dataclass(frozen=True)
class StructuredResult:
    data: Any
    model: str
    attempts: int
    input_tokens: int | None = None
    output_tokens: int | None = None


def _retry_prompt(original_prompt: str, previous_text: str, errors: list[str]) -> str:
    error_lines = "\n".join(f"- {error}" for error in errors)
    return (
        f"{original_prompt}\n\n"
        "Your previous output failed validation. Correct it and return ONLY an object "
        "that conforms to the supplied JSON Schema.\n\n"
        f"Validation errors:\n{error_lines}\n\n"
        f"Previous output:\n{previous_text}"
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
    check_schema(schema)

    attempt_prompt = prompt
    last_errors: list[str] = []
    last_text = ""
    final_model = model
    total_input_tokens = 0
    total_output_tokens = 0

    for attempt in range(1, max_attempts + 1):
        response = await generate_structured(
            model=model,
            prompt=attempt_prompt,
            system=system,
            reasoning=reasoning,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            schema=schema,
        )

        final_model = response.get("model", model)
        total_input_tokens += int(response.get("input_tokens") or 0)
        total_output_tokens += int(response.get("output_tokens") or 0)
        last_text = response["text"]

        try:
            data = parse_json(last_text)
        except Exception as exc:
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
                )

        if attempt < max_attempts:
            attempt_prompt = _retry_prompt(prompt, last_text, last_errors)

    from app.errors import StructuredOutputError

    raise StructuredOutputError(
        f"The model failed structured-output validation after {max_attempts} attempt(s).",
        details={
            "validation_errors": last_errors,
            "last_output": last_text,
        },
    )
