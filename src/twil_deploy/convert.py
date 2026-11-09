"""Optional conversion from an existing pinned checkout."""

import subprocess
from pathlib import Path

from twil_deploy.config import Settings


def convert(settings: Settings, snapshot: Path, checkout: Path, python: Path) -> None:
    """Convert and quantize with an isolated Python; retain the F16 intermediate."""
    intermediate = settings.models_dir / "twil-8b-f16.gguf"
    subprocess.run(  # noqa: S603 -- explicit executable and argument list
        [
            str(python),
            str(checkout / "convert_hf_to_gguf.py"),
            str(snapshot),
            "--outfile",
            str(intermediate),
            "--outtype",
            "f16",
        ],
        check=True,
        timeout=7200,
    )
    subprocess.run(  # noqa: S603 -- explicit executable and argument list
        [
            str(settings.llama_bin_dir / "llama-quantize.exe"),
            str(intermediate),
            str(settings.model_path),
            settings.quant,
        ],
        check=True,
        timeout=7200,
    )
