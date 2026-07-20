"""Download models from configs/models.yaml (Ollama + Hugging Face)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from rich.console import Console

from lds_study.config import get_settings

console = Console()


def _run(cmd: list[str], dry_run: bool) -> int:
    console.print(f"[cyan]$[/cyan] {' '.join(cmd)}")
    if dry_run:
        return 0
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


def pull_ollama(model_id: str, dry_run: bool) -> int:
    ollama = shutil.which("ollama")
    if ollama is None:
        console.print(
            "[yellow]ollama[/yellow] not found on PATH. Install from "
            "https://ollama.com and re-run, or use --skip-ollama."
        )
        return 1
    return _run([ollama, "pull", model_id], dry_run=dry_run)


def pull_hf(repo_id: str, local_dir: str, dry_run: bool) -> int:
    if dry_run:
        console.print(f"[cyan]huggingface_hub.snapshot_download[/cyan] {repo_id} -> {local_dir}")
        return 0
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        console.print("[red]huggingface_hub missing[/red]; pip install -e .")
        return 1
    console.print(f"Downloading [bold]{repo_id}[/bold] -> {local_dir}")
    snapshot_download(repo_id=repo_id, local_dir=local_dir)
    return 0


def run_pull(
    *,
    dry_run: bool = False,
    skip_ollama: bool = False,
    skip_hf: bool = False,
    include_finetune_weights: bool = False,
) -> int:
    settings = get_settings()
    cfg: dict[str, Any] = settings.load_yaml("models.yaml")
    models_dir = settings.resolve(settings.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    status = 0
    gen = cfg.get("generator") or {}
    emb = cfg.get("embeddings") or {}
    rerank = cfg.get("reranker") or {}

    if not skip_ollama and gen.get("backend") == "ollama":
        gen_id = gen.get("id")
        if not gen_id:
            console.print("[red]generator.id missing in configs/models.yaml[/red]")
            status = 1
        else:
            code = pull_ollama(str(gen_id), dry_run=dry_run)
            status = status or code

    if not skip_hf:
        for _key, section in ("embeddings", emb), ("reranker", rerank):
            hf_id = section.get("id")
            if not hf_id:
                continue
            safe = str(hf_id).replace("/", "--")
            dest = str(models_dir / safe)
            code = pull_hf(str(hf_id), dest, dry_run=dry_run)
            status = status or code

        # Full HF generator weights are only for Unsloth/QLoRA (PR5) — not default RAG.
        if include_finetune_weights:
            hf_gen = gen.get("hf_id")
            if hf_gen:
                safe = str(hf_gen).replace("/", "--")
                dest = str(models_dir / safe)
                code = pull_hf(str(hf_gen), dest, dry_run=dry_run)
                status = status or code
        elif gen.get("hf_id"):
            console.print(
                "[dim]Skipping generator.hf_id (~28GB). "
                "Pass --include-finetune-weights for QLoRA (see docs/FINETUNE_WINDOWS.md).[/dim]"
            )

    if status == 0:
        console.print("[green]pull-models completed[/green]" + (" (dry-run)" if dry_run else ""))
    return status


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pull models from configs/models.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--skip-hf", action="store_true")
    parser.add_argument(
        "--include-finetune-weights",
        action="store_true",
        help="Also download generator.hf_id for Unsloth/QLoRA (large; not needed for RAG).",
    )
    args = parser.parse_args(argv)
    return run_pull(
        dry_run=args.dry_run,
        skip_ollama=args.skip_ollama,
        skip_hf=args.skip_hf,
        include_finetune_weights=args.include_finetune_weights,
    )


if __name__ == "__main__":
    sys.exit(main())
