"""Compare two aggregates-only eval summaries (PR6a ``--compare``)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lds_study.eval.report import SUMMARY_AGGREGATE_KEYS, SUMMARY_SCHEMA_VERSION

# Shape fields that must match for a meaningful trend diff.
COMPARABILITY_FIELDS = (
    "golden_hash",
    "golden_local_hash",
    "k",
    "profile",
    "include_local",
    "retrieval_only",
    "buckets",
    "limit",
    "models",
    "source_counts",
)

# Shared metrics (top-level) then per-model generation metrics.
_SHARED_METRIC_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("recall_shared", "recall@k", True),
)
_PER_MODEL_METRIC_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("citation_validity_rate", "citation_validity", True),
    ("invalid_marker_rate", "invalid_marker_rate", False),
    ("coverage_fail_rate", "coverage_fail_rate", False),
    ("adversarial_refusal_rate", "adversarial_refusal", True),
    # Lower-is-better count; any increase (or measurable→unmeasurable) is a regression.
    ("error_n", "error_n", False),
)

# Fail closed if the summary projection drops a key diff_summaries needs.
_COMPARE_REQUIRED_AGGREGATE_KEYS = frozenset(
    {key for key, _, _ in _PER_MODEL_METRIC_SPECS} | {"recall_at_k", "model"}
)
if not _COMPARE_REQUIRED_AGGREGATE_KEYS <= SUMMARY_AGGREGATE_KEYS:
    missing = sorted(_COMPARE_REQUIRED_AGGREGATE_KEYS - SUMMARY_AGGREGATE_KEYS)
    raise RuntimeError(
        "SUMMARY_AGGREGATE_KEYS missing keys required by diff_summaries: "
        + ", ".join(missing)
    )


@dataclass(slots=True)
class MetricDelta:
    name: str
    previous: float | None
    current: float | None
    delta: float | None
    higher_is_better: bool
    regressed: bool
    improved: bool
    model: str | None = None


@dataclass(slots=True)
class ComparisonResult:
    comparable: bool
    reason: str
    previous_path: Path | None = None
    current_path: Path | None = None
    mismatches: list[str] = field(default_factory=list)
    deltas: list[MetricDelta] = field(default_factory=list)
    tolerance: float = 0.0

    @property
    def any_regressed(self) -> bool:
        return any(d.regressed for d in self.deltas)

    @property
    def unmeasurable_lost_n(self) -> int:
        """Metrics that were present previously and are None now."""
        return sum(
            1
            for d in self.deltas
            if d.previous is not None and d.current is None
        )


def load_summary(path: Path) -> dict[str, Any]:
    """Load an aggregates-only ``*.summary.json``.

    Rejects full sidecars (``items`` present) and unknown ``schema_version`` so
    ``--compare`` cannot silently trend against a restricted or future-shaped file.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        # Use path.name so absolute machine paths never enter committed reports
        # via the soft-failure "compare failed:" branch.
        raise ValueError(f"summary is not an object: {path.name}")
    if "items" in data:
        raise ValueError(
            f"refusing full eval sidecar (has items): {path.name} "
            "(pass a *.summary.json, not *.json)"
        )
    version = data.get("schema_version")
    if version != SUMMARY_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported summary schema_version={version!r} in {path.name} "
            f"(expected {SUMMARY_SCHEMA_VERSION})"
        )
    return data


def _norm_shape_value(key: str, value: Any) -> Any:
    if key in {"buckets", "models"}:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return tuple(sorted(str(x) for x in value))
        return (str(value),)
    if key == "source_counts":
        if value is None:
            return None
        if isinstance(value, dict):
            return tuple(sorted((str(k), int(v)) for k, v in value.items()))
        return value
    return value


def comparability_mismatches(prev: dict[str, Any], curr: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for key in COMPARABILITY_FIELDS:
        pv = _norm_shape_value(key, prev.get(key))
        cv = _norm_shape_value(key, curr.get(key))
        if pv != cv:
            mismatches.append(f"{key}: previous={pv!r} current={cv!r}")
    return mismatches


def _aggregates_by_model(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in summary.get("aggregates") or []:
        if not isinstance(row, dict):
            continue
        model = row.get("model")
        if model is None:
            continue
        out[str(model)] = row
    return out


def _metric_from_agg(agg: dict[str, Any], key: str) -> float | None:
    raw = agg.get(key)
    if raw is None:
        return None
    return float(raw)


def _shared_metric_value(summary: dict[str, Any], key: str) -> float | None:
    if key == "recall_shared":
        raw = summary.get("recall_shared")
        if raw is None:
            by_model = _aggregates_by_model(summary)
            if by_model:
                raw = next(iter(by_model.values())).get("recall_at_k")
        if raw is None:
            return None
        return float(raw)
    return None


def _is_regressed(
    *,
    delta: float | None,
    higher_is_better: bool,
    tolerance: float,
) -> bool:
    if delta is None:
        return False
    if higher_is_better:
        return delta < -tolerance
    return delta > tolerance


def _is_improved(
    *,
    delta: float | None,
    higher_is_better: bool,
    tolerance: float,
) -> bool:
    if delta is None:
        return False
    if higher_is_better:
        return delta > tolerance
    return delta < -tolerance


def _metric_tolerance(
    *,
    key: str,
    retrieval_only: bool,
    configured: float,
) -> float:
    """Recall / error counts are exact (tol=0). Generation rates use the noise band."""
    if key in {"recall_shared", "error_n"} or retrieval_only:
        return 0.0
    return float(configured)


def _make_delta(
    *,
    name: str,
    key: str,
    prev_v: float | None,
    curr_v: float | None,
    higher_is_better: bool,
    retrieval_only: bool,
    configured: float,
    model: str | None = None,
) -> MetricDelta:
    metric_tol = _metric_tolerance(
        key=key, retrieval_only=retrieval_only, configured=configured
    )
    if prev_v is None and curr_v is None:
        delta = None
        regressed = False
        improved = False
    elif prev_v is not None and curr_v is None:
        # Was measurable, now unmeasurable — treat as regression (not "flat").
        delta = None
        regressed = True
        improved = False
    elif prev_v is None and curr_v is not None:
        delta = None
        regressed = False
        improved = False
    else:
        delta = curr_v - prev_v  # type: ignore[operator]
        regressed = _is_regressed(
            delta=delta,
            higher_is_better=higher_is_better,
            tolerance=metric_tol,
        )
        improved = _is_improved(
            delta=delta,
            higher_is_better=higher_is_better,
            tolerance=metric_tol,
        )
    return MetricDelta(
        name=name,
        previous=prev_v,
        current=curr_v,
        delta=delta,
        higher_is_better=higher_is_better,
        regressed=regressed,
        improved=improved,
        model=model,
    )


def diff_summaries(
    prev: dict[str, Any],
    curr: dict[str, Any],
    *,
    tolerance: float | None = None,
    previous_path: Path | None = None,
    current_path: Path | None = None,
) -> ComparisonResult:
    """Produce per-metric deltas; mark regressed only beyond ``tolerance``."""
    mismatches = comparability_mismatches(prev, curr)
    configured = 0.02 if tolerance is None else float(tolerance)
    if mismatches:
        return ComparisonResult(
            comparable=False,
            reason="not comparable -- run shape differs: " + "; ".join(mismatches),
            previous_path=previous_path,
            current_path=current_path,
            mismatches=mismatches,
            tolerance=configured,
        )

    retrieval_only = bool(curr.get("retrieval_only"))
    deltas: list[MetricDelta] = []
    for key, name, higher_is_better in _SHARED_METRIC_SPECS:
        deltas.append(
            _make_delta(
                name=name,
                key=key,
                prev_v=_shared_metric_value(prev, key),
                curr_v=_shared_metric_value(curr, key),
                higher_is_better=higher_is_better,
                retrieval_only=retrieval_only,
                configured=configured,
            )
        )

    if not retrieval_only:
        prev_by = _aggregates_by_model(prev)
        curr_by = _aggregates_by_model(curr)
        # Intersection in sorted order for stable output (models already comparable).
        for model in sorted(set(prev_by) & set(curr_by)):
            for key, name, higher_is_better in _PER_MODEL_METRIC_SPECS:
                deltas.append(
                    _make_delta(
                        name=name,
                        key=key,
                        prev_v=_metric_from_agg(prev_by[model], key),
                        curr_v=_metric_from_agg(curr_by[model], key),
                        higher_is_better=higher_is_better,
                        retrieval_only=retrieval_only,
                        configured=configured,
                        model=model,
                    )
                )

    return ComparisonResult(
        comparable=True,
        reason="ok",
        previous_path=previous_path,
        current_path=current_path,
        deltas=deltas,
        tolerance=configured,
    )


def display_path(path: Path, repo_root: Path) -> str:
    """Repo-relative posix path for committed reports; filename if outside the repo."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def normalize_compare_display(
    compare: str,
    *,
    resolved: Path | None,
    repo_root: Path,
) -> str:
    """Stable ``compare=`` header value: auto/none, or a repo-relative stem/path."""
    mode = (compare or "auto").strip()
    if mode.lower() in {"auto", "none"}:
        return mode.lower()
    if resolved is not None:
        return display_path(resolved, repo_root)
    # Unresolved should not reach report writers for explicit mode (fail-fast),
    # but keep a portable fallback.
    return Path(mode).name


def render_no_comparison_section(reason: str) -> str:
    """Stub section when no reference resolved (still durable in the committed report)."""
    return "\n".join(
        [
            "## Trend vs previous",
            "",
            f"- No comparison: {reason}",
            "",
        ]
    )


def render_comparison_section(
    result: ComparisonResult,
    *,
    repo_root: Path | None = None,
) -> str:
    """Markdown section for ``write_markdown_report``."""
    lines = ["## Trend vs previous", ""]

    def _fmt(path: Path | None) -> str | None:
        if path is None:
            return None
        if repo_root is None:
            return path.as_posix()
        return display_path(path, repo_root)

    prev_disp = _fmt(result.previous_path)
    curr_disp = _fmt(result.current_path)
    if prev_disp is not None:
        lines.append(f"- Previous: `{prev_disp}`")
    if curr_disp is not None:
        lines.append(f"- Current: `{curr_disp}`")
    if not result.comparable:
        lines.extend(["", f"**Not comparable:** {result.reason}", ""])
        return "\n".join(lines)

    lines.append(f"- Trend tolerance: {result.tolerance}")
    lines.append("")
    lines.extend(
        [
            "| Metric | model | previous | current | delta | verdict |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for d in result.deltas:
        model_s = d.model or "—"
        prev_s = "n/a" if d.previous is None else f"{d.previous:.4f}"
        curr_s = "n/a" if d.current is None else f"{d.current:.4f}"
        if d.previous is not None and d.current is None:
            delta_s = "unmeasurable"
            verdict = "lost"
        elif d.delta is None:
            delta_s = "n/a"
            verdict = "n/a"
        else:
            delta_s = f"{d.delta:+.4f}"
            if d.regressed:
                verdict = "regressed"
            elif d.improved:
                verdict = "improved"
            else:
                verdict = "flat"
        lines.append(
            f"| {d.name} | {model_s} | {prev_s} | {curr_s} | {delta_s} | {verdict} |"
        )
    lines.append("")
    lost_n = result.unmeasurable_lost_n
    if result.any_regressed:
        if lost_n:
            lines.append(
                f"**Trend:** regression(s) beyond tolerance "
                f"({lost_n} metric(s) became unmeasurable)."
            )
        else:
            lines.append("**Trend:** regression(s) beyond tolerance.")
    elif lost_n:
        lines.append(
            f"**Trend:** {lost_n} metric(s) became unmeasurable (no numeric delta)."
        )
    else:
        lines.append("**Trend:** no regression beyond tolerance.")
    lines.append("")
    return "\n".join(lines)


def render_comparison_console(result: ComparisonResult) -> list[str]:
    """Plain lines for CLI console output (ASCII-safe for redirected Windows stdout)."""
    lines: list[str] = []
    if not result.comparable:
        # Reason already starts with "not comparable -- …"; don't double-prefix.
        lines.append(f"Comparison: {result.reason}")
        return lines
    lines.append("Comparison vs previous:")
    for d in result.deltas:
        # Parentheses, not brackets -- rich would parse [model] as markup.
        label = d.name if d.model is None else f"{d.name} ({d.model})"
        if d.previous is not None and d.current is None:
            lines.append(
                f"  {label}: {d.previous:.4f} -> unmeasurable [REGRESSED]"
            )
            continue
        if d.delta is None:
            lines.append(f"  {label}: n/a")
            continue
        flag = ""
        if d.regressed:
            flag = " [REGRESSED]"
        elif d.improved:
            flag = " [improved]"
        lines.append(
            f"  {label}: {d.previous:.4f} -> {d.current:.4f} "
            f"({d.delta:+.4f}){flag}"
        )
    return lines


def _git_tracked_summaries(repo_root: Path) -> list[Path]:
    """Return tracked ``outputs/eval/*.summary.json`` paths."""
    if shutil.which("git") is None:
        return []
    try:
        proc = subprocess.run(
            ["git", "ls-files", "outputs/eval/*.summary.json"],
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    paths: list[Path] = []
    for line in proc.stdout.splitlines():
        rel = line.strip().replace("\\", "/")
        if not rel.endswith(".summary.json"):
            continue
        paths.append(repo_root / rel)
    return [p for p in paths if p.is_file()]


def _parse_generated_at(raw: Any) -> float | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _summary_recency(path: Path) -> tuple[tuple[float, float], str]:
    """Return ((generated_at epoch, mtime), stamp) for sort + reason text."""
    mtime = path.stat().st_mtime
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            raw_ga = data.get("generated_at")
            ga = _parse_generated_at(raw_ga)
            if ga is not None:
                return (ga, mtime), str(raw_ga)
    except (OSError, ValueError):
        pass
    return (mtime, mtime), f"mtime={mtime:.0f}"


def _resolve_summary_candidate(
    ref: str,
    *,
    repo_root: Path,
    outputs_eval_dir: Path | None,
) -> Path | None:
    """Resolve a path, stem, or relative name to an existing ``*.summary.json``."""
    raw = Path(ref)
    out_dir = outputs_eval_dir or (repo_root / "outputs" / "eval")
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend(
            [
                repo_root / raw,
                out_dir / raw,
                out_dir / f"{raw.name}.summary.json"
                if not raw.name.endswith(".summary.json")
                else out_dir / raw.name,
                out_dir / f"{raw.stem}.summary.json",
            ]
        )
        if "/" not in ref.replace("\\", "/") and not ref.endswith(".json"):
            candidates.append(out_dir / f"{ref}.summary.json")
    for c in candidates:
        if c.is_file() and c.name.endswith(".summary.json"):
            return c.resolve()
    return None


def resolve_compare_reference(
    *,
    compare: str,
    repo_root: Path,
    eval_cfg: dict[str, Any],
    exclude: Path | None = None,
    outputs_eval_dir: Path | None = None,
) -> tuple[Path | None, str]:
    """Resolve ``--compare`` to a summary path and a human reason string.

    Resolution for ``auto``:
      1. ``eval.reference_report`` stem/path in rag.yaml (if set)
      2. newest *git-tracked* ``*.summary.json`` by ``generated_at`` (mtime fallback),
         excluding ``exclude``
    Never falls back to an untracked file.

    Explicit paths that do not resolve raise ``ValueError`` (hard fail).
    """
    mode = (compare or "auto").strip()
    if mode.lower() == "none":
        return None, "compare=none"

    if mode.lower() != "auto":
        path = _resolve_summary_candidate(
            mode, repo_root=repo_root, outputs_eval_dir=outputs_eval_dir
        )
        if path is None:
            raise ValueError(f"compare path not found: {mode}")
        return path, f"explicit --compare {path}"

    ref = eval_cfg.get("reference_report")
    if ref:
        ref_s = str(ref).strip()
        path = _resolve_summary_candidate(
            ref_s, repo_root=repo_root, outputs_eval_dir=outputs_eval_dir
        )
        if path is not None:
            if exclude is None or path != exclude.resolve():
                return path, f"eval.reference_report={ref_s}"

    tracked = _git_tracked_summaries(repo_root)
    if exclude is not None:
        ex = exclude.resolve()
        tracked = [p for p in tracked if p.resolve() != ex]

    if not tracked:
        return None, "no reference (no tracked *.summary.json)"

    ranked = sorted(
        ((_summary_recency(p), p) for p in tracked),
        key=lambda item: item[0][0],
        reverse=True,
    )
    (_key, stamp), chosen_path = ranked[0]
    chosen = chosen_path.resolve()
    return (
        chosen,
        f"newest git-tracked summary ({chosen.name}, generated_at={stamp})",
    )
