"""Retriever protocols and shared retrieval types (PR3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from lds_study.data.models import Chunk


@dataclass(slots=True)
class RetrievalFilters:
    """Query-time filters exposed by HybridRetriever."""

    volume: str | None = None
    book: str | None = None
    source_type: str | None = None
    date_from: str | None = None  # inclusive ISO-ish YYYY-MM-DD when present
    date_to: str | None = None


@dataclass(slots=True)
class RetrievedHit:
    chunk: Chunk
    score: float
    source: str = "hybrid"  # dense | bm25 | hybrid | expand
    # For expand hits: id of the seed hit that pulled this neighbor (None for seeds).
    seed_id: str | None = None


@dataclass(slots=True)
class RetrievalResult:
    hits: list[RetrievedHit] = field(default_factory=list)
    peak_vram_gb: float | None = None


class DenseStore(Protocol):
    """Persistent dense vector store over chunk ids."""

    def existing_ids(self) -> set[str]:
        """Return ids already present (for resumable embedding)."""

    def upsert(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        """Insert or replace vectors for the given chunks."""

    def query(
        self,
        embedding: Sequence[float],
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[tuple[str, float]]:
        """Return (chunk_id, distance_or_score) pairs — lower distance preferred for L2."""

    def count(self) -> int:
        """Number of vectors stored."""


class Embedder(Protocol):
    """Batch text embedder."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts; returns one vector per input."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""

    def unload(self) -> None:
        """Release GPU/CPU weights when possible."""


class Reranker(Protocol):
    """Cross-encoder reranker over (query, passage) pairs."""

    def rerank(self, query: str, passages: Sequence[str]) -> list[float]:
        """Higher score = more relevant."""

    def unload(self) -> None:
        """Release weights when possible."""


class Retriever(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Hybrid retrieve + optional expand."""
