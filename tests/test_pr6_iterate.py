"""PR6a — eval summaries + --compare (offline; no GPU/Ollama)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from lds_study.config import Settings
from lds_study.data.models import Chunk
from lds_study.eval.compare import (
    diff_summaries,
    resolve_compare_reference,
)
from lds_study.eval.metrics import AggregateMetrics
from lds_study.eval.report import (
    SUMMARY_AGGREGATE_KEYS,
    SUMMARY_TOP_LEVEL_KEYS,
    build_summary_payload,
    summary_safe_aggregate,
    write_summary_json,
)
from lds_study.eval.run import run_eval
from lds_study.index.base import RetrievalResult, RetrievedHit
from lds_study.rag.generate import ScriptedGenerator

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_staged_data.py"


def _chunk(cid: str, text: str = "t") -> Chunk:
    return Chunk(
        id=cid,
        text=text,
        source_id="fixture",
        source_type="scripture",
        redistributable=True,
        canonical_ref=cid,
    )


class _FakeRetriever:
    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self.mapping = mapping

    def retrieve(self, query: str, *, filters=None, top_k=None):  # noqa: ANN001
        if query in self.mapping:
            ids = list(self.mapping[query])
        else:
            ids = list(self.mapping.get("*") or [])
        if top_k is not None:
            ids = ids[:top_k]
        hits = [
            RetrievedHit(chunk=_chunk(cid), score=1.0 - i * 0.01, source="hybrid")
            for i, cid in enumerate(ids)
        ]
        return RetrievalResult(hits=hits)


def _mini_settings(tmp_path: Path) -> Settings:
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / "golden.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "questions": [
                    {
                        "id": "t-1",
                        "bucket": "verse_lookup",
                        "question": "q1",
                        "gold_chunk_ids": ["bofm/alma/32/27"],
                    },
                    {
                        "id": "t-2",
                        "bucket": "adversarial",
                        "question": "q2",
                        "expect_refuse": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    cfg = tmp_path / "configs"
    cfg.mkdir(exist_ok=True)
    (cfg / "models.yaml").write_text(
        "generator:\n  id: mock-a\nshortlist:\n  - mock-a\n",
        encoding="utf-8",
    )
    (cfg / "rag.yaml").write_text(
        "retrieval:\n  final_top_k: 8\neval:\n  recall_k: 8\n"
        "  trend_tolerance: 0.25\n  baselines:\n"
        "    min_recall_at_k: 0.5\n"
        "    min_citation_validity: 0.5\n"
        "    min_adversarial_refusal: 0.5\n",
        encoding="utf-8",
    )
    return Settings(
        root=tmp_path,
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "indexes",
        models_dir=tmp_path / "models",
        outputs_dir=tmp_path / "outputs",
    )


def _agg(
    *,
    model: str = "m",
    recall: float = 0.8,
    cite: float = 0.9,
    inv: float = 0.05,
    cov: float = 0.1,
    refuse: float = 0.85,
) -> AggregateMetrics:
    return AggregateMetrics(
        model=model,
        n_items=10,
        recall_at_k=recall,
        recall_n=10,
        citation_validity_rate=cite,
        citation_n=8,
        invalid_marker_rate=inv,
        invalid_marker_n=8,
        coverage_fail_rate=cov,
        coverage_fail_n=8,
        adversarial_refusal_rate=refuse,
        adversarial_n=10,
    )


def _base_summary(**overrides: object) -> dict:
    payload = build_summary_payload(
        profile="default",
        k=8,
        models=["m"],
        aggs=[_agg()],
        retrieval_only=False,
        include_local=False,
        golden_hash="abc123",
        recall_shared=0.8,
        baselines_checked={"min_recall_at_k": 0.7},
        baseline_verdicts={"m": (True, [])},
        buckets=None,
        limit=None,
    )
    payload.update(overrides)
    return payload


def test_write_summary_json_round_trip_no_items(tmp_path: Path) -> None:
    path = tmp_path / "unit.summary.json"
    leaky = _agg(model="mock-a")
    leaky.first_error = "upstream 400: prompt was SECRET_SHOULD_NOT_APPEAR"
    payload = write_summary_json(
        path,
        profile="default",
        k=8,
        models=["mock-a"],
        aggs=[leaky],
        retrieval_only=True,
        include_local=False,
        golden_hash="deadbeef",
        recall_shared=1.0,
        baselines_checked={"min_recall_at_k": 0.9},
        baseline_verdicts={"mock-a": (False, ["recall_at_k 0.5 < 0.9"])},
        buckets=["verse_lookup"],
        limit=5,
    )
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 1
    assert "items" not in loaded
    assert "first_error" not in loaded["aggregates"][0]
    assert "SECRET_SHOULD_NOT_APPEAR" not in path.read_text(encoding="utf-8")
    assert set(loaded) <= SUMMARY_TOP_LEVEL_KEYS
    assert set(loaded["aggregates"][0]) <= SUMMARY_AGGREGATE_KEYS
    assert loaded["baseline_verdicts"]["mock-a"]["keep"] is False
    assert loaded["baselines_checked"]["min_recall_at_k"] == 0.9
    assert loaded["buckets"] == ["verse_lookup"]
    assert loaded["limit"] == 5
    assert payload["aggregates"][0]["model"] == "mock-a"
    assert summary_safe_aggregate(leaky).get("first_error") is None


def test_summary_copyright_boundary_generation_path_error(tmp_path: Path) -> None:
    """Generation errors that echo restricted question text must not enter summary."""
    settings = _mini_settings(tmp_path)
    secret = "RESTRICTED_LOCAL_QUESTION_TEXT_NEVER_COMMIT"
    (tmp_path / "eval" / "golden.local.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "questions": [
                    {
                        "id": "local-1",
                        "bucket": "verse_lookup",
                        "question": secret,
                        "gold_chunk_ids": ["bofm/alma/32/27"],
                        "source": "local",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    src_prompts = ROOT / "prompts"
    if src_prompts.is_dir():
        for p in src_prompts.glob("*.md"):
            (prompts / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    class _BoomGenerator:
        def complete(self, *, system: str, user: str, temperature: float) -> str:
            raise RuntimeError(f"upstream 400: prompt was {secret}")

    retriever = _FakeRetriever(
        {"q1": ["bofm/alma/32/27"], secret: ["bofm/alma/32/27"], "*": ["noise"]}
    )
    result = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=False,
        include_local=True,
        settings=settings,
        retriever=retriever,
        generators={"mock-a": _BoomGenerator()},  # type: ignore[dict-item]
        skip_preflight=True,
        stem="local-leak",
        compare="none",
    )
    assert result.summary_path is not None
    assert any(i.error and secret in i.error for i in result.items)
    # Markdown is committed; free-text errors must not leak restricted question text.
    assert secret not in result.md_path.read_text(encoding="utf-8")
    raw = result.summary_path.read_text(encoding="utf-8")
    assert secret not in raw
    data = json.loads(raw)
    assert "items" not in data
    assert "first_error" not in json.dumps(data)
    assert set(data) <= SUMMARY_TOP_LEVEL_KEYS
    for agg in data["aggregates"]:
        assert set(agg) <= SUMMARY_AGGREGATE_KEYS
        assert agg.get("error_n", 0) >= 1


def test_run_eval_writes_summary_and_keep_section(tmp_path: Path) -> None:
    settings = _mini_settings(tmp_path)
    # Copy prompts so generation path can load if needed; retrieval-only skips.
    retriever = _FakeRetriever({"q1": ["bofm/alma/32/27"], "q2": ["noise"], "*": ["x"]})
    result = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=True,
        include_local=False,
        settings=settings,
        retriever=retriever,
        stem="sum-md",
        check_baselines=True,
        compare="none",
    )
    assert result.summary_path is not None and result.summary_path.is_file()
    body = result.md_path.read_text(encoding="utf-8")
    assert "## Keep-or-revert" in body
    assert "KEEP" in body or "REVERT" in body
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "mock-a" in summary["baseline_verdicts"]
    assert summary["baselines_checked"]


def test_run_eval_changed_local_golden_is_not_comparable(tmp_path: Path) -> None:
    """Editing golden.local.yaml must not produce a false recall regression."""
    settings = _mini_settings(tmp_path)
    (tmp_path / "eval" / "golden.local.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "questions": [
                    {
                        "id": "local-1",
                        "bucket": "verse_lookup",
                        "question": "local-q-a",
                        "gold_chunk_ids": ["bofm/alma/32/27"],
                        "source": "local",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retriever = _FakeRetriever(
        {
            "q1": ["bofm/alma/32/27"],
            "q2": ["noise"],
            "local-q-a": ["bofm/alma/32/27"],
            "local-q-b": ["noise"],
            "local-q-c": ["noise"],
            "*": ["noise"],
        }
    )
    first = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=True,
        include_local=True,
        settings=settings,
        retriever=retriever,
        stem="loc-a",
        compare="none",
    )
    (tmp_path / "eval" / "golden.local.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "questions": [
                    {
                        "id": "local-2",
                        "bucket": "verse_lookup",
                        "question": "local-q-b",
                        "gold_chunk_ids": ["bofm/alma/32/27"],
                        "source": "local",
                    },
                    {
                        "id": "local-3",
                        "bucket": "verse_lookup",
                        "question": "local-q-c",
                        "gold_chunk_ids": ["bofm/alma/32/27"],
                        "source": "local",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    second = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=True,
        include_local=True,
        settings=settings,
        retriever=retriever,
        stem="loc-b",
        compare=str(first.summary_path),
    )
    assert second.comparison is not None
    assert not second.comparison.comparable
    assert "golden_local_hash" in second.comparison.reason
    body = second.md_path.read_text(encoding="utf-8")
    assert "Not comparable" in body
    assert "regressed" not in body.lower() or "Not comparable" in body


def test_diff_summaries_lost_metric_is_regressed() -> None:
    """A metric that was measurable and becomes None must not read as 'no regression'."""
    from lds_study.eval.compare import render_comparison_section

    prev = _base_summary(
        retrieval_only=False,
        aggregates=[summary_safe_aggregate(_agg(cite=0.95))],
    )
    # Drop generation rates; spike errors — simulates a dead generator.
    broken = summary_safe_aggregate(_agg(cite=0.95))
    broken["citation_validity_rate"] = None
    broken["invalid_marker_rate"] = None
    broken["coverage_fail_rate"] = None
    broken["adversarial_refusal_rate"] = None
    broken["error_n"] = 50
    curr = _base_summary(retrieval_only=False, aggregates=[broken])
    result = diff_summaries(prev, curr, tolerance=0.02)
    assert result.comparable
    assert result.any_regressed
    cite = next(d for d in result.deltas if d.name == "citation_validity")
    assert cite.previous == 0.95 and cite.current is None
    assert cite.regressed
    err = next(d for d in result.deltas if d.name == "error_n")
    assert err.regressed and err.delta == 50.0
    section = render_comparison_section(result)
    assert "no regression beyond tolerance" not in section
    assert "unmeasurable" in section
    assert "lost" in section


def test_diff_summaries_improvement_and_regression() -> None:
    prev = _base_summary(
        recall_shared=0.80, aggregates=[summary_safe_aggregate(_agg(recall=0.80, cite=0.90))]
    )
    better = _base_summary(
        recall_shared=0.90,
        aggregates=[summary_safe_aggregate(_agg(recall=0.90, cite=0.95))],
    )
    improved = diff_summaries(prev, better, tolerance=0.02)
    assert improved.comparable
    recall_d = next(d for d in improved.deltas if d.name == "recall@k")
    assert recall_d.improved and not recall_d.regressed

    worse = _base_summary(
        recall_shared=0.70,
        aggregates=[summary_safe_aggregate(_agg(recall=0.70, cite=0.80))],
    )
    regressed = diff_summaries(prev, worse, tolerance=0.02)
    recall_r = next(d for d in regressed.deltas if d.name == "recall@k")
    assert recall_r.regressed
    cite_r = next(d for d in regressed.deltas if d.name == "citation_validity")
    assert cite_r.regressed


def test_diff_summaries_sub_tolerance_not_flagged() -> None:
    prev = _base_summary(
        retrieval_only=False,
        recall_shared=0.80,
        aggregates=[summary_safe_aggregate(_agg(cite=0.90))],
    )
    curr = _base_summary(
        retrieval_only=False,
        recall_shared=0.80,
        aggregates=[summary_safe_aggregate(_agg(cite=0.885))],  # -0.015 < 0.02
    )
    result = diff_summaries(prev, curr, tolerance=0.02)
    cite = next(d for d in result.deltas if d.name == "citation_validity")
    assert cite.delta is not None and cite.delta < 0
    assert not cite.regressed


def test_diff_summaries_not_comparable_per_guarded_field() -> None:
    prev = _base_summary()
    for field, value in [
        ("golden_hash", "other"),
        ("golden_local_hash", "other-local"),
        ("k", 4),
        ("profile", "other"),
        ("include_local", True),
        ("retrieval_only", True),
        ("buckets", ["adversarial"]),
        ("limit", 3),
        ("models", ["other-model"]),
        ("source_counts", {"golden": 1, "local": 9}),
    ]:
        curr = _base_summary(**{field: value})
        result = diff_summaries(prev, curr, tolerance=0.02)
        assert not result.comparable, field
        assert field in result.reason


def test_diff_summaries_model_order_normalized() -> None:
    """Same model set in different order remains comparable; metrics keyed by name."""
    a = summary_safe_aggregate(_agg(model="a", cite=0.9))
    b = summary_safe_aggregate(_agg(model="b", cite=0.8))
    prev = _base_summary(models=["a", "b"], aggregates=[a, b])
    curr = _base_summary(models=["b", "a"], aggregates=[b, a])
    result = diff_summaries(prev, curr, tolerance=0.02)
    assert result.comparable
    cite_a = next(
        d for d in result.deltas if d.name == "citation_validity" and d.model == "a"
    )
    assert cite_a.delta == 0.0


def test_diff_retrieval_only_uses_zero_tolerance() -> None:
    prev = _base_summary(
        retrieval_only=True,
        recall_shared=0.80,
        aggregates=[summary_safe_aggregate(_agg())],
    )
    curr = _base_summary(
        retrieval_only=True,
        recall_shared=0.79,
        aggregates=[summary_safe_aggregate(_agg())],
    )
    result = diff_summaries(prev, curr, tolerance=0.02)
    recall = next(d for d in result.deltas if d.name == "recall@k")
    assert recall.regressed  # any drop flags under tol=0
    assert len(result.deltas) == 1  # generation metrics skipped


def test_summary_aggregate_keys_cover_compare_metrics() -> None:
    from lds_study.eval import compare as compare_mod

    assert compare_mod._COMPARE_REQUIRED_AGGREGATE_KEYS <= SUMMARY_AGGREGATE_KEYS

def test_compare_auto_prefers_tracked_over_untracked(tmp_path: Path) -> None:
    """Untracked summaries are skipped while a tracked one is chosen (by generated_at)."""
    repo = tmp_path / "repo"
    out = repo / "outputs" / "eval"
    out.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    older = _base_summary(generated_at="2026-01-01T00:00:00+00:00")
    newer = _base_summary(generated_at="2026-07-22T12:00:00+00:00")
    # Lexicographically last name, but older timestamp — must NOT win.
    tracked_old = out / "verify-z.summary.json"
    tracked_old.write_text(json.dumps(older), encoding="utf-8")
    tracked_new = out / "2026-07-22.summary.json"
    tracked_new.write_text(json.dumps(newer), encoding="utf-8")
    untracked = out / "zz-local.summary.json"
    untracked.write_text(
        json.dumps(_base_summary(generated_at="2099-01-01T00:00:00+00:00")),
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "outputs/eval/verify-z.summary.json"], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "add", "outputs/eval/2026-07-22.summary.json"], cwd=str(repo), check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "track summaries"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    path, reason = resolve_compare_reference(
        compare="auto",
        repo_root=repo,
        eval_cfg={},
        exclude=None,
        outputs_eval_dir=out,
    )
    assert path == tracked_new.resolve()
    assert "2026-07-22" in reason
    assert "generated_at=" in reason
    assert untracked.is_file()


def test_compare_explicit_missing_raises(tmp_path: Path) -> None:
    out = tmp_path / "outputs" / "eval"
    out.mkdir(parents=True)
    try:
        resolve_compare_reference(
            compare="does-not-exist",
            repo_root=tmp_path,
            eval_cfg={},
            outputs_eval_dir=out,
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not found" in str(exc)


def test_compare_rejects_full_sidecar_filename(tmp_path: Path) -> None:
    """Explicit --compare must not resolve a restricted *.json sidecar by path."""
    from lds_study.eval.compare import load_summary

    out = tmp_path / "outputs" / "eval"
    out.mkdir(parents=True)
    sidecar = out / "run.json"
    sidecar.write_text(
        json.dumps({**_base_summary(), "items": [{"question": "secret"}]}),
        encoding="utf-8",
    )
    try:
        resolve_compare_reference(
            compare=str(sidecar),
            repo_root=tmp_path,
            eval_cfg={},
            outputs_eval_dir=out,
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not found" in str(exc)

    try:
        load_summary(sidecar)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "items" in str(exc)


def test_load_summary_rejects_unknown_schema_version(tmp_path: Path) -> None:
    from lds_study.eval.compare import load_summary

    path = tmp_path / "future.summary.json"
    path.write_text(json.dumps(_base_summary(schema_version=99)), encoding="utf-8")
    try:
        load_summary(path)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "schema_version" in str(exc)


def test_compare_explicit_and_reference_report(tmp_path: Path) -> None:
    out = tmp_path / "outputs" / "eval"
    out.mkdir(parents=True)
    blessed = out / "blessed.summary.json"
    blessed.write_text(json.dumps(_base_summary()), encoding="utf-8")
    path, reason = resolve_compare_reference(
        compare="auto",
        repo_root=tmp_path,
        eval_cfg={"reference_report": "blessed"},
        outputs_eval_dir=out,
    )
    assert path == blessed.resolve()
    assert "reference_report" in reason

    path2, _ = resolve_compare_reference(
        compare=str(blessed),
        repo_root=tmp_path,
        eval_cfg={},
        outputs_eval_dir=out,
    )
    assert path2 == blessed.resolve()


def test_run_eval_compare_embeds_section(tmp_path: Path) -> None:
    settings = _mini_settings(tmp_path)
    retriever = _FakeRetriever({"q1": ["bofm/alma/32/27"], "q2": ["noise"], "*": ["x"]})
    first = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=True,
        include_local=False,
        settings=settings,
        retriever=retriever,
        stem="cmp-a",
        compare="none",
    )
    assert first.summary_path is not None
    second = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=True,
        include_local=False,
        settings=settings,
        retriever=retriever,
        stem="cmp-b",
        compare=str(first.summary_path),
    )
    body = second.md_path.read_text(encoding="utf-8")
    assert "## Trend vs previous" in body
    assert second.comparison is not None
    assert second.comparison.comparable
    # Distinctive fixture value proves eval.trend_tolerance was read (not defaulted).
    assert second.comparison.tolerance == 0.25
    # Committed report must stay repo-relative (no OS username / abs temp paths).
    assert "Users" not in body
    assert "AppData" not in body
    assert "C:" not in body
    assert "outputs/eval/cmp-a.summary.json" in body
    assert "compare=outputs/eval/cmp-a.summary.json" in body


def test_run_eval_bad_compare_fails_before_retrieval(tmp_path: Path) -> None:
    """Explicit missing --compare must fail fast — no report artifacts written."""
    settings = _mini_settings(tmp_path)
    calls = {"n": 0}

    class _CountingRetriever(_FakeRetriever):
        def retrieve(self, query: str, *, filters=None, top_k=None):  # noqa: ANN001
            calls["n"] += 1
            return super().retrieve(query, filters=filters, top_k=top_k)

    retriever = _CountingRetriever({"q1": ["bofm/alma/32/27"], "q2": ["noise"], "*": ["x"]})
    try:
        run_eval(
            profile="default",
            models=["mock-a"],
            retrieval_only=True,
            include_local=False,
            settings=settings,
            retriever=retriever,
            stem="should-not-exist",
            compare="2026-07-21-r2",
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not found" in str(exc)
    assert calls["n"] == 0
    out = tmp_path / "outputs" / "eval"
    if out.exists():
        assert not list(out.glob("should-not-exist*"))


def test_run_eval_corrupt_reference_keeps_paths_relative(tmp_path: Path) -> None:
    """Soft compare failure must not embed absolute machine paths in the report."""
    settings = _mini_settings(tmp_path)
    out = tmp_path / "outputs" / "eval"
    out.mkdir(parents=True)
    bad = out / "bad.summary.json"
    bad.write_text('["not","an","object"]\n', encoding="utf-8")
    retriever = _FakeRetriever({"q1": ["bofm/alma/32/27"], "q2": ["noise"], "*": ["x"]})
    result = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=True,
        include_local=False,
        settings=settings,
        retriever=retriever,
        stem="corrupt-ref",
        compare=str(bad),
    )
    body = result.md_path.read_text(encoding="utf-8")
    assert "## Trend vs previous" in body
    assert "compare failed" in body
    assert "Users" not in body
    assert "AppData" not in body
    assert "C:" not in body
    assert "bad.summary.json" in body


def test_run_eval_compare_none_still_records_section(tmp_path: Path) -> None:
    settings = _mini_settings(tmp_path)
    retriever = _FakeRetriever({"q1": ["bofm/alma/32/27"], "q2": ["noise"], "*": ["x"]})
    result = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=True,
        include_local=False,
        settings=settings,
        retriever=retriever,
        stem="no-cmp",
        compare="none",
    )
    body = result.md_path.read_text(encoding="utf-8")
    assert "## Trend vs previous" in body
    assert "No comparison" in body
    assert "compare=none" in body
    assert "## Keep-or-revert" in body
    assert "Gate not run" in body


def test_run_eval_generation_compare_round_trips_citation_delta(tmp_path: Path) -> None:
    """Two real generation summaries must yield a non-n/a citation_validity delta."""
    settings = _mini_settings(tmp_path)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    src_prompts = ROOT / "prompts"
    if src_prompts.is_dir():
        for p in src_prompts.glob("*.md"):
            (prompts / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    retriever = _FakeRetriever({"q1": ["bofm/alma/32/27"], "q2": ["noise"], "*": ["x"]})

    def _gen(replies: list[str]) -> ScriptedGenerator:
        return ScriptedGenerator(replies=list(replies))

    first = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=False,
        include_local=False,
        settings=settings,
        retriever=retriever,
        generators={
            "mock-a": _gen(
                [
                    "Answer [[bofm/alma/32/27]].",
                    "I don't have enough evidence in the provided sources.",
                ]
            )
        },
        skip_preflight=True,
        stem="gen-a",
        compare="none",
    )
    second = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=False,
        include_local=False,
        settings=settings,
        retriever=retriever,
        generators={
            "mock-a": _gen(
                [
                    "Answer [[bofm/alma/32/27]].",
                    "I don't have enough evidence in the provided sources.",
                ]
            )
        },
        skip_preflight=True,
        stem="gen-b",
        compare=str(first.summary_path),
    )
    assert second.comparison is not None and second.comparison.comparable
    cite = next(
        d
        for d in second.comparison.deltas
        if d.name == "citation_validity" and d.model == "mock-a"
    )
    assert cite.previous is not None and cite.current is not None
    assert cite.delta is not None
    body = second.md_path.read_text(encoding="utf-8")
    assert "citation_validity" in body
    assert "Users\\" not in body and "AppData" not in body


def test_allowlist_allows_summary_rejects_full_json() -> None:
    ok = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--paths",
            "outputs/eval/2026-07-21-r2.summary.json",
            "outputs/eval/2026-07-21-r2.md",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr

    bad = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--paths",
            "outputs/eval/2026-07-21-r2.json",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert bad.returncode == 1


def test_run_eval_scripted_keep_verdicts_in_summary(tmp_path: Path) -> None:
    settings = _mini_settings(tmp_path)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    src_prompts = ROOT / "prompts"
    if src_prompts.is_dir():
        for p in src_prompts.glob("*.md"):
            (prompts / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    retriever = _FakeRetriever({"q1": ["bofm/alma/32/27"], "q2": ["noise"], "*": ["x"]})
    gen = ScriptedGenerator(
        replies=[
            "Answer [[bofm/alma/32/27]].",
            "I don't have enough evidence in the provided sources.",
        ]
    )
    result = run_eval(
        profile="default",
        models=["mock-a"],
        retrieval_only=False,
        include_local=False,
        settings=settings,
        retriever=retriever,
        generators={"mock-a": gen},
        skip_preflight=True,
        stem="gen-sum",
        check_baselines=True,
        compare="none",
    )
    assert result.summary_path is not None
    data = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert data["baseline_verdicts"]["mock-a"]["keep"] in (True, False)
    assert "items" not in data


def test_cli_eval_compare_keep_exit_and_console_encoding(tmp_path: Path, monkeypatch) -> None:
    """Drive the typer CLI: --compare marshalling, KEEP exit 0, cp1252-safe console."""
    import io
    from pathlib import Path as P
    from unittest.mock import MagicMock

    from rich.console import Console
    from typer.testing import CliRunner

    from lds_study.cli import app
    from lds_study.eval.compare import MetricDelta, ComparisonResult, render_comparison_console
    from lds_study.eval.metrics import AggregateMetrics

    # Avoid N:N fragments that ReprHighlighter would style mid-token.
    model_id = "qwen2.5-7b-instruct"
    captured: dict = {}

    def fake_run_eval(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        agg = AggregateMetrics(
            model=model_id,
            n_items=2,
            recall_at_k=0.9,
            recall_n=1,
            citation_validity_rate=0.95,
            citation_n=1,
            adversarial_refusal_rate=0.9,
            adversarial_n=1,
        )
        return MagicMock(
            md_path=P("outputs/eval/cli.md"),
            json_path=P("outputs/eval/cli.json"),
            summary_path=P("outputs/eval/cli.summary.json"),
            compare_reason="explicit --compare outputs/eval/a.summary.json",
            comparison=ComparisonResult(
                comparable=True,
                reason="ok",
                deltas=[
                    MetricDelta(
                        name="citation_validity",
                        previous=0.95,
                        current=0.94,
                        delta=-0.01,
                        higher_is_better=True,
                        regressed=False,
                        improved=False,
                        model=model_id,
                    )
                ],
                tolerance=0.02,
            ),
            aggregates=[agg],
            suggested_baselines={},
            baseline_verdicts={model_id: (True, [])},
        )

    monkeypatch.setattr("lds_study.eval.run.run_eval", fake_run_eval)
    # Exercise the shipped module console (do not replace it).

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["eval", "--compare", "outputs/eval/a.summary.json", "--no-local"],
    )
    assert result.exit_code == 0, result.output
    assert captured.get("compare") == "outputs/eval/a.summary.json"
    assert model_id in result.output
    assert "->" in result.output or "citation_validity" in result.output

    # Console lines must survive a cp1252 stream (Windows redirect = not a TTY).
    ok_lines = render_comparison_console(
        ComparisonResult(
            comparable=True,
            reason="ok",
            deltas=[
                MetricDelta(
                    name="citation_validity",
                    previous=0.95,
                    current=0.70,
                    delta=-0.25,
                    higher_is_better=True,
                    regressed=True,
                    improved=False,
                    model=model_id,
                )
            ],
            tolerance=0.02,
        )
    )
    bad_lines = render_comparison_console(
        ComparisonResult(
            comparable=False,
            reason="not comparable -- run shape differs: buckets: previous=None current=('adversarial',)",
            mismatches=["buckets"],
            tolerance=0.02,
        )
    )
    for line in ok_lines + bad_lines:
        assert all(ord(c) < 128 for c in line), line

    bio = io.BytesIO()
    buf = io.TextIOWrapper(bio, encoding="cp1252", errors="strict")
    c = Console(file=buf, force_terminal=False, legacy_windows=False)
    for line in ok_lines + bad_lines:
        c.print(line, markup=False)
    buf.flush()
    text = bio.getvalue().decode("cp1252")
    assert model_id in text
    assert "->" in text
    assert "REGRESSED" in text
    assert "not comparable -- run shape differs" in text
    assert "not comparable -- not comparable" not in text


def test_cli_eval_revert_exits_1(monkeypatch) -> None:
    from pathlib import Path as P
    from unittest.mock import MagicMock

    from typer.testing import CliRunner

    from lds_study.cli import app
    from lds_study.eval.metrics import AggregateMetrics

    def fake_run_eval(**kwargs):  # noqa: ANN003
        agg = AggregateMetrics(
            model="m",
            n_items=1,
            recall_at_k=0.1,
            recall_n=1,
            citation_validity_rate=0.1,
            citation_n=1,
            adversarial_refusal_rate=0.1,
            adversarial_n=1,
        )
        return MagicMock(
            md_path=P("outputs/eval/x.md"),
            json_path=P("outputs/eval/x.json"),
            summary_path=P("outputs/eval/x.summary.json"),
            compare_reason="compare=none",
            comparison=None,
            aggregates=[agg],
            suggested_baselines={},
            baseline_verdicts={"m": (False, ["citation_validity 0.1 < 0.9"])},
        )

    monkeypatch.setattr("lds_study.eval.run.run_eval", fake_run_eval)
    runner = CliRunner()
    result = runner.invoke(app, ["eval", "--compare", "none", "--check-baselines"])
    assert result.exit_code == 1
    assert "REVERT" in result.output
