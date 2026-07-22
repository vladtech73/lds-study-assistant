"""Typer CLI entrypoint. PR1–PR5: pull-models | prepare | index | ask | eval | finetune-*."""

from __future__ import annotations

from pathlib import Path
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
def eval_cmd(
    profile: str = typer.Option("default", "--profile", help="Index profile name"),
    models: Optional[str] = typer.Option(
        None,
        "--models",
        help="Comma-separated Ollama model ids (default: full shortlist in models.yaml)",
    ),
    k: Optional[int] = typer.Option(
        None,
        "--k",
        help="Recall@k cutoff (default: rag.eval.recall_k); must be <= retrieval.final_top_k",
    ),
    buckets: Optional[str] = typer.Option(
        None,
        "--buckets",
        help="Comma-separated buckets: verse_lookup,doctrinal_synthesis,"
        "lesson_planning,adversarial",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", help="Evaluate only the first N questions (after filters)"
    ),
    retrieval_only: bool = typer.Option(
        False,
        "--retrieval-only",
        help="Skip generation; compute recall@k only (fast, offline-friendly)",
    ),
    include_local: bool = typer.Option(
        True,
        "--include-local/--no-local",
        help="Also load gitignored eval/golden.local.yaml when present",
    ),
    stem: Optional[str] = typer.Option(
        None,
        "--stem",
        help="Report filename stem under outputs/eval/ (default: today's date)",
    ),
    check_baselines: bool = typer.Option(
        False,
        "--check-baselines",
        help=(
            "PR5 keep-or-revert: compare each model to configs/rag.yaml "
            "eval.baselines; exit 1 if any REVERT."
        ),
    ),
) -> None:
    """Run golden-question eval; write outputs/eval/{date}.md (+ JSON sidecar)."""
    from lds_study.eval.run import run_eval

    model_list = (
        [m.strip() for m in models.split(",") if m.strip()] if models else None
    )
    bucket_list = (
        [b.strip() for b in buckets.split(",") if b.strip()] if buckets else None
    )
    try:
        result = run_eval(
            profile=profile,
            models=model_list,
            k=k,
            buckets=bucket_list,
            limit=limit,
            include_local=include_local,
            retrieval_only=retrieval_only,
            stem=stem,
            check_baselines=check_baselines,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        console.print("eval failed:", str(exc), style="red")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Wrote[/green] {result.md_path}")
    console.print(f"JSON sidecar -> {result.json_path}")
    for agg in result.aggregates:
        console.print(
            f"  {agg.model}: recall={agg.recall_at_k} "
            f"cite={agg.citation_validity_rate} "
            f"refuse={agg.adversarial_refusal_rate}"
        )
    if result.suggested_baselines:
        console.print("Suggested baselines:", result.suggested_baselines)
    if result.baseline_verdicts:
        console.print("Keep-or-revert vs eval.baselines:")
        any_revert = False
        for model, (ok, failures) in result.baseline_verdicts.items():
            if ok:
                console.print(f"  {model}: [green]KEEP[/green]")
            else:
                any_revert = True
                console.print(f"  {model}: [red]REVERT[/red] — {'; '.join(failures)}")
        if any_revert:
            raise typer.Exit(code=1)


@app.command("finetune-dataset")
def finetune_dataset(
    chunks: Optional[Path] = typer.Option(
        None, "--chunks", help="Input chunks.jsonl (default: data/processed/chunks.jsonl)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Output SFT JSONL (default: data/processed/sft.jsonl)"
    ),
    max_pairs: Optional[int] = typer.Option(
        None, "--max-pairs", help="Cap pairs for a debug train slice"
    ),
) -> None:
    """Build ShareGPT SFT pairs from redistributable sources only (PR5)."""
    from lds_study.finetune.build_dataset import build_sft_dataset

    try:
        result = build_sft_dataset(
            chunks_path=chunks,
            output_path=output,
            max_pairs=max_pairs,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        console.print("finetune-dataset failed:", str(exc), style="red")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[green]Wrote[/green] {result.pairs_written} pairs → {result.output_path} "
        f"(restricted_dropped={result.restricted_dropped})"
    )


@app.command("finetune-train")
def finetune_train(
    data: Optional[Path] = typer.Option(None, "--data", help="SFT JSONL path"),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Adapter output dir (default: adapters/lds-qlora)"
    ),
    base_model: Optional[str] = typer.Option(
        None, "--base-model", help="HF id override (default: generator.hf_id)"
    ),
    max_steps: Optional[int] = typer.Option(
        None, "--max-steps", help="Debug slice (e.g. 20)"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate dataset only (no Unsloth / GPU).",
    ),
) -> None:
    """QLoRA train via Unsloth (requires ``pip install -e '.[finetune]'``)."""
    from lds_study.finetune.train_qlora import main as train_main

    argv: list[str] = []
    if data is not None:
        argv.extend(["--data", str(data)])
    if output is not None:
        argv.extend(["--output", str(output)])
    if base_model:
        argv.extend(["--base-model", base_model])
    if max_steps is not None:
        argv.extend(["--max-steps", str(max_steps)])
    if dry_run:
        argv.append("--dry-run")
    code = train_main(argv)
    raise typer.Exit(code)


@app.command("finetune-export")
def finetune_export(
    adapter: Optional[Path] = typer.Option(
        None, "--adapter", help="Adapter dir (default: adapters/lds-qlora)"
    ),
    ollama_tag: str = typer.Option(
        "lds-study-adapter", "--ollama-tag", help="Ollama model name after create"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Write Modelfile + ollama_tag only"
    ),
    skip_ollama: bool = typer.Option(False, "--skip-ollama"),
) -> None:
    """Merge adapter, export GGUF, register with Ollama for hybrid ask."""
    from lds_study.finetune.merge_and_export import main as export_main

    argv: list[str] = ["--ollama-tag", ollama_tag]
    if adapter is not None:
        argv.extend(["--adapter", str(adapter)])
    if dry_run:
        argv.append("--dry-run")
    if skip_ollama:
        argv.append("--skip-ollama")
    code = export_main(argv)
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
