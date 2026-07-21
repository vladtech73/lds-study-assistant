"""Neighbor verse expansion for scripture hits."""

from __future__ import annotations

from lds_study.data.models import Chunk
from lds_study.index.base import RetrievedHit


def expand_context(
    hits: list[RetrievedHit],
    chunks_by_id: dict[str, Chunk],
    *,
    neighbor_window: int = 2,
) -> list[RetrievedHit]:
    """Pull ±N neighbor verses for scripture hits; preserve hybrid order, dedupe by id."""
    if neighbor_window <= 0:
        return hits

    seen: set[str] = set()
    expanded: list[RetrievedHit] = []

    for hit in hits:
        chunk = hit.chunk
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        expanded.append(hit)

        if chunk.source_type != "scripture":
            continue
        if chunk.volume is None or chunk.book is None or chunk.chapter is None or chunk.verse is None:
            continue

        neighbors: list[RetrievedHit] = []
        for delta in range(-neighbor_window, neighbor_window + 1):
            if delta == 0:
                continue
            verse = chunk.verse + delta
            if verse < 1:
                continue
            nid = f"{chunk.volume}/{chunk.book}/{chunk.chapter}/{verse}"
            if nid in seen:
                continue
            neighbor = chunks_by_id.get(nid)
            if neighbor is None:
                continue
            seen.add(nid)
            neighbors.append(
                RetrievedHit(
                    chunk=neighbor,
                    score=hit.score * 0.5,
                    source="expand",
                    seed_id=chunk.id,
                )
            )
        # Keep neighbors immediately after the seed hit for readable context blocks.
        expanded.extend(neighbors)

    return expanded
