"""Verse-atomic scripture chunking."""

from __future__ import annotations

import re
from typing import Any, Iterable

from lds_study.data.models import Chunk
from lds_study.data.normalize import normalize_scripture

VOLUME_SLUGS = {
    "old testament": "ot",
    "new testament": "nt",
    "book of mormon": "bofm",
    "doctrine and covenants": "dc",
    "pearl of great price": "pgp",
}

# Display abbreviations for canonical_ref when book_title is long.
BOOK_DISPLAY = {
    "doctrine and covenants": "D&C",
    "joseph smith--matthew": "JS—M",
    "joseph smith--history": "JS—H",
    "words of mormon": "W of M",
    "articles of faith": "A of F",
}

_BOOK_SLUG_RE = re.compile(r"[^a-z0-9]+")


def volume_slug(volume_title: str) -> str:
    key = volume_title.strip().lower()
    if key not in VOLUME_SLUGS:
        raise ValueError(f"Unknown volume_title: {volume_title!r}")
    return VOLUME_SLUGS[key]


def book_slug(book_title: str) -> str:
    title = book_title.strip().lower().replace("'", "")
    # Normalize fancy dashes used in Joseph Smith--History style titles.
    title = title.replace("—", "--").replace("–", "--")
    slug = _BOOK_SLUG_RE.sub("-", title).strip("-")
    if slug in {"doctrine-and-covenants", "d-c", "dc"}:
        return "dc"
    return slug


def canonical_reference(book_title: str, chapter: int, verse: int) -> str:
    key = book_title.strip().lower().replace("—", "--")
    display = BOOK_DISPLAY.get(key, book_title.strip())
    return f"{display} {chapter}:{verse}"


def chunk_id(volume: str, book: str, chapter: int, verse: int) -> str:
    return f"{volume}/{book}/{chapter}/{verse}"


def verse_record_to_chunk(
    record: dict[str, Any],
    *,
    source_id: str,
    redistributable: bool,
) -> Chunk | None:
    text = normalize_scripture(str(record.get("scripture_text") or ""))
    if not text:
        return None
    book_title = str(record["book_title"])
    chapter = int(record["chapter_number"])
    verse = int(record["verse_number"])
    vol = volume_slug(str(record["volume_title"]))
    book = book_slug(book_title)
    # Prefer mirror-provided title when present (already apparatus-free in nephi dumps).
    ref = str(record.get("verse_title") or "").strip() or canonical_reference(
        book_title, chapter, verse
    )
    return Chunk(
        id=chunk_id(vol, book, chapter, verse),
        text=text,
        source_id=source_id,
        source_type="scripture",
        redistributable=redistributable,
        volume=vol,
        book=book,
        chapter=chapter,
        verse=verse,
        canonical_ref=ref,
    )


def chunk_scripture_records(
    records: Iterable[dict[str, Any]],
    *,
    source_id: str,
    redistributable: bool,
) -> tuple[list[Chunk], int]:
    """Return (chunks, empty_dropped)."""
    chunks: list[Chunk] = []
    empty = 0
    for record in records:
        chunk = verse_record_to_chunk(
            record, source_id=source_id, redistributable=redistributable
        )
        if chunk is None:
            empty += 1
            continue
        chunks.append(chunk)
    return chunks, empty
