"""Embedding backends — real BGE-M3 via LlamaIndex HF wrapper, plus test hash embedder."""

from __future__ import annotations

import hashlib
import math
from typing import Sequence

from rich.console import Console

from lds_study.index.base import Embedder

console = Console()


class HashEmbedder:
    """Deterministic bag-of-hash embedder for offline unit tests (no GPU/weights)."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def unload(self) -> None:
        return None


class HuggingFaceEmbedder:
    """BGE-M3 (or configured HF id) via llama_index HuggingFaceEmbedding."""

    def __init__(
        self,
        model_name: str,
        *,
        device: str = "cuda",
        batch_size: int = 32,
        local_files_only: bool = False,
    ) -> None:
        # Import inside constructor so offline citation tests never pull torch stacks.
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        self._batch_size = batch_size
        self._model_name = model_name
        kwargs: dict = {
            "model_name": model_name,
            "embed_batch_size": batch_size,
            "device": device,
        }
        if local_files_only:
            kwargs["model_kwargs"] = {"local_files_only": True}
        try:
            self._emb = HuggingFaceEmbedding(**kwargs)
        except TypeError:
            self._emb = HuggingFaceEmbedding(model_name=model_name, device=device)
        console.print(
            f"[dim]Loaded embedder {model_name} on {device} (batch={batch_size})[/dim]"
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        # encode uses the configured embed_batch_size internally when available
        out: list[list[float]] = []
        bs = self._batch_size
        for start in range(0, len(texts), bs):
            batch = list(texts[start : start + bs])
            vectors = self._emb.get_text_embedding_batch(batch)
            out.extend([list(map(float, v)) for v in vectors])
        return out

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, self._emb.get_query_embedding(text)))

    def unload(self) -> None:
        self._emb = None  # type: ignore[assignment]
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


def build_embedder(
    models_cfg: dict,
    *,
    force_hash: bool = False,
    settings=None,
) -> Embedder:
    """Construct embedder from configs/models.yaml embeddings section."""
    if force_hash:
        return HashEmbedder()
    from lds_study.index.model_paths import resolve_model_path

    section = models_cfg.get("embeddings") or {}
    model_id = str(section.get("id") or "BAAI/bge-m3")
    load_path, is_local = resolve_model_path(model_id, settings=settings)
    if is_local:
        console.print(f"[dim]Using local embedder weights:[/dim] {load_path}")
    else:
        console.print(
            f"[yellow]Local snapshot missing for {model_id};[/yellow] "
            "loading from Hugging Face hub (run `lds pull-models` to cache under models/)."
        )
    device = str(section.get("device") or "cuda")
    batch_size = int(section.get("batch_size") or 32)
    try:
        import torch

        if device.startswith("cuda") and not torch.cuda.is_available():
            console.print("[yellow]CUDA unavailable — falling back to CPU embeddings[/yellow]")
            device = "cpu"
    except ImportError:
        device = "cpu"
    return HuggingFaceEmbedder(
        load_path,
        device=device,
        batch_size=batch_size,
        local_files_only=is_local,
    )
