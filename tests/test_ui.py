"""Check proxy authentication, isolation and streamed responses."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import httpx
import pytest
import respx

from twil_deploy.config import Settings
from twil_deploy.ui import handler_for


@pytest.fixture
def ui_server() -> Iterator[tuple[str, Settings]]:
    with ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as server:
        settings = Settings(_env_file=None, api_key="x" * 40, ui_port=server.server_port)
        server.RequestHandlerClass = handler_for(settings)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", settings
        finally:
            server.shutdown()
            thread.join(timeout=5)


def chat_request(url: str, *, origin: str | None = None) -> Request:
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    return Request(  # noqa: S310 -- loopback test server
        url + "/api/chat",
        data=json.dumps({"messages": [{"role": "user", "content": "Hello"}]}).encode(),
        headers=headers,
    )


def test_page_does_not_contain_secret(ui_server: tuple[str, Settings]) -> None:
    url, settings = ui_server
    with urlopen(url, timeout=5) as response:  # noqa: S310 -- loopback test server
        page = response.read().decode()
    assert "TwIL" in page
    assert settings.api_key.get_secret_value() not in page


def test_foreign_origin_rejected(ui_server: tuple[str, Settings]) -> None:
    url, _ = ui_server
    with pytest.raises(HTTPError) as error:
        urlopen(chat_request(url, origin="https://example.com"), timeout=5)  # noqa: S310
    assert error.value.code == 403


@respx.mock
def test_stream_proxy_injects_key(ui_server: tuple[str, Settings]) -> None:
    url, settings = ui_server
    event = 'data: {"choices":[{"delta":{"content":"Hello!"}}]}\n\ndata: [DONE]\n\n'
    upstream = respx.post(settings.base_url + "/chat/completions").mock(
        return_value=httpx.Response(200, text=event)
    )
    with urlopen(chat_request(url), timeout=5) as response:  # noqa: S310
        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.read().decode() == event
    assert upstream.calls[0].request.headers["Authorization"] == "Bearer " + "x" * 40


@respx.mock
def test_offline_server_returns_clear_error(ui_server: tuple[str, Settings]) -> None:
    url, settings = ui_server
    respx.post(settings.base_url + "/chat/completions").mock(
        side_effect=httpx.ConnectError("offline")
    )
    with pytest.raises(HTTPError) as error:
        urlopen(chat_request(url), timeout=5)  # noqa: S310
    assert error.value.code == 503


@respx.mock
def test_continuation_uses_exact_rendered_prefix(ui_server: tuple[str, Settings]) -> None:
    url, settings = ui_server
    respx.post(settings.base_url.removesuffix("/v1") + "/apply-template").mock(
        return_value=httpx.Response(200, json={"prompt": "actual model template:"})
    )
    event = 'data: {"choices":[{"text":" finished.","finish_reason":"stop"}]}\n\n'
    upstream = respx.post(settings.base_url + "/completions").mock(
        return_value=httpx.Response(200, text=event)
    )
    request = chat_request(url)
    request.data = json.dumps(
        {"messages": [{"role": "user", "content": "Explain"}], "continuation": "This was"}
    ).encode()
    with urlopen(request, timeout=5) as response:  # noqa: S310 -- loopback test server
        assert response.read().decode() == event
    payload = json.loads(upstream.calls[0].request.content)
    assert payload["prompt"] == "actual model template:This was"
    assert "continuation" not in payload
    assert "messages" not in payload
