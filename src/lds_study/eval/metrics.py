"""Eval metrics — recall@k, citation validity, adversarial refusal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


@dataclass(slots=True)
class ItemMetrics:
    question_id: str
    bucket: str
    model: str
    recall_hit: bool | None  # None when no gold ids
    recall_rank: int | None
    retrieved_ids: list[str] = field(default_factory=list)
    # Seed (non-expand) rerank scores — for min_score calibration.
    seed_scores: list[float] = field(default_factory=list)
    top1_score: float | None = None
    topk_min_score: float | None = None
    status: str | None = None
    exit_code: int | None = None
    # Among non-adversarial answered items only: True iff zero invalid markers.
    citation_valid: bool | None = None
    citation_coverage: float | None = None
    invalid_markers: list[str] = field(default_factory=list)
    had_invalid_marker: bool | None = None
    coverage_gate_fail: bool | None = None  # unsupported with no invalid markers
    refused: bool | None = None
    expect_refuse: bool = False
    refusal_correct: bool | None = None
    quality_manual: str = ""  # human 1-5; blank in automated runs
    source: str = "golden"  # golden | local
    error: str | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.question_id,
            "bucket": self.bucket,
            "model": self.model,
            "source": self.source,
            "recall_hit": self.recall_hit,
            "recall_rank": self.recall_rank,
            "retrieved_ids": list(self.retrieved_ids),
            "seed_scores": list(self.seed_scores),
            "top1_score": self.top1_score,
            "topk_min_score": self.topk_min_score,
            "status": self.status,
            "citation_valid": self.citation_valid,
            "citation_coverage": self.citation_coverage,
            "invalid_markers": list(self.invalid_markers),
            "had_invalid_marker": self.had_invalid_marker,
            "coverage_gate_fail": self.coverage_gate_fail,
            "refused": self.refused,
            "expect_refuse": self.expect_refuse,
            "refusal_correct": self.refusal_correct,
            "quality_manual": self.quality_manual or "",
            "error": self.error,
        }


@dataclass(slots=True)
class AggregateMetrics:
    model: str
    n_items: int
    recall_at_k: float | None
    recall_n: int
    # Non-adversarial answered items: fraction with zero invalid markers.
    citation_validity_rate: float | None
    citation_n: int
    # Non-adversarial answered items: fraction that emitted ≥1 invalid marker.
    invalid_marker_rate: float | None = None
    invalid_marker_n: int = 0
    # Non-adversarial: unsupported caused by coverage (no invalid markers).
    coverage_fail_rate: float | None = None
    coverage_fail_n: int = 0
    adversarial_refusal_rate: float | None = None
    adversarial_n: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    error_n: int = 0
    first_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "n_items": self.n_items,
            "recall_at_k": self.recall_at_k,
            "recall_n": self.recall_n,
            "citation_validity_rate": self.citation_validity_rate,
            "citation_n": self.citation_n,
            "invalid_marker_rate": self.invalid_marker_rate,
            "invalid_marker_n": self.invalid_marker_n,
            "coverage_fail_rate": self.coverage_fail_rate,
            "coverage_fail_n": self.coverage_fail_n,
            "adversarial_refusal_rate": self.adversarial_refusal_rate,
            "adversarial_n": self.adversarial_n,
            "status_counts": dict(self.status_counts),
            "error_n": self.error_n,
            "first_error": self.first_error,
        }


def recall_at_k(
    retrieved_ids: Sequence[str],
    gold_chunk_ids: Sequence[str],
    *,
    k: int,
) -> tuple[bool, int | None]:
    """Return (hit, best_rank_1based) if any gold id appears in top-k retrieved seeds."""
    if not gold_chunk_ids:
        return False, None
    gold = set(gold_chunk_ids)
    top = list(retrieved_ids)[: max(0, k)]
    best: int | None = None
    for i, cid in enumerate(top, start=1):
        if cid in gold:
            best = i
            break
    return best is not None, best


def is_refusal_status(status: str | None) -> bool:
    return status in {"no_evidence", "unsupported"}


def _rate(oks: list[bool]) -> float | None:
    if not oks:
        return None
    return sum(1 for x in oks if x) / len(oks)


def aggregate(items: Iterable[ItemMetrics], *, model: str) -> AggregateMetrics:
    rows = [r for r in items if r.model == model]
    recall_hits = [r for r in rows if r.recall_hit is not None]
    # Citation metrics: non-adversarial items that attempted an answer.
    cite_rows = [
        r
        for r in rows
        if not r.expect_refuse and r.citation_valid is not None
    ]
    invalid_rows = [
        r
        for r in rows
        if not r.expect_refuse and r.had_invalid_marker is not None
    ]
    coverage_rows = [
        r
        for r in rows
        if not r.expect_refuse and r.coverage_gate_fail is not None
    ]
    adv = [r for r in rows if r.expect_refuse and r.refusal_correct is not None]
    status_counts: dict[str, int] = {}
    errors = [r.error for r in rows if r.error]
    for r in rows:
        key = r.status or ("error" if r.error else "unknown")
        status_counts[key] = status_counts.get(key, 0) + 1

    return AggregateMetrics(
        model=model,
        n_items=len(rows),
        recall_at_k=_rate([bool(r.recall_hit) for r in recall_hits]),
        recall_n=len(recall_hits),
        citation_validity_rate=_rate([bool(r.citation_valid) for r in cite_rows]),
        citation_n=len(cite_rows),
        invalid_marker_rate=_rate([bool(r.had_invalid_marker) for r in invalid_rows]),
        invalid_marker_n=len(invalid_rows),
        coverage_fail_rate=_rate([bool(r.coverage_gate_fail) for r in coverage_rows]),
        coverage_fail_n=len(coverage_rows),
        adversarial_refusal_rate=_rate([bool(r.refusal_correct) for r in adv]),
        adversarial_n=len(adv),
        status_counts=status_counts,
        error_n=len(errors),
        first_error=errors[0] if errors else None,
    )


def suggested_baselines(aggs: Sequence[AggregateMetrics]) -> dict[str, float]:
    """Conservative floors = 90% of best observed (no artificial floor clamp).

    Used to populate configs/rag.yaml eval.baselines after a comparison run.
    """
    if not aggs:
        return {}
    recalls = [a.recall_at_k for a in aggs if a.recall_at_k is not None]
    cites = [a.citation_validity_rate for a in aggs if a.citation_validity_rate is not None]
    refuses = [
        a.adversarial_refusal_rate
        for a in aggs
        if a.adversarial_refusal_rate is not None
    ]
    out: dict[str, float] = {}
    if recalls:
        out["min_recall_at_k"] = round(max(recalls) * 0.9, 3)
    if cites:
        out["min_citation_validity"] = round(max(cites) * 0.9, 3)
    if refuses:
        out["min_adversarial_refusal"] = round(max(refuses) * 0.9, 3)
    return out


def meets_regression_baselines(
    agg: AggregateMetrics,
    baselines: dict[str, float],
) -> tuple[bool, list[str]]:
    """PR5 keep-or-revert gate: citation validity + adversarial refusal (+ recall).

    Returns ``(ok, failure_messages)``. A style adapter that loses groundedness
    or refusal quality is a regression, not a tradeoff.
    """
    failures: list[str] = []
    cite_floor = baselines.get("min_citation_validity")
    if cite_floor is not None:
        got = agg.citation_validity_rate
        if got is None or got < float(cite_floor):
            failures.append(
                f"citation_validity {got} < min_citation_validity {cite_floor}"
            )
    refuse_floor = baselines.get("min_adversarial_refusal")
    if refuse_floor is not None:
        got = agg.adversarial_refusal_rate
        if got is None or got < float(refuse_floor):
            failures.append(
                f"adversarial_refusal {got} < min_adversarial_refusal {refuse_floor}"
            )
    recall_floor = baselines.get("min_recall_at_k")
    if recall_floor is not None:
        got = agg.recall_at_k
        if got is None or got < float(recall_floor):
            failures.append(f"recall_at_k {got} < min_recall_at_k {recall_floor}")
    return (not failures), failures


def score_distribution(
    items: Sequence[ItemMetrics],
) -> dict[str, Any]:
    """Summarize top-1 seed scores for grounded vs adversarial questions.

    Shared across models (retrieval is model-independent); uses first model only
    when multiple are present for the same question id.
    """
    seen: set[str] = set()
    grounded: list[float] = []
    adversarial: list[float] = []
    for row in items:
        if row.question_id in seen:
            continue
        if row.top1_score is None:
            continue
        seen.add(row.question_id)
        if row.expect_refuse:
            adversarial.append(row.top1_score)
        else:
            grounded.append(row.top1_score)

    def _stats(vals: list[float]) -> dict[str, float | int | None]:
        if not vals:
            return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}
        s = sorted(vals)

        def pct(p: float) -> float:
            if len(s) == 1:
                return s[0]
            idx = (len(s) - 1) * p
            lo = int(idx)
            hi = min(lo + 1, len(s) - 1)
            frac = idx - lo
            return s[lo] * (1 - frac) + s[hi] * frac

        return {
            "n": len(s),
            "min": round(s[0], 4),
            "p25": round(pct(0.25), 4),
            "median": round(pct(0.5), 4),
            "p75": round(pct(0.75), 4),
            "max": round(s[-1], 4),
        }

    return {
        "grounded_top1": _stats(grounded),
        "adversarial_top1": _stats(adversarial),
    }


def suggest_min_score(dist: dict[str, Any]) -> float | None:
    """Heuristic floor: midpoint between adversarial p75 and grounded p25 when ordered."""
    adv = dist.get("adversarial_top1") or {}
    gnd = dist.get("grounded_top1") or {}
    adv_p75 = adv.get("p75")
    gnd_p25 = gnd.get("p25")
    if adv_p75 is None or gnd_p25 is None:
        return None
    if gnd_p25 <= adv_p75:
        # Overlap — no clean threshold; leave None.
        return None
    return round((float(adv_p75) + float(gnd_p25)) / 2.0, 4)


def coverage_stats(items: Sequence[ItemMetrics]) -> dict[str, Any]:
    """Coverage values for non-adversarial answered items (for min_coverage calibration)."""
    vals = [
        r.citation_coverage
        for r in items
        if not r.expect_refuse
        and r.citation_coverage is not None
        and r.status in {"ok", "unsupported"}
    ]
    ok_vals = [
        r.citation_coverage
        for r in items
        if not r.expect_refuse and r.status == "ok" and r.citation_coverage is not None
    ]
    if not vals:
        return {"n": 0}
    s = sorted(float(v) for v in vals)
    ok_s = sorted(float(v) for v in ok_vals) if ok_vals else []
    return {
        "n": len(s),
        "min": round(s[0], 3),
        "median": round(s[len(s) // 2], 3),
        "max": round(s[-1], 3),
        "ok_n": len(ok_s),
        "ok_min": round(ok_s[0], 3) if ok_s else None,
        "ok_median": round(ok_s[len(ok_s) // 2], 3) if ok_s else None,
    }
