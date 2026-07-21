"""Cross-encoder reranker (CPU by default during ask)."""

from __future__ import annotations

from typing import Sequence

from rich.console import Console

from lds_study.index.base import Reranker

console = Console()


class IdentityReranker:
    """Pass-through scores (tests / when reranker weights unavailable)."""

    def rerank(self, query: str, passages: Sequence[str]) -> list[float]:
        _ = query
        # Preserve input order with gently decreasing scores.
        n = len(passages)
        return [float(n - i) for i in range(n)]

    def unload(self) -> None:
        return None


class CrossEncoderReranker:
    def __init__(self, model_id: str, *, device: str = "cpu") -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_id, device=device)
        self._model_id = model_id
        console.print(f"[dim]Loaded reranker {model_id} on {device}[/dim]")

    def rerank(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, p) for p in passages]
        scores = self._model.predict(pairs)
        return [float(s) for s in scores]

    def unload(self) -> None:
        self._model = None  # type: ignore[assignment]
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


def build_reranker(
    models_cfg: dict,
    rag_cfg: dict,
    *,
    identity: bool = False,
    settings=None,
) -> Reranker:
    if identity:
        return IdentityReranker()
    from lds_study.index.model_paths import resolve_model_path

    section = models_cfg.get("reranker") or {}
    model_id = str(section.get("id") or "BAAI/bge-reranker-v2-m3")
    load_path, is_local = resolve_model_path(model_id, settings=settings)
    if is_local:
        console.print(f"[dim]Using local reranker weights:[/dim] {load_path}")
    else:
        console.print(
            f"[yellow]Local snapshot missing for {model_id};[/yellow] "
            "loading from Hugging Face hub (run `lds pull-models` to cache under models/)."
        )
    device = str(
        (rag_cfg.get("retrieval") or {}).get("reranker_device")
        or section.get("device")
        or "cpu"
    )
    return CrossEncoderReranker(load_path, device=device)
