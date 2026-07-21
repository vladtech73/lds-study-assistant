"""Public scripture loaders (nephi / beandog JSON mirror)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from lds_study.data.chunk_scripture import chunk_scripture_records
from lds_study.data.manifest import (
    ManifestError,
    load_download_manifest,
    save_download_manifest,
)
from lds_study.data.models import Chunk, PrepareStats, SourceRecord

DEFAULT_USER_AGENT = "lds-study-assistant/0.1 (personal-use; offline RAG)"


def load_verse_json(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ManifestError(f"{path} must be a JSON array of verse objects")
    return data


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_local_scripture_path(path_or_url: str, root: Path) -> Path | None:
    """Return a local path if path_or_url points at an existing file/dir."""
    candidate = Path(path_or_url)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    if candidate.exists():
        return candidate
    return None


def ensure_scripture_artifact(
    source: SourceRecord,
    *,
    raw_public_dir: Path,
    refresh: bool = False,
) -> Path:
    """
    Ensure the scripture JSON (or zip containing it) is on disk under raw/public.

    Records URL + sha256 + timestamp in data/raw/public/MANIFEST.json.
    A changed hash fails unless --refresh.
    """
    repo_root = raw_public_dir.parents[2]  # data/raw/public → repo root
    local = resolve_local_scripture_path(source.path_or_url, repo_root)
    if local is not None and local.is_file() and not _looks_like_url(source.path_or_url):
        # Fixture / already-local path — still record hash for integrity.
        digest = sha256_file(local)
        if source.expected_sha256 and digest != source.expected_sha256 and not refresh:
            raise ManifestError(
                f"Source '{source.id}' local file sha256 {digest} does not match "
                f"expected_sha256 {source.expected_sha256}."
            )
        _update_manifest(
            raw_public_dir / "MANIFEST.json",
            source_id=source.id,
            url=str(local),
            sha256=digest,
            local_path=str(local),
            refresh=refresh,
            expected=None,  # already checked above for local fixtures
        )
        return local

    if local is not None and local.is_dir():
        json_files = sorted(local.rglob("*.json")) + sorted(local.rglob("*-json.txt"))
        if not json_files:
            raise ManifestError(f"No scripture JSON under {local}")
        return json_files[0]

    if not _looks_like_url(source.path_or_url):
        raise ManifestError(
            f"Source '{source.id}' path not found: {source.path_or_url}. "
            "Place the file under data/raw/public/ or set a downloadable URL."
        )

    dest_dir = raw_public_dir / source.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = source.path_or_url.rstrip("/").split("/")[-1] or f"{source.id}.json"
    dest = dest_dir / filename

    manifest_path = raw_public_dir / "MANIFEST.json"
    existing = load_download_manifest(manifest_path)
    prior = (existing.get("artifacts") or {}).get(source.id) or {}

    if dest.exists() and not refresh:
        digest = sha256_file(dest)
        if source.expected_sha256 and digest != source.expected_sha256:
            raise ManifestError(
                f"Source '{source.id}' local file sha256 {digest} does not match "
                f"expected_sha256 {source.expected_sha256}. Re-download with --refresh "
                "after verifying the mirror, or fix the expected hash."
            )
        if prior.get("sha256") and prior["sha256"] != digest:
            raise ManifestError(
                f"Source '{source.id}' sha256 changed since last prepare "
                f"(was {prior['sha256']}, now {digest}). Pass --refresh to accept."
            )
        return _maybe_unzip(dest, dest_dir)

    data = _download(source.path_or_url)
    digest = sha256_bytes(data)
    if source.expected_sha256 and digest != source.expected_sha256 and not refresh:
        raise ManifestError(
            f"Downloaded '{source.id}' sha256 {digest} != expected "
            f"{source.expected_sha256}. Inspect the mirror before --refresh."
        )
    if prior.get("sha256") and prior["sha256"] != digest and not refresh:
        raise ManifestError(
            f"Source '{source.id}' sha256 changed (was {prior['sha256']}, now {digest}). "
            "Pass --refresh to accept the new artifact deliberately."
        )

    dest.write_bytes(data)
    _update_manifest(
        manifest_path,
        source_id=source.id,
        url=source.path_or_url,
        sha256=digest,
        local_path=str(dest),
        refresh=True,
        expected=source.expected_sha256,
    )
    return _maybe_unzip(dest, dest_dir)


def load_public_scripture(
    source: SourceRecord,
    *,
    artifact_path: Path,
) -> tuple[list[Chunk], PrepareStats]:
    records = _load_records(artifact_path)
    chunks, empty = chunk_scripture_records(
        records,
        source_id=source.id,
        redistributable=source.redistributable,
    )
    stats = PrepareStats(source_id=source.id, empty_dropped=empty)
    for chunk in chunks:
        stats.add_chunk(chunk.text)
    return chunks, stats


def _load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".zip":
        raise ManifestError(f"Pass an extracted JSON path, not zip: {path}")
    if path.is_dir():
        files = sorted(path.rglob("*.json")) + sorted(path.rglob("*-json.txt"))
        if not files:
            raise ManifestError(f"No JSON under {path}")
        path = files[0]
    return load_verse_json(path)


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _download(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urlopen(req, timeout=120) as resp:  # noqa: S310 — intentional user-configured URL
            return resp.read()
    except URLError as exc:
        raise ManifestError(f"Failed to download {url}: {exc}") from exc


def _maybe_unzip(path: Path, dest_dir: Path) -> Path:
    if path.suffix.lower() != ".zip":
        return path
    with zipfile.ZipFile(path) as zf:
        zf.extractall(dest_dir)
    json_files = sorted(dest_dir.rglob("*-json.txt")) + sorted(dest_dir.rglob("*.json"))
    json_files = [p for p in json_files if p.name.lower() != "manifest.json"]
    if not json_files:
        raise ManifestError(f"Zip {path} contained no scripture JSON")
    # Prefer the combined lds-scriptures dump when present.
    for preferred in json_files:
        if "lds-scriptures" in preferred.name.lower():
            return preferred
    return json_files[0]


def _update_manifest(
    path: Path,
    *,
    source_id: str,
    url: str,
    sha256: str,
    local_path: str,
    refresh: bool,
    expected: str | None,
) -> None:
    data = load_download_manifest(path)
    artifacts = data.setdefault("artifacts", {})
    prior = artifacts.get(source_id) or {}
    if prior.get("sha256") and prior["sha256"] != sha256 and not refresh:
        raise ManifestError(
            f"Source '{source_id}' sha256 changed (was {prior['sha256']}, now {sha256}). "
            "Pass --refresh to accept."
        )
    if expected and expected != sha256 and not refresh:
        raise ManifestError(
            f"Source '{source_id}' sha256 {sha256} != expected_sha256 {expected}."
        )
    artifacts[source_id] = {
        "url": url,
        "sha256": sha256,
        "local_path": local_path,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    save_download_manifest(path, data)
