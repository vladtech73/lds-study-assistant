"""Build Chroma + BM25 indexes from chunks.jsonl (`lds index`)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn

from lds_study.config import Settings, get_settings
from lds_study.data.models import Chunk
from lds_study.index.chroma_store import ChromaDenseStore
from lds_study.index.base import Embedder
from lds_study.index.bm25_index import BM25Index
from lds_study.index.chunks_io import chunks_by_id, load_chunks_jsonl
from lds_study.index.embedder import build_embedder
from lds_study.index.hybrid import HybridRetriever
from lds_study.index.rerank import IdentityReranker
from lds_study.index.vram import (
    log_peak_vram,
    reset_peak_vram,
    unload_ollama_generator,
)

console = Console()

BM25_NAME = "bm25.pkl"
MANIFEST_NAME = "index_manifest.json"


@dataclass(slots=True)
class IndexBuildResult:
    profile: str
    profile_dir: Path
    chunk_count: int
    embedded_count: int
    resumed_skipped: int
    peak_vram_gb: float | None
    smoke_passed: int | None = None
    smoke_total: int | None = None


def profile_dir(settings: Settings, profile: str) -> Path:
    return settings.resolve(settings.index_dir) / profile


def run_index(
    *,
    profile: str = "default",
    rebuild: bool = False,
    smoke: bool = False,
    verbose: bool = False,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    chunks_path: Path | None = None,
    batch_size: int | None = None,
) -> IndexBuildResult:
    settings = settings or get_settings()
    models_cfg = settings.load_yaml("models.yaml")
    rag_cfg = settings.load_yaml("rag.yaml")

    root = settings.effective_root
    chunks_file = chunks_path or (settings.resolve(settings.data_dir) / "processed" / "chunks.jsonl")
    chunks = load_chunks_jsonl(chunks_file)
    if not chunks:
        raise ValueError(f"No chunks found in {chunks_file}")

    out_dir = profile_dir(settings, profile)
    chroma_dir = out_dir / "chroma"
    if rebuild and out_dir.exists():
        console.print(f"[yellow]Rebuilding[/yellow] profile {profile} — removing {out_dir}")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # VRAM discipline: unload generator before embedding.
    gen = models_cfg.get("generator") or {}
    unload_ollama_generator(
        settings.ollama_host,
        str(gen.get("id")) if gen.get("id") else None,
    )

    reset_peak_vram()
    own_embedder = embedder is None
    if embedder is None:
        embedder = build_embedder(models_cfg, settings=settings)
    emb_batch = batch_size or int((models_cfg.get("embeddings") or {}).get("batch_size") or 32)

    store = ChromaDenseStore(chroma_dir)
    existing = store.existing_ids() if not rebuild else set()
    pending = [c for c in chunks if c.id not in existing]
    skipped = len(chunks) - len(pending)

    if pending:
        console.print(
            f"Embedding [bold]{len(pending)}[/bold] chunks "
            f"(skipping {skipped} already indexed)…"
        )
        _embed_batches(
            store,
            pending,
            embedder,
            batch_size=emb_batch,
            verbose=verbose,
        )
    else:
        console.print(f"[green]Dense store up to date[/green] ({len(existing)} vectors)")

    console.print("Building BM25…")
    bm25 = BM25Index.build(chunks)
    bm25.save(out_dir / BM25_NAME)

    peak = log_peak_vram(verbose, label="index peak VRAM")

    manifest = {
        "profile": profile,
        "chunk_count": len(chunks),
        "dense_count": store.count(),
        "chunks_path": str(chunks_file),
        "embedder": (models_cfg.get("embeddings") or {}).get("id"),
        "rag": {
            "dense_top_k": (rag_cfg.get("retrieval") or {}).get("dense_top_k"),
            "bm25_top_k": (rag_cfg.get("retrieval") or {}).get("bm25_top_k"),
            "final_top_k": (rag_cfg.get("retrieval") or {}).get("final_top_k"),
        },
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    smoke_passed = smoke_total = None
    if smoke:
        from lds_study.index.smoke import run_phrase_smoke

        # Identity reranker during index smoke — never load embedder + reranker together.
        retriever = HybridRetriever(
            dense=store,
            bm25=bm25,
            embedder=embedder,
            chunks_by_id=chunks_by_id(chunks),
            reranker=IdentityReranker(),
            dense_top_k=int((rag_cfg.get("retrieval") or {}).get("dense_top_k", 50)),
            bm25_top_k=int((rag_cfg.get("retrieval") or {}).get("bm25_top_k", 50)),
            rrf_k=int((rag_cfg.get("retrieval") or {}).get("rrf_k", 60)),
            final_top_k=1,
            neighbor_window=0,
            min_score=0.0,
            verbose=False,
        )
        smoke_passed, smoke_total = run_phrase_smoke(retriever, root=root, verbose=verbose)
        console.print(
            f"Phrase smoke: [bold]{smoke_passed}/{smoke_total}[/bold] at rank 1"
        )
        if smoke_passed < smoke_total:
            if own_embedder:
                embedder.unload()
            raise RuntimeError(
                f"Phrase smoke failed: {smoke_passed}/{smoke_total} (need 10/10)"
            )

    if own_embedder:
        embedder.unload()

    return IndexBuildResult(
        profile=profile,
        profile_dir=out_dir,
        chunk_count=len(chunks),
        embedded_count=len(pending),
        resumed_skipped=skipped,
        peak_vram_gb=peak,
        smoke_passed=smoke_passed,
        smoke_total=smoke_total,
    )


def load_retriever(
    *,
    profile: str = "default",
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    identity_rerank: bool = False,
    verbose: bool = False,
) -> HybridRetriever:
    """Load a HybridRetriever for an existing profile."""
    settings = settings or get_settings()
    models_cfg = settings.load_yaml("models.yaml")
    rag_cfg = settings.load_yaml("rag.yaml")
    retrieval = rag_cfg.get("retrieval") or {}
    chunking = rag_cfg.get("chunking") or {}

    out_dir = profile_dir(settings, profile)
    if not out_dir.is_dir():
        raise FileNotFoundError(
            f"Index profile not found: {out_dir}. Run `lds index --profile {profile}` first."
        )

    chunks_file = settings.resolve(settings.data_dir) / "processed" / "chunks.jsonl"
    # Prefer path recorded in manifest when present.
    manifest_path = out_dir / MANIFEST_NAME
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded = manifest.get("chunks_path")
        if recorded and Path(recorded).is_file():
            chunks_file = Path(recorded)

    chunks = load_chunks_jsonl(chunks_file)
    store = ChromaDenseStore(out_dir / "chroma")
    bm25 = BM25Index.load(out_dir / BM25_NAME)
    if embedder is None:
        embedder = build_embedder(models_cfg, settings=settings)

    from lds_study.index.rerank import build_reranker

    reranker = build_reranker(
        models_cfg, rag_cfg, identity=identity_rerank, settings=settings
    )

    return HybridRetriever(
        dense=store,
        bm25=bm25,
        embedder=embedder,
        chunks_by_id=chunks_by_id(chunks),
        reranker=reranker,
        dense_top_k=int(retrieval.get("dense_top_k", 50)),
        bm25_top_k=int(retrieval.get("bm25_top_k", 50)),
        rrf_k=int(retrieval.get("rrf_k", 60)),
        final_top_k=int(retrieval.get("final_top_k", 8)),
        neighbor_window=int(chunking.get("neighbor_window", 2)),
        min_score=float(retrieval.get("min_score", 0.0)),
        verbose=verbose,
    )


def _embed_batches(
    store: ChromaDenseStore,
    chunks: list[Chunk],
    embedder: Embedder,
    *,
    batch_size: int,
    verbose: bool,
) -> None:
    """Embed and upsert; resume is driven by Chroma existing_ids upstream."""
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("embed", total=len(chunks))
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embedder.embed([c.text for c in batch])
            store.upsert(batch, vectors)
            progress.advance(task, len(batch))
            if verbose:
                log_peak_vram(True, label="batch peak VRAM")
