"""Typer CLI entrypoint. Full commands land in later PRs; PR1 wires pull-models."""

from __future__ import annotations

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
def prepare() -> None:
    """Ingest sources into chunks (PR2)."""
    _not_yet("PR2", "prepare")


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
