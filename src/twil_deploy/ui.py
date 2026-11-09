"""Loopback HTML interface and authenticated streaming proxy."""

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from pydantic import ValidationError

from twil_deploy.config import Settings
from twil_deploy.context import (
    ChatRequest,
    ContextWindowError,
    model_messages,
    prepare_context,
    render_prompt,
)

MAX_REQUEST_BYTES = 128_000


class LocalHTTPServer(ThreadingHTTPServer):
    """Prevent overlapping Windows listeners from serving stale interface assets."""

    allow_reuse_address = False


def handler_for(settings: Settings) -> type[BaseHTTPRequestHandler]:
    """Create a handler without placing the upstream credential in browser assets."""
    allowed_host = f"127.0.0.1:{settings.ui_port}"
    static = Path(__file__).parent / "static"
    page = (static / "index.html").read_bytes()
    assets = {
        "/assets/markdown-it.min.js": (static / "vendor/markdown-it.min.js", "text/javascript"),
        "/assets/purify.min.js": (static / "vendor/purify.min.js", "text/javascript"),
        "/assets/markdown.css": (static / "markdown.css", "text/css"),
        "/assets/chat.js": (static / "chat.js", "text/javascript"),
        "/assets/conversations.css": (static / "conversations.css", "text/css"),
    }

    class Handler(BaseHTTPRequestHandler):
        """Serve fixed assets and a bounded same-origin proxy."""

        def log_message(self, format: str, *args: object) -> None:
            """Route request logs through application logging."""
            logging.getLogger(__name__).info(format, *args)

        def reply(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self) -> bool:
            if self.headers.get("Host") != allowed_host:
                self.reply(403, b'{"error":"Use the loopback interface URL"}', "application/json")
                return False
            return True

        def do_GET(self) -> None:
            """Serve the page or check upstream readiness."""
            if not self.valid_host():
                return
            if self.path in {"/", "/index.html"}:
                self.reply(200, page, "text/html; charset=utf-8")
            elif self.path in assets:
                asset, content_type = assets[self.path]
                self.reply(200, asset.read_bytes(), content_type)
            elif self.path == "/api/health":
                try:
                    with httpx.Client(timeout=3) as client:
                        result = client.get(settings.base_url.removesuffix("/v1") + "/health")
                    self.reply(result.status_code, result.content, "application/json")
                except httpx.TransportError:
                    self.reply(503, b'{"error":"Model server is offline"}', "application/json")
            else:
                self.reply(404, b"Not found", "text/plain")

        def do_POST(self) -> None:
            """Validate a same-origin request and forward SSE with server-side authentication."""
            if not self.valid_host():
                return
            if self.path not in {"/api/chat", "/api/context"}:
                self.reply(404, b"Not found", "text/plain")
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{allowed_host}":
                self.reply(403, b'{"error":"Origin rejected"}', "application/json")
                return
            if self.headers.get("Content-Type") != "application/json":
                self.reply(415, b'{"error":"JSON required"}', "application/json")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise ValueError("Request exceeds size limit")
                request = ChatRequest.model_validate_json(self.rfile.read(length))
            except (ValueError, ValidationError):
                self.reply(
                    400, b'{"error":"Invalid or oversized chat request"}', "application/json"
                )
                return
            if self.path == "/api/context":
                try:
                    context = prepare_context(settings, request)
                    self.reply(200, context.model_dump_json().encode(), "application/json")
                except ContextWindowError as error:
                    self.reply(400, json.dumps({"error": str(error)}).encode(), "application/json")
                except (httpx.HTTPError, ValidationError):
                    self.reply(
                        503,
                        b'{"error":"Context preparation failed; chat preserved"}',
                        "application/json",
                    )
            else:
                self.forward(request)

        def forward(self, request: ChatRequest) -> None:
            """Relay a validated generation request without buffering the response."""
            payload = request.model_dump() | {"model": settings.alias, "stream": True}
            payload.pop("summary")
            payload.pop("continuation")
            payload["messages"] = model_messages(request.messages, request.summary)
            streaming = False
            try:
                with httpx.Client(
                    timeout=settings.timeout,
                    headers={
                        "Authorization": "Bearer " + settings.api_key.get_secret_value(),
                    },
                ) as client:
                    endpoint = "/chat/completions"
                    if request.continuation:
                        prompt = (
                            render_prompt(
                                client,
                                settings,
                                model_messages(
                                    request.messages,
                                    request.summary,
                                ),
                            )
                            + request.continuation
                        )
                        payload.pop("messages")
                        payload["prompt"] = prompt
                        endpoint = "/completions"
                    with client.stream(
                        "POST",
                        settings.base_url + endpoint,
                        json=payload,
                    ) as response:
                        if response.is_error:
                            self.reply(
                                response.status_code,
                                json.dumps(
                                    {"error": "Request rejected. Try fewer tokens."}
                                ).encode(),
                                "application/json",
                            )
                            return
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        streaming = True
                        for chunk in response.iter_bytes():
                            self.wfile.write(chunk)
                            self.wfile.flush()
            except ConnectionError:
                logging.getLogger(__name__).info("Chat stream cancelled by browser")
            except httpx.TransportError:
                if not streaming:
                    self.reply(503, b'{"error":"Model server is offline"}', "application/json")
                    return
                event = 'data: {"error":"Connection to model server failed"}\n\n'
                try:
                    self.wfile.write(event.encode())
                except ConnectionError:
                    logging.getLogger(__name__).info("Browser disconnected")

    return Handler


def run_ui(settings: Settings) -> None:
    """Serve the local chat interface until interrupted."""
    with LocalHTTPServer((settings.ui_host, settings.ui_port), handler_for(settings)) as server:
        server.serve_forever()
