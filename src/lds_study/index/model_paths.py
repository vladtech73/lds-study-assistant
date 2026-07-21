"""Resolve HF repo ids to local `models/` snapshots from `lds pull-models`."""

from __future__ import annotations


from rich.console import Console

from lds_study.config import Settings, get_settings

console = Console()


def hf_snapshot_dirname(repo_id: str) -> str:
    return repo_id.replace("/", "--")


def resolve_model_path(
    repo_id: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, bool]:
    """Return (load_path, is_local).

    Prefers `models/{org--name}` written by pull-models; falls back to the hub id.
    Requires `config.json` so a partial download is not treated as complete.
    """
    settings = settings or get_settings()
    local = settings.resolve(settings.models_dir) / hf_snapshot_dirname(repo_id)
    if local.is_dir() and (local / "config.json").is_file():
        return str(local), True
    return repo_id, False
