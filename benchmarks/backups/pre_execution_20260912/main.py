from fastapi import FastAPI, Header, HTTPException, status

from app.config import settings
from app.schemas import GenerateRequest, GenerateResponse
from app.routing import choose_model
from app.lmstudio import generate, LMStudioError


app = FastAPI(
    title="Local AI Gateway",
    version="1.0.0",
)


def authenticate(x_local_ai_key: str | None):
    if x_local_ai_key != settings.gateway_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "local-ai-gateway",
    }


@app.post(
    "/v1/generate",
    response_model=GenerateResponse,
)
async def generate_endpoint(
    request: GenerateRequest,
    x_local_ai_key: str | None = Header(default=None),
):
    authenticate(x_local_ai_key)

    model = choose_model(request.quality)

    try:
        result = await generate(
            model=model,
            prompt=request.prompt,
            system=request.system,
            quality=request.quality,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )

    except LMStudioError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    return GenerateResponse(
        text=result["text"],
        model=result["model"],
        quality=request.quality,

        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],

        tokens_per_second=result["tokens_per_second"],
        time_to_first_token_seconds=
            result["time_to_first_token_seconds"],

        model_load_time_seconds=
            result["model_load_time_seconds"],
    )