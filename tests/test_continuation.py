"""Exact continuation prefixes and rolling context accounting."""

import json

import httpx
import pytest
import respx

from twil_deploy import context
from twil_deploy.config import Settings
from twil_deploy.context import ChatRequest, Message, model_messages, prepare_context, token_count


@respx.mock
def test_token_budget_includes_partial_answer() -> None:
    settings = Settings(_env_file=None, api_key="x" * 40)
    root = settings.base_url.removesuffix("/v1")
    respx.post(root + "/apply-template").mock(
        return_value=httpx.Response(200, json={"prompt": "rendered prefix:"})
    )
    tokenizer = respx.post(root + "/tokenize").mock(
        return_value=httpx.Response(200, json={"tokens": [1, 2, 3]})
    )
    with httpx.Client() as client:
        assert token_count(client, settings, [], "unfinished") == 3
    assert json.loads(tokenizer.calls[0].request.content)["content"] == "rendered prefix:unfinished"


def test_rolling_prefix_preserves_exact_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, api_key="x" * 40, ctx_size=4096, parallel=1)
    original = "Earlier generated answer. " * 180 + "The final exact bytes: unfinished_"
    captured = []

    def count(
        _client: httpx.Client,
        _settings: Settings,
        _messages: list[dict[str, str]],
        suffix: str = "",
    ) -> int:
        return len(suffix) + 20

    def summarize(
        _client: httpx.Client, _settings: Settings, _summary: str, messages: list[Message]
    ) -> str:
        captured.extend(messages)
        return "Memory of earlier answer."

    monkeypatch.setattr(context, "token_count", count)
    monkeypatch.setattr(context, "compact_older", summarize)
    request = ChatRequest(
        messages=[Message(role="user", content="Explain the plan")],
        continuation=original,
        max_tokens=512,
    )
    result = prepare_context(settings, request)
    assert result.compacted
    assert result.continuation.endswith("The final exact bytes: unfinished_")
    assert "".join(m.content for m in captured) + result.continuation == original
    assert result.messages == request.messages
    assert result.prompt_tokens <= result.available_tokens
    assert request.continuation == original


def test_summary_precedes_original_conversation() -> None:
    turns = [Message(role="user", content="original request")]
    assert model_messages(turns, "memory")[-1] == {"role": "user", "content": "original request"}
