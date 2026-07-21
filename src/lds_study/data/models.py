"""Shared data models for prepare / chunk / export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Chunk:
    """One retrieval unit written to chunks.jsonl."""

    id: str
    text: str
    source_id: str
    source_type: str  # scripture | talk | lesson | prose
    redistributable: bool
    volume: str | None = None
    book: str | None = None
    chapter: int | None = None
    verse: int | None = None
    canonical_ref: str | None = None
    title: str | None = None
    author: str | None = None
    date: str | None = None
    session: str | None = None
    url: str | None = None
    heading: str | None = None
    # Window ordinal within the normalized section body for this prepare run.
    window_index: int | None = None
    # Character offset into the normalized, heading-prepended section text produced
    # during this prepare run — not a seek offset into the original ePub/PDF/HTML file.
    char_offset: int | None = None
    # Relative path of the BYOF source file when known (for collision diagnostics).
    source_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra") or {}
        # Drop Nones for a compact JSONL line; keep empty string texts only if present.
        out = {k: v for k, v in data.items() if v is not None}
        if extra:
            out["extra"] = extra
        return out


@dataclass(slots=True)
class SourceRecord:
    """One entry from configs/sources.yaml."""

    id: str
    type: str
    loader: str
    path_or_url: str
    license: str
    license_url: str | None
    verified_on: str | None
    redistributable: bool
    notes: str = ""
    volume: str | None = None
    expected_sha256: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> SourceRecord:
        required = ("id", "type", "loader", "path_or_url", "license", "redistributable")
        missing = [k for k in required if k not in raw]
        if missing:
            raise ValueError(f"source entry missing fields: {missing}")
        return cls(
            id=str(raw["id"]),
            type=str(raw["type"]),
            loader=str(raw["loader"]),
            path_or_url=str(raw["path_or_url"]),
            license=str(raw["license"]),
            license_url=(str(raw["license_url"]) if raw.get("license_url") else None),
            verified_on=(str(raw["verified_on"]) if raw.get("verified_on") else None),
            redistributable=bool(raw["redistributable"]),
            notes=str(raw.get("notes") or ""),
            volume=(str(raw["volume"]) if raw.get("volume") else None),
            expected_sha256=(str(raw["expected_sha256"]) if raw.get("expected_sha256") else None),
        )


@dataclass(slots=True)
class PrepareStats:
    source_id: str
    chunk_count: int = 0
    empty_dropped: int = 0
    token_lengths: list[int] = field(default_factory=list)

    def add_chunk(self, text: str) -> None:
        tokens = approx_token_count(text)
        self.token_lengths.append(tokens)
        self.chunk_count += 1

    def summary(self) -> dict[str, Any]:
        lengths = self.token_lengths
        if lengths:
            hist = _histogram(lengths)
            avg = sum(lengths) / len(lengths)
        else:
            hist = {}
            avg = 0.0
        return {
            "source_id": self.source_id,
            "chunk_count": self.chunk_count,
            "empty_dropped": self.empty_dropped,
            "token_avg": round(avg, 2),
            "token_histogram": hist,
        }


def approx_token_count(text: str) -> int:
    """Whitespace token estimate — good enough for prepare stats histograms."""
    return len(text.split()) if text.strip() else 0


def _histogram(lengths: list[int], bucket: int = 50) -> dict[str, int]:
    counts: dict[str, int] = {}
    for n in lengths:
        lo = (n // bucket) * bucket
        key = f"{lo}-{lo + bucket - 1}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: int(kv[0].split("-")[0])))
