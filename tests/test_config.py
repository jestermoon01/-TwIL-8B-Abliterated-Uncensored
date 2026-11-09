"""Configuration validation."""

import pytest
from pydantic import ValidationError

from twil_deploy.config import Settings


def test_reject_short_credentials() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(_env_file=None, api_key="short")


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWIL_PORT", "9876")
    settings = Settings(_env_file=None, api_key="x" * 40)
    assert settings.port == 9876
    assert settings.base_url == "http://127.0.0.1:9876/v1"
    assert "x" * 40 not in repr(settings)


@pytest.mark.parametrize("port", [0, 65536])
def test_reject_invalid_ports(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_key="x" * 40, port=port)
