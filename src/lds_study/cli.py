"""Typer CLI entrypoint. PR1: pull-models; PR2: prepare; PR3: index + ask."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from lds_study import __version__

app = typer.Typer(
    name="lds",
    help="Private local LDS study assistant (unofficial). RAG-first CLI.",
    no_args_is_help=True,
)
console = Console()


def _not_yet(pr: str, name: str) -> None:
    console.print(
        f"[yellow]{name}[/yellow] is not implemented yet "
        f"(planned for [bold]{pr}[/bold]). See docs/ARCHITECTURE.md."
    )
    raise typer.Exit(code=1)


@app.callback()
def main() -> None:
    """LDS Study Assistant — unofficial personal study tool."""


@app.command("version")
def version() -> None:
    """Print package version."""
    console.print(__version__)


@app.command("pull-models")
def pull_models(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions only"),
    skip_ollama: bool = typer.Option(False, "--skip-ollama"),
    skip_hf: bool = typer.Option(False, "--skip-hf"),
    include_finetune_weights: bool = typer.Option(
        False,
        "--include-finetune-weights",
        help="Also download generator.hf_id for QLoRA (~28GB; not needed for RAG).",
    ),
) -> None:
    """Download models listed in configs/models.yaml."""
    from lds_study.pull_models import run_pull

    code = run_pull(
        dry_run=dry_run,
        skip_ollama=skip_ollama,
        skip_hf=skip_hf,
        include_finetune_weights=include_finetune_weights,
    )
    raise typer.Exit(code)


@app.command("prepare")
def prepare(
    stats: bool = typer.Option(False, "--stats", help="Print per-source chunk stats"),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Accept a new download sha256 deliberately (otherwise hash drift fails).",
    ),
    scripture_only: bool = typer.Option(
        False,
        "--scripture-only",
        help="Only run public_scripture loaders (skip BYOF user files).",
    ),
    source: Optional[list[str]] = typer.Option(
        None,
        "--source",
        help="Limit to one or more source ids from configs/sources.yaml (repeatable).",
    ),
) -> None:
    """Ingest sources into data/processed/chunks.jsonl."""
    from lds_study.data.manifest import ManifestError, UnverifiedSourceError
    from lds_study.data.prepare import run_prepare

    try:
        result = run_prepare(
            source_ids=source,
            scripture_only=scripture_only,
            refresh=refresh,
            show_stats=stats,
        )
    except (UnverifiedSourceError, ManifestError) as exc:
        console.print("prepare failed:", str(exc), style="red")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Wrote[/green] {len(result.chunks)} chunks → {result.chunks_path}"
    )
    if result.empty_total:
        console.print(
            f"[yellow]Dropped {result.empty_total} empty record(s)[/yellow] "
            f"(see {result.stats_path})"
        )
    else:
        console.print(f"Stats → {result.stats_path} (zero empty chunks)")


@app.command("index")
def index_cmd(
    profile: str = typer.Option("default", "--profile", help="Index profile name"),
    rebuild: bool = typer.Option(False, "--rebuild", help="Delete profile and rebuild"),
    smoke: bool = typer.Option(
        False,
        "--smoke",
        help="Run 10/10 phrase-lookup smoke after build (needs matching embedder).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Log peak VRAM (device + process) at end of build / per batch",
    ),
) -> None:
    """Build Chroma + BM25 indexes from data/processed/chunks.jsonl."""
    from lds_study.index.build import run_index

    try:
        result = run_index(
            profile=profile,
            rebuild=rebuild,
            smoke=smoke,
            verbose=verbose,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        console.print("index failed:", str(exc), style="red")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Indexed[/green] {result.chunk_count} chunks → {result.profile_dir} "
        f"(embedded {result.embedded_count}, resumed skip {result.resumed_skipped})"
    )
    if result.peak_vram_gb is not None:
        console.print(f"Peak VRAM: {result.peak_vram_gb:.2f} GiB")


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="Study question"),
    mode: str = typer.Option("study", "--mode", help="study | lesson | talk"),
    profile: str = typer.Option("default", "--profile"),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Skip citation regenerate; refuse immediately on invalid markers.",
    ),
    show_context: bool = typer.Option(
        False, "--show-context", help="Print retrieved chunks before answering"
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit AskResult JSON"),
    volume: Optional[str] = typer.Option(None, "--volume", help="Filter volume slug"),
    book: Optional[str] = typer.Option(None, "--book", help="Filter book slug"),
    source_type: Optional[str] = typer.Option(
        None, "--source-type", help="Filter source_type (e.g. scripture)"
    ),
    date_from: Optional[str] = typer.Option(None, "--date-from"),
    date_to: Optional[str] = typer.Option(None, "--date-to"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Answer a study question with citations (or refuse with exit 2/3)."""
    from lds_study.index.base import RetrievalFilters
    from lds_study.rag.ask import run_ask

    filters = RetrievalFilters(
        volume=volume,
        book=book,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
    )
    try:
        result = run_ask(
            question,
            mode=mode,
            profile=profile,
            strict=strict,
            show_context=show_context,
            as_json=as_json,
            filters=filters,
            verbose=verbose,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        console.print("ask failed:", str(exc), style="red")
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=result.exit_code)


@app.command("eval")
def eval_cmd() -> None:
    """Run golden-question eval (PR4)."""
    _not_yet("PR4", "eval")


if __name__ == "__main__":
    app()
