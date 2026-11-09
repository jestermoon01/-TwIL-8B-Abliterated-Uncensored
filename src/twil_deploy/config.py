"""Validated deployment configuration."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_KEY_LENGTH = 32


class Settings(BaseSettings):
    """Load typed settings from the environment and .env."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TWIL_")
    hf_repo: str = "mradermacher/TwIL-8B-Abliterated-Uncensored-GGUF"
    hf_revision: str = "185406da788423cc0d0dc13f290fea87072904b2"
    model_filename: str = "TwIL-8B-Abliterated-Uncensored.Q5_K_M.gguf"
    model_sha256: str = "fbec9bf51afe4419abd7c62fceac9126b557a1ae56af884b0c19b9264c13e08c"
    models_dir: Path = Path("models")
    llama_bin_dir: Path = Path("bin-b10000")
    logs_dir: Path = Path("logs")
    quant: str = "Q5_K_M"
    ctx_size: int = Field(default=8192, ge=512)
    n_gpu_layers: int = Field(default=99, ge=0)
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    api_key: SecretStr
    parallel: int = Field(default=2, ge=1, le=5)
    alias: str = "twil-8b"
    max_tokens: int = Field(default=128, ge=1, le=4096)
    timeout: float = Field(default=180, gt=0)
    enable_thinking: bool = False
    log_verbosity: int = Field(default=4, ge=0, le=5)
    ui_port: int = Field(default=8081, ge=1, le=65535)

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        """Require a nontrivial credential."""
        if len(value.get_secret_value()) < MIN_KEY_LENGTH:
            raise ValueError("TWIL_API_KEY must contain at least 32 characters")
        return value

    @property
    def model_path(self) -> Path:
        """Return the selected model artifact."""
        return self.models_dir / self.model_filename

    @property
    def base_url(self) -> str:
        """Probe wildcard listeners through loopback."""
        host = "127.0.0.1" if self.host == "0.0.0.0" else self.host  # noqa: S104
        return f"http://{host}:{self.port}/v1"
