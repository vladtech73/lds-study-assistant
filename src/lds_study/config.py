"""Application configuration (pydantic-settings)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def repo_root() -> Path:
    """Return repository root when installed as src/lds_study (editable / source tree)."""
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="LDS_STUDY_",
    )

    root: Path = Field(default_factory=repo_root)
    data_dir: Path = Path("data")
    index_dir: Path = Path("indexes")
    models_dir: Path = Path("models")
    outputs_dir: Path = Path("outputs")
    ollama_host: str = "http://127.0.0.1:11434"

    def resolve(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (self.root / path).resolve()

    @property
    def configs_dir(self) -> Path:
        return self.root / "configs"

    def load_yaml(self, name: str) -> dict[str, Any]:
        path = self.configs_dir / name
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a mapping at the top level")
        return data


def get_settings() -> Settings:
    """Load settings, preferring repo-root `.env` when present.

    `LDS_STUDY_ROOT` is honored when set to a non-empty path in the environment or
    `.env`. Only when it is unset/empty do we fall back to deriving the root from
    this package's location.
    """
    env_path = repo_root() / ".env"
    if env_path.exists():
        settings = Settings(_env_file=env_path)
    else:
        settings = Settings()

    root_explicit = "root" in settings.model_fields_set
    root_value = str(settings.root).strip() if settings.root is not None else ""
    if not root_explicit or not root_value:
        settings.root = repo_root()
    else:
        settings.root = Path(root_value)
    return settings
