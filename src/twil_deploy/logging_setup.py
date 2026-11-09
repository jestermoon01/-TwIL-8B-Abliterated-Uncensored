"""Shared logging configuration."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(directory: Path) -> None:
    """Rotate tooling logs and include timestamps."""
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                directory / "tooling.log",
                maxBytes=2_000_000,
                backupCount=3,
            ),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
