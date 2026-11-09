"""Bounded OpenAI client."""

import httpx
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from twil_deploy.config import Settings

MAX_PROMPT_CHARACTERS = 16000


def complete(settings: Settings, prompt: str, *, stream: bool = False) -> str:
    """Generate text with explicit limits, timeout and bounded retries."""
    if len(prompt) > MAX_PROMPT_CHARACTERS:
        raise ValueError("Prompt exceeds 16000 characters")
    messages: list[ChatCompletionMessageParam] = [{"role": "user", "content": prompt}]
    with OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value(),
        timeout=settings.timeout,
        max_retries=2,
        http_client=httpx.Client(timeout=settings.timeout),
    ) as client:
        if stream:
            chunks = client.chat.completions.create(
                model=settings.alias,
                messages=messages,
                max_tokens=settings.max_tokens,
                stream=True,
            )
            return "".join(c.choices[0].delta.content or "" for c in chunks if c.choices)
        response = client.chat.completions.create(
            model=settings.alias,
            messages=messages,
            max_tokens=settings.max_tokens,
        )
        return response.choices[0].message.content or ""
