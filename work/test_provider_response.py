import asyncio
from unittest.mock import patch

import httpx

from app.lmstudio import generate


def test_provider_final_answer_extraction():
    async def run():
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "output": [
                        {"type": "reasoning", "content": "planning"},
                        {"type": "message", "content": '{"answer":42}'},
                        {"type": "tool_call", "tool": "ignored"},
                    ],
                    "stats": {
                        "total_output_tokens": 10,
                        "reasoning_output_tokens": 5,
                    },
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("app.lmstudio.httpx.AsyncClient", return_value=client):
            result = await generate(
                model="test",
                prompt="test",
                system=None,
                reasoning=None,
                temperature=0,
                max_output_tokens=4096,
            )

        assert result["text"] == '{"answer":42}'
        assert result["reasoning_output_tokens"] == 5

    asyncio.run(run())
