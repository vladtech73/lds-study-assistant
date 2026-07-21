"""Hybrid dense ∪ BM25 → RRF → rerank → expand."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from lds_study.data.models import Chunk
from lds_study.index.base import (
    DenseStore,
    Embedder,
    Reranker,
    RetrievalFilters,
    RetrievalResult,
    RetrievedHit,
)
from lds_study.index.bm25_index import BM25Index, apply_filters, filter_chunk_ids
from lds_study.index.expand import expand_context
from lds_study.index.vram import log_peak_vram, peak_vram_gb, reset_peak_vram


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[tuple[str, float]]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """RRF over ranked id lists. Input scores are ignored; first rank per id per list wins."""
    scores: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        seen: set[str] = set()
        for rank, (cid, _score) in enumerate(ranked, start=1):
            if cid in seen:
                continue
            seen.add(cid)
            scores[cid] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


class HybridRetriever:
    def __init__(
        self,
        *,
        dense: DenseStore,
        bm25: BM25Index,
        embedder: Embedder,
        chunks_by_id: dict[str, Chunk],
        reranker: Reranker | None = None,
        dense_top_k: int = 50,
        bm25_top_k: int = 50,
        rrf_k: int = 60,
        final_top_k: int = 8,
        neighbor_window: int = 2,
        min_score: float = 0.0,
        verbose: bool = False,
    ) -> None:
        self.dense = dense
        self.bm25 = bm25
        self.embedder = embedder
        self.chunks_by_id = chunks_by_id
        self.reranker = reranker
        self.dense_top_k = dense_top_k
        self.bm25_top_k = bm25_top_k
        self.rrf_k = rrf_k
        self.final_top_k = final_top_k
        self.neighbor_window = neighbor_window
        self.min_score = min_score
        self.verbose = verbose

    def retrieve(
        self,
        query: str,
        *,
        filters: RetrievalFilters | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        reset_peak_vram()
        final_k = top_k if top_k is not None else self.final_top_k
        allowed = filter_chunk_ids(self.chunks_by_id, filters)

        query_vec = self.embedder.embed_query(query)
        dense_hits = self.dense.query(
            query_vec, top_k=self.dense_top_k, filters=filters
        )
        dense_hits = apply_filters(dense_hits, allowed)

        bm25_hits = self.bm25.query(query, top_k=self.bm25_top_k, allowed_ids=allowed)

        fused = reciprocal_rank_fusion([dense_hits, bm25_hits], k=self.rrf_k)
        # Take a pool larger than final_k for reranking.
        pool_n = max(final_k * 4, final_k)
        pool = fused[:pool_n]

        candidates: list[RetrievedHit] = []
        for cid, score in pool:
            chunk = self.chunks_by_id.get(cid)
            if chunk is None:
                continue
            candidates.append(RetrievedHit(chunk=chunk, score=score, source="hybrid"))

        if self.reranker is not None and candidates:
            passages = [h.chunk.text for h in candidates]
            scores = self.reranker.rerank(query, passages)
            for hit, score in zip(candidates, scores, strict=False):
                hit.score = float(score)
            candidates.sort(key=lambda h: h.score, reverse=True)

        top = [h for h in candidates if h.score >= self.min_score][:final_k]
        top = expand_context(top, self.chunks_by_id, neighbor_window=self.neighbor_window)

        vram = log_peak_vram(self.verbose, label="retrieve peak VRAM")
        if vram is None:
            vram = peak_vram_gb()
        return RetrievalResult(hits=top, peak_vram_gb=vram)
