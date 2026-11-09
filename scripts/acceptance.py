"""Record repeatable local acceptance results without credentials."""

import json
import shutil
import statistics
import subprocess
from pathlib import Path

import httpx
import typer

from twil_deploy.config import Settings
from twil_deploy.healthcheck import check


def memory_used() -> int:
    """Read total GPU memory usage in MiB from the installed NVIDIA tool."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        raise FileNotFoundError("nvidia-smi is not available")
    result = subprocess.run(  # noqa: S603 -- resolved NVIDIA utility, fixed arguments
        [executable, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return int(result.stdout.strip().splitlines()[0])


def main() -> None:
    """Check both response modes and record twelve sequential generations."""
    settings = Settings()  # type: ignore[call-arg]
    smoke = check(settings)
    samples = []
    memory = [memory_used()]
    with httpx.Client(
        timeout=settings.timeout,
        headers={"Authorization": "Bearer " + settings.api_key.get_secret_value()},
    ) as client:
        prompts = [
            json.loads(line) for line in Path("tests/prompts.jsonl").read_text().splitlines()
        ]
        for index in range(12):
            prompt = prompts[index % len(prompts)]
            response = client.post(
                settings.base_url + "/chat/completions",
                json={
                    "model": settings.alias,
                    "messages": [{"role": "user", "content": prompt["prompt"]}],
                    "max_tokens": settings.max_tokens,
                    "temperature": 0,
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            if not text or not text.strip():
                raise RuntimeError("Empty answer during consecutive-request check")
            samples.append({"prompt_id": prompt["id"], "text": text, "timings": data["timings"]})
            memory.append(memory_used())
        response = client.post(
            settings.base_url + "/chat/completions",
            json={
                "model": settings.alias,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Explain in three paragraphs how quantizing a language model "
                            "reduces GPU memory."
                        ),
                    }
                ],
                "max_tokens": 128,
                "temperature": 0,
            },
        )
        response.raise_for_status()
        longer = response.json()
    speeds = [sample["timings"]["predicted_per_second"] for sample in samples]
    report = {
        "smoke": smoke,
        "samples": samples,
        "memory_mib": memory,
        "memory_span_mib": max(memory) - min(memory),
        "median_generation_tokens_per_second": statistics.median(speeds),
        "longer_generation": {
            "text": longer["choices"][0]["message"]["content"],
            "finish_reason": longer["choices"][0]["finish_reason"],
            "timings": longer["timings"],
        },
        "external_lan_test": "pending second device",
        "external_public_test": "pending external network",
    }
    destination = Path("reports/acceptance.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
