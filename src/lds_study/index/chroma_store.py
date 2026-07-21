"""Chroma dense store (chromadb PersistentClient; no LlamaIndex VectorStore)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import chromadb
from chromadb.config import Settings as ChromaSettings
from rich.console import Console

from lds_study.data.models import Chunk
from lds_study.index.base import RetrievalFilters

console = Console()

# Collection name is stable per profile directory.
COLLECTION = "lds_chunks"


def _meta_for(chunk: Chunk) -> dict[str, Any]:
    """Chroma metadata: only str/int/float/bool."""
    meta: dict[str, Any] = {
        "source_id": chunk.source_id,
        "source_type": chunk.source_type,
        "redistributable": bool(chunk.redistributable),
    }
    if chunk.volume:
        meta["volume"] = chunk.volume
    if chunk.book:
        meta["book"] = chunk.book
    if chunk.chapter is not None:
        meta["chapter"] = int(chunk.chapter)
    if chunk.verse is not None:
        meta["verse"] = int(chunk.verse)
    if chunk.canonical_ref:
        meta["canonical_ref"] = chunk.canonical_ref
    if chunk.title:
        meta["title"] = chunk.title
    if chunk.author:
        meta["author"] = chunk.author
    if chunk.date:
        meta["date"] = chunk.date
    return meta


def _where_from_filters(filters: RetrievalFilters | None) -> dict[str, Any] | None:
    if filters is None:
        return None
    clauses: list[dict[str, Any]] = []
    if filters.volume:
        clauses.append({"volume": filters.volume})
    if filters.book:
        clauses.append({"book": filters.book})
    if filters.source_type:
        clauses.append({"source_type": filters.source_type})
    # date_range is applied post-query in hybrid (chroma where on strings is brittle)
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class ChromaDenseStore:
    """Persistent Chroma collection under indexes/{profile}/chroma/."""

    def __init__(self, persist_dir: Path) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def existing_ids(self) -> set[str]:
        # Chroma get() without ids returns all; for large corpora use pagination.
        result = self._collection.get(include=[])
        return set(result.get("ids") or [])

    def upsert(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=[list(map(float, e)) for e in embeddings],
            documents=[c.text for c in chunks],
            metadatas=[_meta_for(c) for c in chunks],
        )

    def query(
        self,
        embedding: Sequence[float],
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        where = _where_from_filters(filters)
        kwargs: dict[str, Any] = {
            "query_embeddings": [list(map(float, embedding))],
            "n_results": top_k,
            "include": ["distances"],
        }
        if where is not None:
            kwargs["where"] = where
        try:
            result = self._collection.query(**kwargs)
        except (ValueError, chromadb.errors.InvalidArgumentError) as exc:
            # Empty collection or filter that matches nothing — expected soft miss.
            console.print(f"[dim]Dense query soft-miss:[/dim] {exc}")
            return []
        except Exception as exc:
            # Schema / dimension / corrupt store — do not silently fall back to BM25-only.
            console.print(
                f"[yellow]Dense query failed ({type(exc).__name__}):[/yellow] {exc}. "
                "Returning no dense hits; BM25 may still answer."
            )
            return []
        ids = (result.get("ids") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        # Cosine distance: convert to similarity-ish score (higher better) for RRF peers
        out: list[tuple[str, float]] = []
        for cid, dist in zip(ids, dists, strict=False):
            score = 1.0 / (1.0 + float(dist))
            out.append((cid, score))
        return out

    def count(self) -> int:
        return int(self._collection.count())
