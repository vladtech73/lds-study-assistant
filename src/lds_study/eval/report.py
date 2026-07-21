"""Markdown + JSON report writers for `lds eval`."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lds_study.eval.metrics import AggregateMetrics, ItemMetrics, suggested_baselines


def default_report_stem(when: date | None = None) -> str:
    return (when or date.today()).isoformat()


def report_paths(outputs_eval_dir: Path, stem: str) -> tuple[Path, Path]:
    """Return (md_path, json_path). JSON is local-only (gitignored via outputs/**)."""
    outputs_eval_dir.mkdir(parents=True, exist_ok=True)
    return outputs_eval_dir / f"{stem}.md", outputs_eval_dir / f"{stem}.json"


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * value:.1f}%"


def render_comparison_table(aggs: Sequence[AggregateMetrics]) -> str:
    lines = [
        "| Model | n | Cite validity (non-adv) | Invalid markers | Coverage fail | "
        "Adversarial refusal | errors |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for a in aggs:
        err = str(a.error_n)
        if a.first_error and a.error_n:
            err = f"{a.error_n}*"
        lines.append(
            f"| `{a.model}` | {a.n_items} | {_pct(a.citation_validity_rate)} "
            f"({a.citation_n}) | {_pct(a.invalid_marker_rate)} ({a.invalid_marker_n}) | "
            f"{_pct(a.coverage_fail_rate)} ({a.coverage_fail_n}) | "
            f"{_pct(a.adversarial_refusal_rate)} ({a.adversarial_n}) | {err} |"
        )
    return "\n".join(lines)


def _fmt_stats(block: dict[str, Any]) -> str:
    if not block or not block.get("n"):
        return "n=0"
    return (
        f"n={block['n']} min={block.get('min')} p25={block.get('p25')} "
        f"median={block.get('median')} p75={block.get('p75')} max={block.get('max')}"
    )


def write_markdown_report(
    path: Path,
    *,
    profile: str,
    k: int,
    models: Sequence[str],
    aggs: Sequence[AggregateMetrics],
    items: Sequence[ItemMetrics],
    retrieval_only: bool,
    include_local: bool = False,
    source_counts: dict[str, int] | None = None,
    golden_hash: str | None = None,
    golden_local_hash: str | None = None,
    recall_shared: float | None = None,
    score_dist: dict[str, Any] | None = None,
    suggested_min_score: float | None = None,
    coverage: dict[str, Any] | None = None,
    notes: str = "",
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    baselines = suggested_baselines(aggs)
    source_counts = source_counts or {}
    # Deduplicate by question for shared retrieval depth (post min_score).
    seen_q: set[str] = set()
    grounded_seed_ns: list[int] = []
    for r in items:
        if r.expect_refuse or r.question_id in seen_q:
            continue
        seen_q.add(r.question_id)
        grounded_seed_ns.append(len(r.seed_scores))
    median_seeds = None
    if grounded_seed_ns:
        s = sorted(grounded_seed_ns)
        median_seeds = s[len(s) // 2]

    lines: list[str] = [
        f"# Eval report — {path.stem}",
        "",
        f"- Generated: {now}",
        f"- Profile: `{profile}`",
        f"- Models: {', '.join(f'`{m}`' for m in models)}",
        f"- Recall@{k} (shared / model-independent); retrieval_only={retrieval_only}",
        f"- include_local={include_local}; source_counts={source_counts}",
        f"- golden.yaml sha256[:16]={golden_hash or 'n/a'}",
        f"- golden.local.yaml sha256[:16]={golden_local_hash or 'n/a'}",
        "- Manual quality column is left blank for human scoring (1-5).",
        "",
        "## Retrieval quality (shared)",
        "",
        f"- Recall@{k}: {_pct(recall_shared)}",
        f"- Median grounded seed-hit count: {median_seeds if median_seeds is not None else 'n/a'}",
        "",
    ]
    if score_dist:
        lines.extend(
            [
                "### Top-1 seed score distribution",
                "",
                f"- Grounded: {_fmt_stats(score_dist.get('grounded_top1') or {})}",
                f"- Adversarial: {_fmt_stats(score_dist.get('adversarial_top1') or {})}",
                "",
            ]
        )
        if suggested_min_score is not None:
            lines.append(
                f"- Suggested `retrieval.min_score` (midpoint adv p75 / grounded p25): "
                f"**{suggested_min_score}**"
            )
            lines.append("")
        else:
            lines.append(
                "- No clean `min_score` separation (adversarial and grounded score "
                "distributions overlap)."
            )
            lines.append("")

    if coverage and coverage.get("n"):
        lines.extend(
            [
                "### Citation coverage (non-adversarial answered)",
                "",
                f"- All answered: n={coverage.get('n')} min={coverage.get('min')} "
                f"median={coverage.get('median')} max={coverage.get('max')}",
                f"- status=ok only: n={coverage.get('ok_n')} "
                f"min={coverage.get('ok_min')} median={coverage.get('ok_median')}",
                "",
            ]
        )

    lines.extend(
        [
            "## Comparison (generation)",
            "",
            render_comparison_table(aggs),
            "",
        ]
    )
    if any(a.error_n for a in aggs):
        lines.append(
            "\\* First error message(s): "
            + "; ".join(
                f"`{a.model}`: {a.first_error}" for a in aggs if a.first_error
            )
        )
        lines.append("")

    if baselines:
        lines.extend(
            [
                "## Suggested regression baselines",
                "",
                "Conservative floors (90% of best observed; no artificial clamp) "
                "for `configs/rag.yaml`:",
                "",
                "```yaml",
                "eval:",
                "  baselines:",
            ]
        )
        for key, val in baselines.items():
            lines.append(f"    {key}: {val}")
        lines.extend(["```", ""])

    if notes.strip():
        lines.extend(["## Notes", "", notes.strip(), ""])

    lines.extend(
        [
            "## Per-item results",
            "",
            "| id | src | bucket | model | recall | rank | top1 | status | "
            "cite_ok | inv | cov_fail | coverage | refuse_ok | quality |",
            "|---|---|---|---|---|---:|---:|---|---|---|---|---:|---|---|",
        ]
    )
    for row in items:
        recall = (
            "—"
            if row.recall_hit is None
            else ("Y" if row.recall_hit else "N")
        )
        rank = "—" if row.recall_rank is None else str(row.recall_rank)
        top1 = "—" if row.top1_score is None else f"{row.top1_score:.3f}"
        cite = (
            "—"
            if row.citation_valid is None
            else ("Y" if row.citation_valid else "N")
        )
        inv = (
            "—"
            if row.had_invalid_marker is None
            else ("Y" if row.had_invalid_marker else "N")
        )
        cov_fail = (
            "—"
            if row.coverage_gate_fail is None
            else ("Y" if row.coverage_gate_fail else "N")
        )
        cov = (
            "—"
            if row.citation_coverage is None
            else f"{row.citation_coverage:.2f}"
        )
        refuse = (
            "—"
            if row.refusal_correct is None
            else ("Y" if row.refusal_correct else "N")
        )
        status = row.status or ("error" if row.error else "")
        quality = row.quality_manual or ""
        lines.append(
            f"| `{row.question_id}` | {row.source} | {row.bucket} | `{row.model}` | "
            f"{recall} | {rank} | {top1} | {status} | {cite} | {inv} | {cov_fail} | "
            f"{cov} | {refuse} | {quality} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def items_payload(items: Sequence[ItemMetrics]) -> list[dict[str, Any]]:
    return [i.to_row() for i in items]


def write_json_sidecar(
    path: Path,
    *,
    profile: str,
    k: int,
    models: Sequence[str],
    aggs: Sequence[AggregateMetrics],
    items: Sequence[ItemMetrics],
    retrieval_only: bool,
    include_local: bool = False,
    source_counts: dict[str, int] | None = None,
    golden_hash: str | None = None,
    golden_local_hash: str | None = None,
    recall_shared: float | None = None,
    score_dist: dict[str, Any] | None = None,
    suggested_min_score: float | None = None,
    coverage: dict[str, Any] | None = None,
) -> None:
    import json

    payload = {
        "profile": profile,
        "k": k,
        "models": list(models),
        "retrieval_only": retrieval_only,
        "include_local": include_local,
        "source_counts": source_counts or {},
        "golden_hash": golden_hash,
        "golden_local_hash": golden_local_hash,
        "recall_shared": recall_shared,
        "score_distribution": score_dist,
        "suggested_min_score": suggested_min_score,
        "coverage_stats": coverage,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregates": [a.to_dict() for a in aggs],
        "suggested_baselines": suggested_baselines(aggs),
        "items": items_payload(items),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
