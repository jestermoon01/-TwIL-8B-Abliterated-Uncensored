"""Live acceptance probes."""

import httpx

from twil_deploy.client import complete
from twil_deploy.config import Settings


def check(settings: Settings) -> dict[str, str]:
    """Check health, missing-key rejection and both completion modes."""
    with httpx.Client(timeout=settings.timeout) as client:
        client.get(settings.base_url.removesuffix("/v1") + "/health").raise_for_status()
        denied = client.post(settings.base_url + "/chat/completions", json={})
        if denied.status_code != httpx.codes.UNAUTHORIZED:
            raise RuntimeError("Unauthenticated request did not return 401")
    text = complete(settings, "Say hello in one sentence.")
    stream = complete(settings, "Say hello in one sentence.", stream=True)
    if not text.strip() or not stream.strip():
        raise RuntimeError("Generation returned empty text")
    return {"health": "ok", "unauthenticated": "401", "text": text, "stream": stream}
