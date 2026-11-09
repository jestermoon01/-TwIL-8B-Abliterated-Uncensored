"""Optional browser regressions for output-limit recovery; no model calls are made."""

import json
import os
from collections.abc import Iterator
from typing import Any

import pytest

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.smoke


@pytest.fixture
def page() -> Iterator[Any]:
    executable = os.environ.get("TWIL_BROWSER_EXECUTABLE")
    if not executable:
        pytest.skip("Set TWIL_BROWSER_EXECUTABLE to an installed Chromium browser")
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch(executable_path=executable, headless=True)
        tab = browser.new_page()
        tab.route("**/api/health", lambda r: r.fulfill(json={"status": "ok"}))

        def context_response(route: Any) -> None:
            data = route.request.post_data_json
            route.fulfill(
                json={
                    "messages": data["messages"],
                    "summary": data.get("summary", ""),
                    "continuation": data.get("continuation", ""),
                    "compacted": False,
                    "prompt_tokens": 20,
                    "available_tokens": 3456,
                }
            )

        tab.route("**/api/context", context_response)
        tab.goto("http://127.0.0.1:8081", wait_until="domcontentloaded")
        tab.get_by_text("Model online", exact=True).wait_for()
        yield tab
        browser.close()


def event(text: str, reason: str | None, *, continuation: bool = False) -> str:
    choice: dict[str, object] = {"finish_reason": reason}
    choice.update({"text": text} if continuation else {"delta": {"content": text}})
    return "data: " + json.dumps({"choices": [choice]}) + "\n\ndata: [DONE]\n\n"


def send(page: Any) -> None:
    page.get_by_label("Your message").fill("Finish this answer.")
    page.locator("#send").click()
    page.wait_for_function("!document.getElementById('prompt').disabled", timeout=15000)


def test_automatic_resume_appends_one_reply(page: Any) -> None:
    requests = []

    def respond(route: Any) -> None:
        data = route.request.post_data_json
        requests.append(data)
        body = (
            event("Start", "length")
            if len(requests) == 1
            else event(" and finish.", "stop", continuation=True)
        )
        route.fulfill(content_type="text/event-stream", body=body)

    page.route("**/api/chat", respond)
    send(page)
    assert len(requests) == 2
    assert requests[1]["continuation"] == "Start"
    assert page.locator(".assistant .content").inner_text() == "Start and finish."
    assert page.locator(".message").count() == 2
    page.reload(wait_until="domcontentloaded")
    assert page.locator(".assistant .content").inner_text() == "Start and finish."


def test_auto_finish_cap_keeps_manual_continue(page: Any) -> None:
    requests = []

    def respond(route: Any) -> None:
        requests.append(route.request.post_data_json)
        route.fulfill(content_type="text/event-stream", body=event(" part", "length"))

    page.route("**/api/chat", respond)
    send(page)
    assert len(requests) == 5
    assert page.get_by_role("button", name="Continue response", exact=True).is_visible()
    assert "paused" in page.locator("#metrics").inner_text()


def test_manual_continue_when_auto_finish_disabled(page: Any) -> None:
    requests = []

    def respond(route: Any) -> None:
        requests.append(route.request.post_data_json)
        body = (
            event("First", "length")
            if len(requests) == 1
            else event(" last.", "stop", continuation=True)
        )
        route.fulfill(content_type="text/event-stream", body=body)

    page.route("**/api/chat", respond)
    page.locator("#autoFinish").uncheck()
    send(page)
    assert len(requests) == 1
    page.reload(wait_until="domcontentloaded")
    page.get_by_role("button", name="Continue response", exact=True).click()
    page.wait_for_function("!document.getElementById('prompt').disabled")
    assert len(requests) == 2
    assert page.locator(".assistant .content").inner_text() == "First last."
    assert page.locator(".message").count() == 2


def test_interrupted_stream_is_not_marked_finished(page: Any) -> None:
    page.route(
        "**/api/chat",
        lambda route: route.fulfill(
            content_type="text/event-stream", body=event("Partial answer", None)
        ),
    )
    send(page)
    assert page.locator(".assistant .content").inner_text() == "Partial answer"
    assert page.get_by_role("button", name="Continue response", exact=True).is_visible()
    assert "Finished" not in page.locator("#metrics").inner_text()


def test_stop_cancels_followup_without_more_retries(page: Any) -> None:
    requests = []

    def respond(route: Any) -> None:
        requests.append(route.request.post_data_json)
        if len(requests) == 1:
            route.fulfill(content_type="text/event-stream", body=event("Partial", "length"))
        # Keep the followup pending so the test can cancel it.

    page.route("**/api/chat", respond)
    page.get_by_label("Your message").fill("Finish this answer.")
    with page.expect_request(
        lambda r: r.url.endswith("/api/chat") and bool(r.post_data_json.get("continuation"))
    ):
        page.locator("#send").click()
    page.locator("#send").click()
    page.wait_for_function("!document.getElementById('prompt').disabled")
    assert len(requests) == 2
    assert page.locator(".assistant .content").inner_text() == "Partial"
    assert page.get_by_role("button", name="Continue response", exact=True).is_visible()
