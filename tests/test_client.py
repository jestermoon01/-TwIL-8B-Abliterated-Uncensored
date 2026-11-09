"""Mocked OpenAI contract tests."""

import httpx
import pytest
import respx

from twil_deploy.client import complete
from twil_deploy.config import Settings


@respx.mock
def test_completion_authentication() -> None:
    settings = Settings(_env_file=None, api_key="x" * 40)
    route = respx.post(settings.base_url + "/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "twil-8b",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Hello."},
                    }
                ],
            },
        )
    )
    assert complete(settings, "Hello") == "Hello."
    assert route.calls[0].request.headers["authorization"] == "Bearer " + "x" * 40


@respx.mock
def test_streaming() -> None:
    settings = Settings(_env_file=None, api_key="x" * 40)
    event = (
        'data: {"id":"test","object":"chat.completion.chunk","created":0,'
        '"model":"twil-8b","choices":[{"index":0,"delta":{"content":"Hello."}}]}'
        "\n\ndata: [DONE]\n\n"
    )
    respx.post(settings.base_url + "/chat/completions").mock(
        return_value=httpx.Response(200, text=event, headers={"content-type": "text/event-stream"})
    )
    assert complete(settings, "Hello", stream=True) == "Hello."


def test_prompt_limit() -> None:
    with pytest.raises(ValueError, match="16000"):
        complete(Settings(_env_file=None, api_key="x" * 40), "a" * 16001)
