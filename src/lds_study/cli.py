"""Typer CLI entrypoint. PR1: pull-models; PR2: prepare; later PRs fill the rest."""

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
        console.print(f"[red]prepare failed:[/red] {exc}")
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
def index_cmd() -> None:
    """Build Chroma + BM25 indexes (PR3)."""
    _not_yet("PR3", "index")


@app.command("ask")
def ask() -> None:
    """Answer a study question with citations (PR3)."""
    _not_yet("PR3", "ask")


@app.command("eval")
def eval_cmd() -> None:
    """Run golden-question eval (PR4)."""
    _not_yet("PR4", "eval")


if __name__ == "__main__":
    app()
