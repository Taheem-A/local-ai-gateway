# Structured Output

## Goal

Software needs machine-valid data, not merely prose that looks approximately correct. `/v1/extract` therefore treats model output as untrusted until it passes local validation.

## Enforcement pipeline

```text
caller JSON Schema
      |
      v
LM Studio constrained generation
      |
      v
parse JSON
      |
      v
conservative normalization
      |
      v
Draft 2020-12 JSON Schema validation
      |
      +-- valid -> return typed data
      |
      +-- invalid -> retry with exact errors (bounded)
```

## Normalization rules

Normalization is intentionally narrow. It canonicalizes equivalent representations but does not invent or repair facts.

Built-in behavior:

- `{"type":"string","format":"date"}` converts common unambiguous English dates to `YYYY-MM-DD`.
- `{"type":"string","format":"time"}` converts `11:59 PM` to `23:59`.
- Numeric schema types may convert numeric strings to actual numbers.
- `x-normalize: upper` uppercases a string.
- `x-normalize: lower` lowercases a string.
- `x-normalize: strip` trims surrounding whitespace.

Example:

```json
{
  "type": "object",
  "properties": {
    "course": {
      "type": "string",
      "x-normalize": "upper"
    },
    "due_date": {
      "type": "string",
      "format": "date"
    },
    "due_time": {
      "type": "string",
      "format": "time"
    }
  },
  "required": ["course", "due_date", "due_time"],
  "additionalProperties": false
}
```

An output containing `mat186`, `September 18, 2026`, and `11:59 PM` can safely normalize to `MAT186`, `2026-09-18`, and `23:59`.

An output containing `September 19, 2026` will remain September 19. The gateway must never silently change an incorrect fact into the expected fact.

## Retry policy

Default attempts: 2.

On failure, the second prompt includes:

- the original task,
- the exact local validation errors,
- the previous invalid output,
- an instruction to return only schema-conforming data.

Attempts are hard-bounded to prevent accidental loops.

## Caller guidance

Prefer precise schemas:

- use `required`,
- set `additionalProperties: false` when extra keys are not allowed,
- use `enum` for closed vocabularies,
- use `format: date` and `format: time` for canonical date/time values,
- use descriptive field names instead of relying on prompt prose.

For classification, use `/v1/classify`; it automatically converts labels into an enum-constrained schema.
