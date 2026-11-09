"""Server command safety and configuration."""

from pathlib import Path

import pytest

from twil_deploy.config import Settings
from twil_deploy.server import ModelNotFoundError, build_server_args, serve


def test_paths_with_spaces_and_no_secret() -> None:
    settings = Settings(_env_file=None, api_key="x" * 40, models_dir=Path("a b"))
    args = build_server_args(settings)
    assert args[args.index("-m") + 1] == str(settings.model_path.resolve())
    assert args[args.index("--parallel") + 1] == "2"
    assert "--jinja" in args
    assert args[args.index("--chat-template-kwargs") + 1] == '{"enable_thinking": false}'
    assert all("x" * 40 not in arg for arg in args)


def test_missing_model_fails_before_launch(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, api_key="x" * 40, models_dir=tmp_path)
    with pytest.raises(ModelNotFoundError, match="download"):
        serve(settings)
