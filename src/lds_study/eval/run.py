"""`lds eval` orchestration — golden questions → metrics → report."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from lds_study.config import Settings, get_settings
from lds_study.eval.golden import (
    GoldenQuestion,
    default_golden_path,
    default_local_golden_path,
    load_golden_set,
)
from lds_study.eval.metrics import (
    AggregateMetrics,
    ItemMetrics,
    aggregate,
    coverage_stats,
    is_refusal_status,
    meets_regression_baselines,
    recall_at_k,
    score_distribution,
    suggest_min_score,
    suggested_baselines,
)
from lds_study.eval.compare import (
    ComparisonResult,
    diff_summaries,
    load_summary,
    normalize_compare_display,
    render_comparison_section,
    render_no_comparison_section,
    resolve_compare_reference,
)
from lds_study.eval.report import (
    default_report_stem,
    report_paths,
    write_json_sidecar,
    write_markdown_report,
    write_summary_json,
)
from lds_study.index.base import RetrievalResult, Retriever
from lds_study.index.build import load_retriever
from lds_study.rag.ask import run_ask
from lds_study.rag.generate import (
    Generator,
    OllamaGenerator,
    resolve_generator_think,
)

console = Console()


@dataclass(slots=True)
class EvalResult:
    profile: str
    models: list[str]
    k: int
    items: list[ItemMetrics]
    aggregates: list[AggregateMetrics]
    md_path: Path
    json_path: Path
    suggested_baselines: dict[str, float] = field(default_factory=dict)
    include_local: bool = False
    golden_hash: str | None = None
    golden_local_hash: str | None = None
    source_counts: dict[str, int] = field(default_factory=dict)
    recall_shared: float | None = None
    # PR5 keep-or-revert: model -> (keep: bool, failures: list[str])
    baseline_verdicts: dict[str, tuple[bool, list[str]]] = field(default_factory=dict)
    baselines_checked: dict[str, float] = field(default_factory=dict)
    summary_path: Path | None = None
    comparison: ComparisonResult | None = None
    compare_reason: str | None = None
    buckets: list[str] | None = None
    limit: int | None = None


def _build_generator_for_model(
    model_id: str,
    models_cfg: dict,
    host: str,
) -> OllamaGenerator:
    """Clone models.yaml generator settings with an overridden Ollama model id.

    Eval compares named shortlist tags and does not honor ``generator.adapter``
    (adapter keep-or-revert is a separate single-model ask/eval with adapter set).
    """
    gen = models_cfg.get("generator") or {}
    return OllamaGenerator(
        host=host,
        model=model_id,
        num_ctx=int(gen.get("num_ctx") or 8192),
        keep_alive=str(gen.get("keep_alive") or "5m"),
        think=resolve_generator_think(gen),
    )


def _seed_hits(result: RetrievalResult) -> list:
    seeds = [h for h in result.hits if h.source != "expand"]
    return seeds if seeds else list(result.hits)


def preflight_ollama_models(host: str, models: Sequence[str]) -> None:
    """Fail fast if any requested Ollama model is not available locally."""
    url = f"{host.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Ollama preflight failed ({url}): {exc}") from exc
    names: set[str] = set()
    for row in body.get("models") or []:
        name = str(row.get("name") or "")
        if name:
            names.add(name)
    missing: list[str] = []
    for m in models:
        if m in names:
            continue
        if any(n == m or n.startswith(m + "-") for n in names):
            continue
        missing.append(m)
    if missing:
        available = ", ".join(sorted(n for n in names if ":" in n)[:20]) or "(none)"
        raise RuntimeError(
            f"Ollama model(s) not found: {missing}. Available (sample): {available}"
        )


def evaluate_question(
    q: GoldenQuestion,
    *,
    model: str,
    profile: str,
    k: int,
    retrieval_only: bool,
    retrieval: RetrievalResult,
    generator: Generator | None,
    settings: Settings,
) -> ItemMetrics:
    row = ItemMetrics(
        question_id=q.id,
        bucket=q.bucket,
        model=model,
        recall_hit=None,
        recall_rank=None,
        expect_refuse=q.expect_refuse,
        source=q.source,
    )
    try:
        seeds = _seed_hits(retrieval)
        row.retrieved_ids = [h.chunk.id for h in seeds]
        row.seed_scores = [float(h.score) for h in seeds]
        if row.seed_scores:
            row.top1_score = row.seed_scores[0]
            top = row.seed_scores[:k]
            row.topk_min_score = min(top) if top else None
        if q.gold_chunk_ids:
            hit, rank = recall_at_k(row.retrieved_ids, q.gold_chunk_ids, k=k)
            row.recall_hit = hit
            row.recall_rank = rank

        if retrieval_only:
            return row

        if generator is None:
            raise RuntimeError("generator required unless --retrieval-only")

        ask = run_ask(
            q.question,
            mode=q.mode,
            profile=profile,
            settings=settings,
            generator=generator,
            emit=False,
            retrieval=retrieval,
        )
        row.status = ask.status
        row.exit_code = ask.exit_code
        row.refused = is_refusal_status(ask.status)
        if q.expect_refuse:
            row.refusal_correct = bool(row.refused)

        invalid: list[str] = []
        if ask.citation is not None:
            invalid = [str(x) for x in (ask.citation.get("invalid") or [])]
            row.invalid_markers = invalid
            cov = ask.citation.get("coverage")
            row.citation_coverage = float(cov) if cov is not None else None

        # Citation metrics: non-adversarial items that attempted an answer only.
        if not q.expect_refuse and ask.status in {"ok", "unsupported"}:
            row.had_invalid_marker = len(invalid) > 0
            row.citation_valid = len(invalid) == 0
            # Coverage-only refuse: unsupported with no fabricated markers.
            row.coverage_gate_fail = ask.status == "unsupported" and len(invalid) == 0
    except Exception as exc:  # noqa: BLE001 — surface per-item; don't abort whole run
        row.error = str(exc)
    return row


def run_eval(
    *,
    profile: str = "default",
    models: Sequence[str] | None = None,
    k: int | None = None,
    buckets: Sequence[str] | None = None,
    limit: int | None = None,
    include_local: bool = True,
    retrieval_only: bool = False,
    stem: str | None = None,
    check_baselines: bool = False,
    compare: str = "auto",
    settings: Settings | None = None,
    retriever: Retriever | None = None,
    generators: dict[str, Generator] | None = None,
    skip_preflight: bool = False,
) -> EvalResult:
    settings = settings or get_settings()
    models_cfg = settings.load_yaml("models.yaml")
    rag_cfg = settings.load_yaml("rag.yaml")
    retrieval_cfg = rag_cfg.get("retrieval") or {}
    eval_cfg = rag_cfg.get("eval") or {}

    k = int(k if k is not None else eval_cfg.get("recall_k") or retrieval_cfg.get("final_top_k") or 8)
    final_top_k = int(retrieval_cfg.get("final_top_k") or 8)
    if k > final_top_k:
        raise ValueError(
            f"--k ({k}) cannot exceed retrieval.final_top_k ({final_top_k}): "
            "recall is measured by slicing the production retrieval pool, not by "
            "widening generation context. Raise final_top_k in configs/rag.yaml first."
        )

    if models:
        model_list = [m.strip() for m in models if m and m.strip()]
    else:
        shortlist = models_cfg.get("shortlist") or []
        if isinstance(shortlist, list) and shortlist:
            model_list = [str(m) for m in shortlist]
        else:
            gen_id = str((models_cfg.get("generator") or {}).get("id") or "")
            if not gen_id:
                raise ValueError("No models specified and generator.id missing")
            model_list = [gen_id]
    if not model_list:
        raise ValueError("At least one model id is required")

    out_dir_early = settings.resolve(settings.outputs_dir) / "eval"
    # Fail-fast on explicit --compare before retrieval / generation work.
    compare_mode = (compare or "auto").strip()
    early_ref: Path | None = None
    early_reason: str | None = None
    if compare_mode.lower() not in {"auto", "none"}:
        early_ref, early_reason = resolve_compare_reference(
            compare=compare,
            repo_root=settings.effective_root,
            eval_cfg=eval_cfg if isinstance(eval_cfg, dict) else {},
            exclude=None,
            outputs_eval_dir=out_dir_early,
        )

    questions = load_golden_set(
        settings.effective_root,
        include_local=include_local,
        buckets=buckets,
        limit=limit,
    )
    if not questions:
        raise ValueError("No golden questions after filters")

    source_counts: dict[str, int] = {}
    for q in questions:
        source_counts[q.source] = source_counts.get(q.source, 0) + 1

    golden_path = default_golden_path(settings.effective_root)
    golden_hash = hashlib.sha256(golden_path.read_bytes()).hexdigest()[:16]
    local_path = default_local_golden_path(settings.effective_root)
    golden_local_hash: str | None = None
    if include_local and local_path.is_file():
        golden_local_hash = hashlib.sha256(local_path.read_bytes()).hexdigest()[:16]

    if retriever is None:
        console.print(f"Loading retriever profile={profile}...")
        retriever = load_retriever(profile=profile, settings=settings)

    if not retrieval_only and not skip_preflight:
        need_check = [
            m for m in model_list if not generators or m not in generators
        ]
        if need_check:
            preflight_ollama_models(settings.ollama_host, need_check)

    # Retrieve once at production final_top_k; recall@k slices that pool.
    console.print(
        f"Retrieving {len(questions)} question(s) at final_top_k={final_top_k} "
        f"(recall@{k} sliced)..."
    )
    retrieval_by_qid: dict[str, RetrievalResult] = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("retrieve", total=len(questions))
        for q in questions:
            progress.update(task, description=f"retrieve - {q.id}")
            retrieval_by_qid[q.id] = retriever.retrieve(
                q.question, top_k=final_top_k
            )
            progress.advance(task)

    # Shared recall (same for every model).
    shared_recall_hits = 0
    shared_recall_n = 0
    for q in questions:
        if not q.gold_chunk_ids:
            continue
        seeds = _seed_hits(retrieval_by_qid[q.id])
        ids = [h.chunk.id for h in seeds]
        hit, _ = recall_at_k(ids, q.gold_chunk_ids, k=k)
        shared_recall_n += 1
        if hit:
            shared_recall_hits += 1
    recall_shared = (
        shared_recall_hits / shared_recall_n if shared_recall_n else None
    )

    items: list[ItemMetrics] = []
    total = len(questions) * len(model_list)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("eval", total=total)
        for model in model_list:
            if retrieval_only:
                gen: Generator | None = None
            elif generators and model in generators:
                gen = generators[model]
            else:
                gen = _build_generator_for_model(
                    model, models_cfg, settings.ollama_host
                )
            for q in questions:
                progress.update(task, description=f"{model} - {q.id}")
                row = evaluate_question(
                    q,
                    model=model,
                    profile=profile,
                    k=k,
                    retrieval_only=retrieval_only,
                    retrieval=retrieval_by_qid[q.id],
                    generator=gen,
                    settings=settings,
                )
                items.append(row)
                progress.advance(task)

    aggs = [aggregate(items, model=m) for m in model_list]
    # Overlay shared recall onto aggregates so per-model rows do not imply rivalry.
    if recall_shared is not None:
        for a in aggs:
            a.recall_at_k = recall_shared
            a.recall_n = shared_recall_n

    baselines = suggested_baselines(aggs)
    dist = score_distribution(items)
    suggested_score = suggest_min_score(dist)
    cov = coverage_stats(items)

    baseline_verdicts: dict[str, tuple[bool, list[str]]] = {}
    floors: dict[str, float] = {}
    if check_baselines:
        raw_floors = eval_cfg.get("baselines") or {}
        if not isinstance(raw_floors, dict) or not raw_floors:
            raise ValueError(
                "--check-baselines requires configs/rag.yaml eval.baselines "
                "(citation validity / adversarial refusal floors from PR4)."
            )
        floors = {str(k): float(v) for k, v in raw_floors.items()}
        for agg in aggs:
            ok, failures = meets_regression_baselines(agg, floors)
            baseline_verdicts[agg.model] = (ok, failures)

    out_dir = settings.resolve(settings.outputs_dir) / "eval"
    report_stem = stem or default_report_stem()
    md_path, json_path, summary_path = report_paths(out_dir, report_stem)
    if md_path.exists() or json_path.exists() or summary_path.exists():
        n = 2
        while True:
            candidate = f"{report_stem}-{n}"
            md_c, json_c, sum_c = report_paths(out_dir, candidate)
            if not (md_c.exists() or json_c.exists() or sum_c.exists()):
                md_path, json_path, summary_path = md_c, json_c, sum_c
                break
            n += 1

    bucket_list = [str(b) for b in buckets] if buckets else None
    trend_tol = float(eval_cfg.get("trend_tolerance", 0.02))
    comparison: ComparisonResult | None = None
    compare_reason: str | None = None
    comparison_section: str | None = None
    repo_root = settings.effective_root
    created: list[Path] = []

    # Write summary first so compare can exclude it and MD can embed the delta.
    # On later failure, unlink any artifacts this invocation created.
    try:
        created.append(summary_path)
        write_summary_json(
            summary_path,
            profile=profile,
            k=k,
            models=model_list,
            aggs=aggs,
            retrieval_only=retrieval_only,
            include_local=include_local,
            source_counts=source_counts,
            golden_hash=golden_hash,
            golden_local_hash=golden_local_hash,
            recall_shared=recall_shared,
            suggested_min_score=suggested_score,
            coverage=cov,
            baselines_checked=floors,
            baseline_verdicts=baseline_verdicts,
            buckets=bucket_list,
            limit=limit,
        )

        if compare_mode.lower() not in {"auto", "none"}:
            ref_path, compare_reason = early_ref, early_reason
        else:
            ref_path, compare_reason = resolve_compare_reference(
                compare=compare,
                repo_root=repo_root,
                eval_cfg=eval_cfg if isinstance(eval_cfg, dict) else {},
                exclude=summary_path,
                outputs_eval_dir=out_dir,
            )

        compare_display = normalize_compare_display(
            compare, resolved=ref_path, repo_root=repo_root
        )

        if ref_path is not None:
            try:
                prev = load_summary(ref_path)
                curr = load_summary(summary_path)
                comparison = diff_summaries(
                    prev,
                    curr,
                    tolerance=trend_tol,
                    previous_path=ref_path,
                    current_path=summary_path,
                )
                comparison_section = render_comparison_section(
                    comparison, repo_root=repo_root
                )
            except (OSError, ValueError) as exc:
                compare_reason = f"compare failed: {exc}"
                comparison = None
                comparison_section = render_no_comparison_section(compare_reason)
        else:
            comparison_section = render_no_comparison_section(
                compare_reason or "no reference"
            )

        created.append(md_path)
        write_markdown_report(
            md_path,
            profile=profile,
            k=k,
            models=model_list,
            aggs=aggs,
            items=items,
            retrieval_only=retrieval_only,
            include_local=include_local,
            source_counts=source_counts,
            golden_hash=golden_hash,
            golden_local_hash=golden_local_hash,
            recall_shared=recall_shared,
            score_dist=dist,
            suggested_min_score=suggested_score,
            coverage=cov,
            baselines_checked=floors,
            baseline_verdicts=baseline_verdicts,
            baselines_gate_ran=check_baselines,
            comparison_section=comparison_section,
            compare_mode=compare_display,
        )
        created.append(json_path)
        write_json_sidecar(
            json_path,
            profile=profile,
            k=k,
            models=model_list,
            aggs=aggs,
            items=items,
            retrieval_only=retrieval_only,
            include_local=include_local,
            source_counts=source_counts,
            golden_hash=golden_hash,
            golden_local_hash=golden_local_hash,
            recall_shared=recall_shared,
            score_dist=dist,
            suggested_min_score=suggested_score,
            coverage=cov,
        )
    except Exception:
        for path in created:
            if path.is_file():
                path.unlink(missing_ok=True)
        raise

    return EvalResult(
        profile=profile,
        models=model_list,
        k=k,
        items=items,
        aggregates=aggs,
        md_path=md_path,
        json_path=json_path,
        suggested_baselines=baselines,
        include_local=include_local,
        golden_hash=golden_hash,
        golden_local_hash=golden_local_hash,
        source_counts=source_counts,
        recall_shared=recall_shared,
        baseline_verdicts=baseline_verdicts,
        baselines_checked=floors,
        summary_path=summary_path,
        comparison=comparison,
        compare_reason=compare_reason,
        buckets=bucket_list,
        limit=limit,
    )
