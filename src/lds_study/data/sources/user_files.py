"""Bring-your-own-file loaders for Conference / Come, Follow Me material."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from lds_study.data.chunk_prose import chunk_prose
from lds_study.data.models import Chunk, PrepareStats, SourceRecord
from lds_study.data.normalize import normalize_prose

SUPPORTED_SUFFIXES = {".epub", ".pdf", ".html", ".htm", ".txt", ".md"}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip = True
        if tag in {"h1", "h2", "h3", "h4", "p", "div", "br", "li"}:
            self._chunks.append("\n")
        if tag in {"h1", "h2", "h3", "h4"}:
            # Keep markdown-ish heading markers for chunk_prose.
            level = int(tag[1])
            self._chunks.append("#" * level + " ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "li"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def load_user_files(
    source: SourceRecord,
    *,
    root: Path,
    target_tokens: int = 750,
    overlap_tokens: int = 80,
) -> tuple[list[Chunk], PrepareStats]:
    base = Path(source.path_or_url)
    if not base.is_absolute():
        base = (root / base).resolve()
    if not base.exists():
        from rich.console import Console

        Console().print(
            f"[yellow]user_files:[/yellow] path not found for source "
            f"'{source.id}': {base} (skipping; check path_or_url)"
        )
        stats = PrepareStats(source_id=source.id)
        return [], stats

    files = sorted(
        p
        for p in base.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and p.name != "EXAMPLE.meta.json"
        and not p.name.endswith(".meta.json")
    )

    chunks: list[Chunk] = []
    stats = PrepareStats(source_id=source.id)
    for path in files:
        meta = _load_meta(path)
        text, file_meta = _extract(path)
        meta = {**file_meta, **meta}
        source_type = _infer_type(source.type, meta, path)
        doc_stem = _doc_stem(path, base)
        try:
            rel_path = str(path.resolve().relative_to(base.resolve()))
        except ValueError:
            rel_path = path.name
        part_chunks, empty = chunk_prose(
            text,
            source_id=source.id,
            source_type=source_type,
            redistributable=source.redistributable,
            meta=meta,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            doc_stem=doc_stem,
            source_path=rel_path.replace("\\", "/"),
        )
        stats.empty_dropped += empty
        for chunk in part_chunks:
            stats.add_chunk(chunk.text)
            chunks.append(chunk)
    return chunks, stats


def _extract(path: Path) -> tuple[str, dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return _extract_epub(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".html", ".htm"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _html_to_text(raw), {}
    # .txt / .md
    return path.read_text(encoding="utf-8", errors="replace"), {}


def _extract_epub(path: Path) -> tuple[str, dict[str, Any]]:
    from ebooklib import epub
    from ebooklib import ITEM_DOCUMENT

    book = epub.read_epub(str(path))
    meta: dict[str, Any] = {}
    titles = book.get_metadata("DC", "title")
    if titles:
        meta["title"] = titles[0][0]
    authors = book.get_metadata("DC", "creator")
    if authors:
        meta["author"] = authors[0][0]
    dates = book.get_metadata("DC", "date")
    if dates:
        meta["date"] = str(dates[0][0])[:10]

    parts: list[str] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        name = item.get_name() or ""
        if "nav" in name.lower():
            continue
        raw = item.get_content().decode("utf-8", errors="replace")
        parts.append(_html_to_text(raw))
    return "\n\n".join(parts), meta


def _extract_pdf(path: Path) -> tuple[str, dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    meta: dict[str, Any] = {}
    info = reader.metadata
    if info:
        if info.title:
            meta["title"] = str(info.title)
        if info.author:
            meta["author"] = str(info.author)
        # Creation date like D:20240108000000Z
        raw_date = getattr(info, "creation_date", None) or (info.get("/CreationDate") if hasattr(info, "get") else None)
        if raw_date:
            meta["date"] = _parse_pdf_date(str(raw_date))

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — PDF text extraction is best-effort
            pages.append("")
    text = "\n".join(pages)
    # Many minimal PDFs lack an embedded font → empty extract; keep metadata path working.
    # De-hyphenate before collapsing newlines so experi-\nment survives.
    return normalize_prose(text), meta


def _parse_pdf_date(value: str) -> str:
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", value)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if re.match(r"\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return value[:10]


def _html_to_text(raw: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    return normalize_prose(parser.text())


def _load_meta(path: Path) -> dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".meta.json")
    # Prefer stem.meta.json (EXAMPLE.meta.json style): talk.pdf → talk.meta.json
    alt = path.with_name(path.stem + ".meta.json")
    for candidate in (alt, sidecar):
        if candidate.exists():
            with candidate.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if v is not None}
    return {}


def _infer_type(declared: str, meta: dict[str, Any], path: Path) -> str:
    if declared in {"talk", "lesson", "prose"}:
        return declared
    title = (meta.get("title") or path.stem).lower()
    if "come follow me" in title or "lesson" in title:
        return "lesson"
    return "talk"


def _doc_stem(path: Path, base: Path) -> str:
    """Slugify path relative to BYOF root, including extension.

    Includes the suffix so talk.txt and talk.md in the same folder do not collide
    (Gospel Library exports often ship both).
    Example: 2023/talk.txt → 2023-talk-txt
    """
    try:
        rel = path.resolve().relative_to(base.resolve())
    except ValueError:
        rel = Path(path.name)
    suffix = rel.suffix.lstrip(".").lower() or "bin"
    parts = list(rel.parts[:-1]) + [rel.stem, suffix]
    return _slug("-".join(parts))


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "doc"
