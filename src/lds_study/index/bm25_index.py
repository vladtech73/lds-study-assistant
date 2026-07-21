"""BM25 sparse index persisted beside Chroma under indexes/{profile}/."""

from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from rank_bm25 import BM25Okapi

from lds_study.data.models import Chunk
from lds_study.index.base import RetrievalFilters

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class BM25Index:
    """In-memory BM25 over chunk ids with on-disk pickle + id list."""

    ids: list[str]
    _bm25: BM25Okapi
    _id_to_pos: dict[str, int]

    @classmethod
    def build(cls, chunks: Sequence[Chunk]) -> BM25Index:
        # Last write wins for duplicate ids (should not happen after prepare gate).
        by_id: dict[str, Chunk] = {}
        for chunk in chunks:
            by_id[chunk.id] = chunk
        ordered = list(by_id.values())
        ids = [c.id for c in ordered]
        corpus = [tokenize(c.text) for c in ordered]
        bm25 = BM25Okapi(corpus)
        return cls(ids=ids, _bm25=bm25, _id_to_pos={i: n for n, i in enumerate(ids)})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ids": self.ids,
            "bm25": self._bm25,
        }
        with path.open("wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        meta = path.with_suffix(".meta.json")
        meta.write_text(
            json.dumps({"count": len(self.ids), "format": "bm25-pickle-v1"}, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        with path.open("rb") as fh:
            payload = pickle.load(fh)
        ids: list[str] = list(payload["ids"])
        bm25: BM25Okapi = payload["bm25"]
        return cls(ids=ids, _bm25=bm25, _id_to_pos={i: n for n, i in enumerate(ids)})

    def query(
        self,
        text: str,
        *,
        top_k: int,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        tokens = tokenize(text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked: list[tuple[str, float]] = []
        for idx, score in enumerate(scores):
            cid = self.ids[idx]
            if allowed_ids is not None and cid not in allowed_ids:
                continue
            if score <= 0:
                continue
            ranked.append((cid, float(score)))
        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return ranked[:top_k]


def filter_chunk_ids(
    chunks_by_id: dict[str, Chunk],
    filters: RetrievalFilters | None,
) -> set[str] | None:
    """Return allowed ids, or None when no filters apply."""
    if filters is None:
        return None
    if not any(
        [
            filters.volume,
            filters.book,
            filters.source_type,
            filters.date_from,
            filters.date_to,
        ]
    ):
        return None
    allowed: set[str] = set()
    for cid, chunk in chunks_by_id.items():
        if filters.volume and (chunk.volume or "") != filters.volume:
            continue
        if filters.book and (chunk.book or "") != filters.book:
            continue
        if filters.source_type and chunk.source_type != filters.source_type:
            continue
        if filters.date_from or filters.date_to:
            date = chunk.date or ""
            if not date:
                continue
            if filters.date_from and date < filters.date_from:
                continue
            if filters.date_to and date > filters.date_to:
                continue
        allowed.add(cid)
    return allowed


def apply_filters(
    hits: Iterable[tuple[str, float]],
    allowed_ids: set[str] | None,
) -> list[tuple[str, float]]:
    if allowed_ids is None:
        return list(hits)
    return [(cid, score) for cid, score in hits if cid in allowed_ids]
