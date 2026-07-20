"""Load and enforce configs/sources.yaml license rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lds_study.data.models import SourceRecord


class UnverifiedSourceError(RuntimeError):
    """Raised when a source still has license: unverified."""


class ManifestError(RuntimeError):
    """Invalid sources.yaml or download manifest."""


def load_sources_yaml(path: Path) -> list[SourceRecord]:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ManifestError(f"{path} must be a mapping")
    entries = raw.get("sources") or []
    if not isinstance(entries, list):
        raise ManifestError(f"{path}: 'sources' must be a list")
    return [SourceRecord.from_mapping(item) for item in entries]


def assert_source_ingestible(source: SourceRecord) -> None:
    """Refuse unverified licenses. New sources stay unverified until filled in."""
    if source.license.strip().lower() == "unverified":
        raise UnverifiedSourceError(
            f"Source '{source.id}' has license: unverified. "
            "Fill license, license_url, and verified_on in configs/sources.yaml "
            "after checking the text-vs-edition posture (see docs/LEGAL.md)."
        )
    if not source.license_url:
        raise UnverifiedSourceError(
            f"Source '{source.id}' is missing license_url. "
            "Record where the license claim was verified."
        )
    if not source.verified_on:
        raise UnverifiedSourceError(
            f"Source '{source.id}' is missing verified_on (YYYY-MM-DD). "
            "Set it when a human confirms the license_url claim."
        )


def load_download_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"artifacts": {}}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if isinstance(data, dict) and "artifacts" in data:
        return data
    # JSON-compatible files may be loaded via yaml; also accept pure JSON dicts.
    if isinstance(data, dict):
        data.setdefault("artifacts", {})
        return data
    raise ManifestError(f"{path} must contain an object with 'artifacts'")


def save_download_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer JSON for MANIFEST.json as specified in the plan.
    import json

    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def filter_exportable(chunks: list[Any]) -> list[Any]:
    """Unconditionally drop redistributable=False records. No override flag exists."""
    return [c for c in chunks if getattr(c, "redistributable", False)]
