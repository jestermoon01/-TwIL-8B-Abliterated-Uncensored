"""Server arguments and lifecycle."""

import json
import os
import subprocess
import time

import httpx

from twil_deploy.config import Settings


class ModelNotFoundError(FileNotFoundError):
    """The configured artifact is missing."""


class ServerStartError(RuntimeError):
    """The server failed its readiness probe."""


def build_server_args(settings: Settings) -> list[str]:
    """Build arguments without exposing credentials in the process command line."""
    return [
        str((settings.llama_bin_dir / "llama-server.exe").resolve()),
        "-m",
        str(settings.model_path.resolve()),
        "--host",
        settings.host,
        "--port",
        str(settings.port),
        "-ngl",
        str(settings.n_gpu_layers),
        "-c",
        str(settings.ctx_size),
        "--parallel",
        str(settings.parallel),
        "--jinja",
        "--flash-attn",
        "on",
        "--alias",
        settings.alias,
        "--chat-template-kwargs",
        json.dumps({"enable_thinking": settings.enable_thinking}),
        "--log-verbosity",
        str(settings.log_verbosity),
    ]


def serve(settings: Settings) -> int:
    """Start a hidden server and wait for readiness."""
    if not settings.model_path.is_file():
        raise ModelNotFoundError("Run twil-deploy download first")
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, LLAMA_API_KEY=settings.api_key.get_secret_value())
    with (settings.logs_dir / "server.log").open("ab") as log:
        process = subprocess.Popen(  # noqa: S603 -- explicit executable and argument list
            build_server_args(settings),
            stdout=log,
            stderr=log,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    (settings.logs_dir / "server.pid").write_text(str(process.pid), encoding="utf-8")
    deadline = time.monotonic() + settings.timeout
    with httpx.Client(timeout=3) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ServerStartError("Server exited; inspect logs/server.log")
            try:
                response = client.get(settings.base_url.removesuffix("/v1") + "/health")
                if response.status_code == httpx.codes.OK:
                    return process.pid
            except httpx.TransportError:
                pass
            time.sleep(1)
    process.terminate()
    process.wait(timeout=15)
    raise ServerStartError("Readiness timed out; inspect logs/server.log")


def stop(settings: Settings) -> None:
    """Stop the recorded PID after checking its executable path."""
    record = settings.logs_dir / "server.pid"
    process_id = int(record.read_text(encoding="utf-8"))
    environment = dict(
        os.environ, TWIL_EXPECTED_EXE=str((settings.llama_bin_dir / "llama-server.exe").resolve())
    )
    script = (
        f"$p = Get-Process -Id {process_id} -ErrorAction Stop; "
        "if ($p.Path -ne $env:TWIL_EXPECTED_EXE) { throw 'PID identity mismatch' }; "
        "Stop-Process -Id $p.Id -ErrorAction Stop"
    )
    subprocess.run(  # noqa: S603 -- numeric PID and fixed script
        ["powershell.exe", "-NoProfile", "-Command", script],  # noqa: S607
        env=environment,
        check=True,
        timeout=20,
        capture_output=True,
    )
    record.unlink()
