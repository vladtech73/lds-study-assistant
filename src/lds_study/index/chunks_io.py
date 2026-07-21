"""Load chunks.jsonl produced by `lds prepare`."""

from __future__ import annotations

import json
from pathlib import Path

from lds_study.data.models import Chunk


def load_chunks_jsonl(path: Path) -> list[Chunk]:
    """Parse prepare output into Chunk objects."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing chunks file: {path}. Run `lds prepare` first."
        )
    chunks: list[Chunk] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            chunks.append(_chunk_from_dict(raw))
    return chunks


def chunks_by_id(chunks: list[Chunk]) -> dict[str, Chunk]:
    return {c.id: c for c in chunks}


def _chunk_from_dict(raw: dict) -> Chunk:
    known = {
        "id",
        "text",
        "source_id",
        "source_type",
        "redistributable",
        "volume",
        "book",
        "chapter",
        "verse",
        "canonical_ref",
        "title",
        "author",
        "date",
        "session",
        "url",
        "heading",
        "window_index",
        "char_offset",
        "source_path",
        "extra",
    }
    extra = dict(raw.get("extra") or {})
    for key, value in raw.items():
        if key not in known:
            extra[key] = value
    return Chunk(
        id=str(raw["id"]),
        text=str(raw["text"]),
        source_id=str(raw["source_id"]),
        source_type=str(raw["source_type"]),
        redistributable=bool(raw.get("redistributable", False)),
        volume=_opt_str(raw.get("volume")),
        book=_opt_str(raw.get("book")),
        chapter=_opt_int(raw.get("chapter")),
        verse=_opt_int(raw.get("verse")),
        canonical_ref=_opt_str(raw.get("canonical_ref")),
        title=_opt_str(raw.get("title")),
        author=_opt_str(raw.get("author")),
        date=_opt_str(raw.get("date")),
        session=_opt_str(raw.get("session")),
        url=_opt_str(raw.get("url")),
        heading=_opt_str(raw.get("heading")),
        window_index=_opt_int(raw.get("window_index")),
        char_offset=_opt_int(raw.get("char_offset")),
        source_path=_opt_str(raw.get("source_path")),
        extra=extra,
    )


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _opt_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
