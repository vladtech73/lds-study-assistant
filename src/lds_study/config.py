"""Application configuration (pydantic-settings)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
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

    # None / blank env means "derive from package location" — never Path('.').
    root: Path | None = None
    data_dir: Path = Path("data")
    index_dir: Path = Path("indexes")
    models_dir: Path = Path("models")
    outputs_dir: Path = Path("outputs")
    ollama_host: str = "http://127.0.0.1:11434"

    @field_validator("root", mode="before")
    @classmethod
    def _blank_root_means_unset(cls, value: Any) -> Any:
        """Treat blank `LDS_STUDY_ROOT` as unset.

        An empty env/dotenv value must not become `Path('')` / `Path('.')`, which would
        silently root the project at the current working directory.
        """
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def resolve(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (self.effective_root / path).resolve()

    @property
    def effective_root(self) -> Path:
        """Resolved project root; never None (falls back to package location)."""
        return self.root if self.root is not None else repo_root()

    @property
    def configs_dir(self) -> Path:
        return self.effective_root / "configs"

    def load_yaml(self, name: str) -> dict[str, Any]:
        path = self.configs_dir / name
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a mapping at the top level")
        return data


def get_settings() -> Settings:
    """Load settings, preferring repo-root `.env` when present.

    `LDS_STUDY_ROOT` is honored only when set to a non-empty path. Blank or missing
    values fall back to the package-derived repo root (not the process cwd).
    """
    env_path = repo_root() / ".env"
    if env_path.exists():
        settings = Settings(_env_file=env_path)
    else:
        settings = Settings()

    if settings.root is None:
        settings.root = repo_root()
    else:
        settings.root = Path(settings.root).expanduser().resolve()
    return settings
