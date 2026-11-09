"""Conversation compaction boundaries and model-token accounting."""

import json

import httpx
import pytest
import respx

from twil_deploy import context
from twil_deploy.config import Settings
from twil_deploy.context import ChatRequest, ContextWindowError, Message, prepare_context


def settings() -> Settings:
    return Settings(
        _env_file=None,
        api_key="x" * 40,
        ctx_size=512,
        parallel=1,
        context_margin=32,
        summary_tokens=64,
    )


def test_compaction_preserves_latest_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = [
        Message(role="user" if i % 2 == 0 else "assistant", content=f"turn {i}") for i in range(7)
    ]
    captured = []

    def count(_client: httpx.Client, _settings: Settings, turns: list[dict[str, str]]) -> int:
        return len(turns) * (50 if turns[0]["role"] == "system" else 100)

    def summarize(
        _client: httpx.Client, _settings: Settings, previous: str, older: list[Message]
    ) -> str:
        captured.extend(older)
        assert previous == ""
        return "User's project is Cedar."

    monkeypatch.setattr(context, "token_count", count)
    monkeypatch.setattr(context, "compact_older", summarize)
    result = prepare_context(settings(), ChatRequest(messages=messages, max_tokens=128))
    assert result.compacted
    assert captured == messages[:4]
    assert result.messages == messages[4:]
    assert result.summary == "User's project is Cedar."
    assert result.prompt_tokens + 128 + 32 <= 512
    assert len(messages) == 7


def test_single_oversized_message_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(context, "token_count", lambda *_args: 1000)
    request = ChatRequest(
        messages=[Message(role="user", content="Too much content")], max_tokens=128
    )
    with pytest.raises(ContextWindowError, match="too long"):
        prepare_context(settings(), request)


@respx.mock
def test_actual_template_tokenizer_and_authentication() -> None:
    configuration = settings()
    root = configuration.base_url.removesuffix("/v1")
    template = respx.post(root + "/apply-template").mock(
        return_value=httpx.Response(200, json={"prompt": "rendered template"})
    )
    tokenizer = respx.post(root + "/tokenize").mock(
        return_value=httpx.Response(200, json={"tokens": list(range(17))})
    )
    result = prepare_context(
        configuration, ChatRequest(messages=[Message(role="user", content="Hello")], max_tokens=128)
    )
    assert result.prompt_tokens == 17
    assert not result.compacted
    assert template.calls[0].request.headers["Authorization"] == "Bearer " + "x" * 40
    assert json.loads(tokenizer.calls[0].request.content)["content"] == "rendered template"


@respx.mock
def test_empty_summary_is_not_accepted() -> None:
    configuration = settings()
    respx.post(configuration.base_url + "/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})
    )
    with httpx.Client() as client, pytest.raises(ContextWindowError, match="empty"):
        context.generate_summary(
            client, configuration, "old memory", [Message(role="user", content="Remember Cedar")]
        )
