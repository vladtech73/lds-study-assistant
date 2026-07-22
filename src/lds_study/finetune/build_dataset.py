"""Build ShareGPT/chat SFT pairs from redistributable, license-verified chunks only.

Restricted sources (``redistributable: false``) are dropped with a counted warning.
**No flag re-enables them** — there is no ``--allow-restricted`` or equivalent.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from lds_study.config import Settings, get_settings
from lds_study.data.manifest import assert_source_ingestible, load_sources_yaml
from lds_study.data.models import Chunk, SourceRecord
from lds_study.index.chunks_io import load_chunks_jsonl

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BuildDatasetResult:
    pairs_written: int
    restricted_dropped: int
    unverified_dropped: int
    unknown_source_dropped: int
    output_path: Path
    pair_type_counts: dict[str, int] = field(default_factory=dict)


def eligible_source_ids(sources: Sequence[SourceRecord]) -> set[str]:
    """Return source ids that are redistributable and license-verified."""
    ok: set[str] = set()
    for source in sources:
        if not source.redistributable:
            continue
        try:
            assert_source_ingestible(source)
        except Exception:
            continue
        ok.add(source.id)
    return ok


def filter_sft_chunks(
    chunks: Sequence[Chunk],
    *,
    sources: Sequence[SourceRecord],
) -> tuple[list[Chunk], dict[str, int]]:
    """Keep only redistributable + license-verified chunks.

    Restricted rows are dropped unconditionally (no override).
    """
    by_id = {s.id: s for s in sources}
    eligible = eligible_source_ids(sources)
    kept: list[Chunk] = []
    restricted = 0
    unverified = 0
    unknown = 0

    for chunk in chunks:
        source = by_id.get(chunk.source_id)
        if source is None:
            unknown += 1
            continue
        if not chunk.redistributable or not source.redistributable:
            restricted += 1
            continue
        if chunk.source_id not in eligible:
            unverified += 1
            continue
        kept.append(chunk)
    return kept, {
        "restricted_dropped": restricted,
        "unverified_dropped": unverified,
        "unknown_source_dropped": unknown,
    }


def _sharegpt(human: str, gpt: str) -> dict[str, Any]:
    return {
        "conversations": [
            {"from": "human", "value": human},
            {"from": "gpt", "value": gpt},
        ]
    }


def _explain_pair(chunk: Chunk) -> dict[str, Any] | None:
    ref = chunk.canonical_ref or chunk.id
    text = (chunk.text or "").strip()
    if not text:
        return None
    human = (
        f"Explain {ref} in plain language for personal study. "
        f"Quote or paraphrase only from the verse and cite it with [[{chunk.id}]]."
    )
    gpt = (
        f"{ref} teaches: {text}\n\n"
        f"In short, this passage invites careful attention to its counsel. "
        f"[[{chunk.id}]]"
    )
    return _sharegpt(human, gpt)


def _cross_ref_pair(a: Chunk, b: Chunk) -> dict[str, Any] | None:
    if a.id == b.id:
        return None
    ref_a = a.canonical_ref or a.id
    ref_b = b.canonical_ref or b.id
    text_a = (a.text or "").strip()
    text_b = (b.text or "").strip()
    if not text_a or not text_b:
        return None
    human = (
        f"How does {ref_a} relate to {ref_b}? "
        f"Use both passages and cite [[{a.id}]] and [[{b.id}]]."
    )
    gpt = (
        f"{ref_a} says: {text_a} [[{a.id}]]\n\n"
        f"{ref_b} continues the thought: {text_b} [[{b.id}]]\n\n"
        f"Read together, they reinforce one another for study and teaching."
    )
    return _sharegpt(human, gpt)


def _lesson_pair(chunk: Chunk) -> dict[str, Any] | None:
    ref = chunk.canonical_ref or chunk.id
    text = (chunk.text or "").strip()
    if not text:
        return None
    human = (
        f"Draft a short lesson outline (3 bullet points) focused on {ref}. "
        f"Ground every point in the verse and cite [[{chunk.id}]]."
    )
    gpt = (
        f"Lesson focus: {ref}\n"
        f"- Read the verse aloud and note key phrases. [[{chunk.id}]]\n"
        f"- Discuss: {text[:240]}{'…' if len(text) > 240 else ''} [[{chunk.id}]]\n"
        f"- Invite application: what will you practice this week from {ref}? "
        f"[[{chunk.id}]]"
    )
    return _sharegpt(human, gpt)


def generate_pairs(
    chunks: Sequence[Chunk],
    *,
    max_pairs: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build explain / cross-reference / lesson-outline pairs."""
    pairs: list[dict[str, Any]] = []
    counts = {"explain_verse": 0, "cross_reference": 0, "lesson_outline": 0}

    scripture = [
        c
        for c in chunks
        if c.source_type == "scripture" and (c.text or "").strip()
    ]
    # Prefer scripture; fall back to any kept prose if needed.
    pool = scripture or [c for c in chunks if (c.text or "").strip()]

    for chunk in pool:
        if max_pairs is not None and len(pairs) >= max_pairs:
            break
        row = _explain_pair(chunk)
        if row:
            pairs.append(row)
            counts["explain_verse"] += 1

    # Same-chapter neighbors for cross-reference.
    by_chapter: dict[tuple[str | None, str | None, int | None], list[Chunk]] = {}
    for chunk in pool:
        key = (chunk.volume, chunk.book, chunk.chapter)
        by_chapter.setdefault(key, []).append(chunk)

    for group in by_chapter.values():
        ordered = sorted(group, key=lambda c: (c.verse or 0, c.id))
        for i in range(len(ordered) - 1):
            if max_pairs is not None and len(pairs) >= max_pairs:
                break
            row = _cross_ref_pair(ordered[i], ordered[i + 1])
            if row:
                pairs.append(row)
                counts["cross_reference"] += 1

    for chunk in pool:
        if max_pairs is not None and len(pairs) >= max_pairs:
            break
        row = _lesson_pair(chunk)
        if row:
            pairs.append(row)
            counts["lesson_outline"] += 1

    if max_pairs is not None:
        pairs = pairs[:max_pairs]
    return pairs, counts


def write_sft_jsonl(pairs: Sequence[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in pairs:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(pairs)


def build_sft_dataset(
    *,
    chunks_path: Path | None = None,
    output_path: Path | None = None,
    sources_path: Path | None = None,
    max_pairs: int | None = None,
    settings: Settings | None = None,
) -> BuildDatasetResult:
    """Load prepare output, drop restricted/unverified, write ``sft.jsonl``."""
    settings = settings or get_settings()
    chunks_path = chunks_path or settings.resolve(settings.data_dir / "processed" / "chunks.jsonl")
    output_path = output_path or settings.resolve(settings.data_dir / "processed" / "sft.jsonl")
    sources_path = sources_path or (settings.configs_dir / "sources.yaml")

    sources = load_sources_yaml(sources_path)
    chunks = load_chunks_jsonl(chunks_path)
    kept, drops = filter_sft_chunks(chunks, sources=sources)

    if drops["restricted_dropped"]:
        logger.warning(
            "Dropped %s restricted (redistributable=false) chunk(s); "
            "no flag can re-include them.",
            drops["restricted_dropped"],
        )
    if drops["unverified_dropped"]:
        logger.warning(
            "Dropped %s chunk(s) from sources that are not license-verified "
            "for redistributable SFT.",
            drops["unverified_dropped"],
        )
    if drops["unknown_source_dropped"]:
        logger.warning(
            "Dropped %s chunk(s) with unknown source_id (not in sources.yaml).",
            drops["unknown_source_dropped"],
        )

    pairs, type_counts = generate_pairs(kept, max_pairs=max_pairs)
    written = write_sft_jsonl(pairs, output_path)
    return BuildDatasetResult(
        pairs_written=written,
        restricted_dropped=drops["restricted_dropped"],
        unverified_dropped=drops["unverified_dropped"],
        unknown_source_dropped=drops["unknown_source_dropped"],
        output_path=output_path,
        pair_type_counts=type_counts,
    )


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Build data/processed/sft.jsonl from redistributable, license-verified "
            "chunks only. Restricted sources are always excluded."
        )
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=None,
        help="Input chunks.jsonl (default: data/processed/chunks.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output ShareGPT JSONL (default: data/processed/sft.jsonl)",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=None,
        help="sources.yaml path (default: configs/sources.yaml)",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=None,
        help="Cap total pairs (useful for --max-steps 20 debug trains)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = build_sft_dataset(
        chunks_path=args.chunks,
        output_path=args.output,
        sources_path=args.sources,
        max_pairs=args.max_pairs,
    )
    print(
        f"Wrote {result.pairs_written} pairs → {result.output_path} "
        f"(restricted_dropped={result.restricted_dropped}, "
        f"types={result.pair_type_counts})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
