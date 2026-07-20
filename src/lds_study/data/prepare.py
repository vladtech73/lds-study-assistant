"""Orchestrate `lds prepare`: ingest → normalize → chunk → chunks.jsonl."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from lds_study.config import Settings, get_settings
from lds_study.data.manifest import (
    ManifestError,
    UnverifiedSourceError,
    assert_source_ingestible,
    filter_exportable,
    load_sources_yaml,
)
from lds_study.data.models import Chunk, PrepareStats, SourceRecord
from lds_study.data.sources.public_scripture import (
    ensure_scripture_artifact,
    load_public_scripture,
)
from lds_study.data.sources.user_files import load_user_files


@dataclass(slots=True)
class PrepareResult:
    chunks_path: Path
    stats_path: Path
    chunks: list[Chunk]
    stats: list[dict[str, Any]]
    empty_total: int


def run_prepare(
    *,
    settings: Settings | None = None,
    source_ids: list[str] | None = None,
    scripture_only: bool = False,
    refresh: bool = False,
    show_stats: bool = False,
) -> PrepareResult:
    settings = settings or get_settings()
    root = settings.effective_root
    sources_path = settings.configs_dir / "sources.yaml"
    sources = load_sources_yaml(sources_path)

    if source_ids:
        wanted = set(source_ids)
        sources = [s for s in sources if s.id in wanted]
        missing = wanted - {s.id for s in sources}
        if missing:
            raise ManifestError(f"Unknown source id(s): {sorted(missing)}")

    if scripture_only:
        sources = [s for s in sources if s.loader == "public_scripture"]

    rag = _load_rag(settings)
    target_tokens = int(rag.get("chunking", {}).get("prose_tokens", 750))
    overlap_tokens = int(rag.get("chunking", {}).get("prose_overlap_tokens", 80))

    data_dir = settings.resolve(settings.data_dir)
    raw_public = data_dir / "raw" / "public"
    processed = data_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    raw_public.mkdir(parents=True, exist_ok=True)

    all_chunks: list[Chunk] = []
    all_stats: list[dict[str, Any]] = []

    for source in sources:
        assert_source_ingestible(source)
        chunks, stats = _ingest_one(
            source,
            root=root,
            raw_public=raw_public,
            refresh=refresh,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
        all_chunks.extend(chunks)
        all_stats.append(stats.summary())

    _assert_unique_chunk_ids(all_chunks)

    chunks_path = processed / "chunks.jsonl"
    stats_path = processed / "prepare_stats.json"
    _write_jsonl(chunks_path, all_chunks)
    empty_total = sum(int(s.get("empty_dropped", 0)) for s in all_stats)
    report = {
        "sources": all_stats,
        "total_chunks": len(all_chunks),
        "empty_dropped_total": empty_total,
        "exportable_chunks": len(filter_exportable(all_chunks)),
    }
    stats_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if show_stats:
        _print_stats(report)

    return PrepareResult(
        chunks_path=chunks_path,
        stats_path=stats_path,
        chunks=all_chunks,
        stats=all_stats,
        empty_total=empty_total,
    )


def prepare_from_records(
    records: list[dict[str, Any]],
    *,
    source: SourceRecord,
) -> tuple[list[Chunk], PrepareStats]:
    """Test helper: chunk in-memory nephi-format verse records."""
    from lds_study.data.chunk_scripture import chunk_scripture_records

    chunks, empty = chunk_scripture_records(
        records,
        source_id=source.id,
        redistributable=source.redistributable,
    )
    stats = PrepareStats(source_id=source.id, empty_dropped=empty)
    for chunk in chunks:
        stats.add_chunk(chunk.text)
    return chunks, stats


def _ingest_one(
    source: SourceRecord,
    *,
    root: Path,
    raw_public: Path,
    refresh: bool,
    target_tokens: int,
    overlap_tokens: int,
) -> tuple[list[Chunk], PrepareStats]:
    if source.loader == "public_scripture":
        artifact = ensure_scripture_artifact(
            source, raw_public_dir=raw_public, refresh=refresh
        )
        return load_public_scripture(source, artifact_path=artifact)
    if source.loader == "user_files":
        return load_user_files(
            source,
            root=root,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
    raise ManifestError(f"Unknown loader '{source.loader}' for source '{source.id}'")


def _write_jsonl(path: Path, chunks: list[Chunk]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.to_json(), ensure_ascii=False) + "\n")


def _assert_unique_chunk_ids(chunks: list[Chunk]) -> None:
    from collections import defaultdict

    by_id: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        by_id[chunk.id].append(chunk)
    dupes = {cid: group for cid, group in by_id.items() if len(group) > 1}
    if not dupes:
        return

    details: list[str] = []
    for cid in sorted(dupes)[:5]:
        paths = sorted(
            {
                c.source_path or c.canonical_ref or c.title or "(unknown source)"
                for c in dupes[cid]
            }
        )
        details.append(f"{cid} ← {', '.join(paths)}")
    raise ManifestError(
        f"Duplicate chunk id(s) after prepare ({len(dupes)} unique collisions). "
        f"Offending sources: {'; '.join(details)}. "
        "Distinct relative paths (including file extension) are required under the BYOF root."
    )


def _load_rag(settings: Settings) -> dict[str, Any]:
    path = settings.configs_dir / "rag.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _print_stats(report: dict[str, Any]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="prepare stats")
    table.add_column("source")
    table.add_column("chunks", justify="right")
    table.add_column("empty dropped", justify="right")
    table.add_column("token avg", justify="right")
    for row in report["sources"]:
        table.add_row(
            str(row["source_id"]),
            str(row["chunk_count"]),
            str(row["empty_dropped"]),
            str(row["token_avg"]),
        )
    console.print(table)
    console.print(
        f"total_chunks={report['total_chunks']}  "
        f"empty_dropped_total={report['empty_dropped_total']}  "
        f"exportable={report['exportable_chunks']}"
    )


def load_verse_counts(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ManifestError(f"{path} must be a mapping")
    return data


__all__ = [
    "PrepareResult",
    "UnverifiedSourceError",
    "ManifestError",
    "run_prepare",
    "prepare_from_records",
    "filter_exportable",
    "load_verse_counts",
]
