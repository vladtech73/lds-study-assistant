"""Heading-aware prose chunking for talks and lessons."""

from __future__ import annotations

import re
from typing import Any

from lds_study.data.models import Chunk, approx_token_count
from lds_study.data.normalize import normalize_prose

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_ALL_CAPS_HEADING = re.compile(r"^[A-Z0-9][A-Z0-9 ,.'\-]{2,80}$")


def _split_sections(text: str) -> tuple[list[tuple[str | None, str]], int]:
    """Split on markdown or all-caps headings.

    Colon-terminated lead-ins (\"The Savior taught three things:\") are body text,
    not headings — treating them as headings silently discarded conference prose.

    Returns (sections, discarded_empty_heading_count).
    """
    lines = text.splitlines()
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buf: list[str] = []
    discarded = 0

    def flush() -> None:
        nonlocal buf, current_heading, discarded
        body = "\n".join(buf).strip()
        if body:
            # Keep the heading string in the body so content is never only in metadata.
            if current_heading and current_heading not in body:
                body = f"{current_heading}\n\n{body}"
            sections.append((current_heading, body))
        elif current_heading:
            # Heading with no following body would otherwise vanish from stats.
            discarded += 1
        buf = []

    for line in lines:
        md = _MARKDOWN_HEADING.match(line.strip())
        if md:
            flush()
            current_heading = md.group(2).strip()
            continue
        stripped = line.strip()
        # Strong heading signal only: all-caps title lines (no colon-as-heading).
        if (
            stripped
            and len(stripped) <= 80
            and not stripped.endswith((".", ":", ";", "!", "?"))
            and _ALL_CAPS_HEADING.match(stripped)
        ):
            flush()
            current_heading = stripped
            continue
        buf.append(line)
    flush()
    return sections, discarded


def _window_tokens(tokens: list[str], size: int, overlap: int) -> list[list[str]]:
    if not tokens:
        return []
    if size <= 0 or len(tokens) <= size:
        return [tokens]
    step = max(1, size - overlap)
    windows: list[list[str]] = []
    i = 0
    while i < len(tokens):
        windows.append(tokens[i : i + size])
        if i + size >= len(tokens):
            break
        i += step
    return windows


def chunk_prose(
    text: str,
    *,
    source_id: str,
    source_type: str,
    redistributable: bool,
    meta: dict[str, Any] | None = None,
    target_tokens: int = 750,
    overlap_tokens: int = 80,
    doc_stem: str = "doc",
    source_path: str | None = None,
) -> tuple[list[Chunk], int]:
    """Return (chunks, empty_dropped)."""
    meta = meta or {}
    cleaned = normalize_prose(text)
    if not cleaned:
        return [], 1

    sections, discarded = _split_sections(cleaned)
    if not sections:
        sections = [(None, cleaned)]

    chunks: list[Chunk] = []
    empty = discarded
    part = 0
    char_offset = 0
    for heading, body in sections:
        body_norm = normalize_prose(body)
        if not body_norm:
            empty += 1
            continue
        tokens = body_norm.split()
        for window in _window_tokens(tokens, target_tokens, overlap_tokens):
            part += 1
            piece = " ".join(window).strip()
            if not piece:
                empty += 1
                continue
            # Offset into this prepare run's normalized body (not the original file).
            needle = piece[:40] if len(piece) >= 40 else piece
            start = body_norm.find(needle)
            abs_offset = char_offset + start if start >= 0 else char_offset
            chunks.append(
                Chunk(
                    id=f"{source_id}/{doc_stem}/{part}",
                    text=piece,
                    source_id=source_id,
                    source_type=source_type,
                    redistributable=redistributable,
                    title=meta.get("title"),
                    author=meta.get("author"),
                    date=meta.get("date"),
                    session=meta.get("session"),
                    url=meta.get("url"),
                    heading=heading,
                    window_index=part,
                    char_offset=abs_offset,
                    source_path=source_path,
                    canonical_ref=_prose_ref(meta, heading, part),
                )
            )
        char_offset += len(body_norm) + 2
    return chunks, empty


def _prose_ref(meta: dict[str, Any], heading: str | None, part: int) -> str:
    title = meta.get("title") or "Untitled"
    author = meta.get("author")
    date = meta.get("date")
    bits = [title]
    if author:
        bits.append(str(author))
    if date:
        bits.append(str(date))
    if heading:
        bits.append(str(heading))
    else:
        bits.append(f"§{part}")
    return " — ".join(bits)


def estimate_tokens(text: str) -> int:
    return approx_token_count(text)
