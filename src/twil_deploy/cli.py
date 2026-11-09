"""Deployment command line."""

import json
from pathlib import Path

import typer

from twil_deploy.config import Settings
from twil_deploy.convert import convert as convert_model
from twil_deploy.download import download_model
from twil_deploy.healthcheck import check as check_server
from twil_deploy.logging_setup import configure_logging
from twil_deploy.server import serve as start_server
from twil_deploy.server import stop as stop_server
from twil_deploy.ui import run_ui

app = typer.Typer(no_args_is_help=True)


@app.command()
def ui() -> None:
    """Open a loopback-only HTML chat server with automatic API authentication."""
    settings = configured()
    typer.echo(f"Chat interface: http://127.0.0.1:{settings.ui_port}")
    run_ui(settings)


def configured() -> Settings:
    """Load configuration and initialize logging."""
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.logs_dir)
    return settings


@app.command()
def download() -> None:
    """Download and verify the pinned GGUF."""
    typer.echo(download_model(configured()))


@app.command()
def serve() -> None:
    """Start the authenticated LAN server in the background."""
    typer.echo(f"Server ready; PID {start_server(configured())}")


@app.command()
def stop() -> None:
    """Stop the recorded server."""
    stop_server(configured())
    typer.echo("Server stopped")


@app.command()
def check() -> None:
    """Check health, authentication, completion and streaming."""
    typer.echo(json.dumps(check_server(configured()), indent=2))


@app.command()
def convert(snapshot: Path, checkout: Path, python: Path) -> None:
    """Convert with a pinned checkout and isolated Python."""
    convert_model(configured(), snapshot, checkout, python)
