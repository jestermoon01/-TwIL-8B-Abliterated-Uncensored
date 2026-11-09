"""Pinned, checksum-verified model download."""

import hashlib
import logging
from pathlib import Path

from huggingface_hub import hf_hub_download

from twil_deploy.config import Settings


def download_model(settings: Settings) -> Path:
    """Resume the selected GGUF and verify the upstream LFS digest."""
    logging.info("Downloading %s at %s", settings.hf_repo, settings.hf_revision)
    path = Path(
        hf_hub_download(
            repo_id=settings.hf_repo,
            revision=settings.hf_revision,
            filename=settings.model_filename,
            local_dir=settings.models_dir,
        )
    )
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != settings.model_sha256:
        raise ValueError("Model SHA-256 mismatch; redownload the pinned artifact")
    path.with_suffix(".gguf.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return path
