import httpx

from app.config import settings


class LMStudioError(RuntimeError):
    pass


async def generate(
    *,
    model: str,
    prompt: str,
    system: str | None,
    quality: str,
    temperature: float,
    max_output_tokens: int,
) -> dict:

    body = {
        "model": model,
        "input": prompt,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "context_length": settings.default_context_length,
        "store": False,
    }

    if system:
        body["system_prompt"] = system

    if quality == "deep":
        body["reasoning"] = "medium"

    headers = {
        "Authorization": f"Bearer {settings.lm_api_token}",
        "Content-Type": "application/json",
    }

    timeout = httpx.Timeout(settings.lm_timeout_seconds)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.lm_base_url}/api/v1/chat",
            headers=headers,
            json=body,
        )

    if not response.is_success:
        raise LMStudioError(
            f"LM Studio returned "
            f"{response.status_code}: "
            f"{response.text}"
        )

    data = response.json()

    messages = [
        item["content"]
        for item in data.get("output", [])
        if item.get("type") == "message"
    ]

    text = "\n".join(messages).strip()

    stats = data.get("stats", {})

    return {
        "text": text,
        "model": data.get("model_instance_id", model),

        "input_tokens": stats.get("input_tokens"),
        "output_tokens": stats.get("total_output_tokens"),
        "reasoning_output_tokens": stats.get("reasoning_output_tokens"),

        "tokens_per_second":
            stats.get("tokens_per_second"),

        "time_to_first_token_seconds":
            stats.get("time_to_first_token_seconds"),

        "model_load_time_seconds":
            stats.get("model_load_time_seconds"),
    }
