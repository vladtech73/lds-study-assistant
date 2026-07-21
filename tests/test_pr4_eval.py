"""PR4 — golden eval harness (offline; mock retriever + ScriptedGenerator)."""

from __future__ import annotations

from pathlib import Path

import yaml

from lds_study.config import Settings
from lds_study.data.models import Chunk
from lds_study.eval.golden import BUCKETS, load_golden_set
from lds_study.eval.metrics import aggregate, recall_at_k, suggested_baselines
from lds_study.eval.report import render_comparison_table
from lds_study.eval.run import run_eval
from lds_study.index.base import RetrievalResult, RetrievedHit
from lds_study.rag.generate import ScriptedGenerator

ROOT = Path(__file__).resolve().parents[1]


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


def test_committed_golden_has_four_buckets_and_about_fifty() -> None:
    questions = load_golden_set(ROOT, include_local=False)
    assert len(questions) >= 45
    assert len(questions) <= 60
    by_bucket = {b: 0 for b in BUCKETS}
    for q in questions:
        by_bucket[q.bucket] += 1
    for b in BUCKETS:
        assert by_bucket[b] >= 8, b
    # Scripture-only: every gold id looks like volume/book/...
    for q in questions:
        for cid in q.gold_chunk_ids:
            assert "/" in cid
            assert not cid.startswith("http")


def test_recall_at_k_ranks() -> None:
    hit, rank = recall_at_k(["a", "b", "c"], ["c"], k=3)
    assert hit is True and rank == 3
    hit, rank = recall_at_k(["a", "b"], ["z"], k=2)
    assert hit is False and rank is None
    hit, rank = recall_at_k(["a", "b", "c"], ["c"], k=2)
    assert hit is False


def test_run_eval_retrieval_only_writes_report(tmp_path: Path) -> None:
    # Tiny private golden beside a fake root.
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
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
    settings = Settings(
        root=tmp_path,
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "indexes",
        models_dir=tmp_path / "models",
        outputs_dir=tmp_path / "outputs",
    )
    # Copy minimal configs needed by run_eval.
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "models.yaml").write_text(
        "generator:\n  id: mock-a\nshortlist:\n  - mock-a\n  - mock-b\n",
        encoding="utf-8",
    )
    (cfg / "rag.yaml").write_text(
        "retrieval:\n  final_top_k: 8\neval:\n  recall_k: 8\n",
        encoding="utf-8",
    )

    retriever = _FakeRetriever(
        {
            "q1": ["bofm/alma/32/27", "other"],
            "q2": ["noise"],
            "*": ["noise"],
        }
    )
    result = run_eval(
        profile="default",
        models=["mock-a", "mock-b"],
        retrieval_only=True,
        include_local=False,
        settings=settings,
        retriever=retriever,
        stem="unit-test",
    )
    assert result.md_path.is_file()
    body = result.md_path.read_text(encoding="utf-8")
    assert "Retrieval quality" in body
    assert "mock-a" in body and "mock-b" in body
    assert len(result.items) == 4  # 2 questions × 2 models
    assert result.items[0].top1_score is not None
    agg_a = next(a for a in result.aggregates if a.model == "mock-a")
    assert agg_a.recall_at_k == 1.0
    assert agg_a.recall_n == 1


def test_run_eval_with_scripted_generator_citation_and_refuse(tmp_path: Path) -> None:
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "golden.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "questions": [
                    {
                        "id": "ok-1",
                        "bucket": "doctrinal_synthesis",
                        "question": "faith q",
                        "gold_chunk_ids": ["bofm/alma/32/27"],
                    },
                    {
                        "id": "adv-1",
                        "bucket": "adversarial",
                        "question": "out of corpus",
                        "expect_refuse": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        root=tmp_path,
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "indexes",
        models_dir=tmp_path / "models",
        outputs_dir=tmp_path / "outputs",
    )
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "models.yaml").write_text("generator:\n  id: scripted\n", encoding="utf-8")
    (cfg / "rag.yaml").write_text(
        (ROOT / "configs" / "rag.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    for name in ("study_assistant.md", "lesson_assistant.md", "talk_assistant.md"):
        src = ROOT / "prompts" / name
        (prompts / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    retriever = _FakeRetriever(
        {
            "faith q": ["bofm/alma/32/27"],
            "out of corpus": [],  # no_evidence path
            "*": ["bofm/alma/32/27"],
        }
    )
    # First question needs a cited answer; second never generates (empty retrieval).
    gen = ScriptedGenerator(
        replies=[
            "Faith grows as we experiment [[bofm/alma/32/27]].",
        ]
    )
    result = run_eval(
        profile="default",
        models=["scripted"],
        retrieval_only=False,
        include_local=False,
        settings=settings,
        retriever=retriever,
        generators={"scripted": gen},
        stem="unit-gen",
    )
    by_id = {(r.question_id, r.model): r for r in result.items}
    assert by_id[("ok-1", "scripted")].citation_valid is True
    assert by_id[("ok-1", "scripted")].recall_hit is True
    assert by_id[("adv-1", "scripted")].status == "no_evidence"
    assert by_id[("adv-1", "scripted")].refusal_correct is True


def test_suggested_baselines_and_table() -> None:
    from lds_study.eval.metrics import AggregateMetrics

    aggs = [
        AggregateMetrics(
            model="a",
            n_items=10,
            recall_at_k=1.0,
            recall_n=8,
            citation_validity_rate=0.9,
            citation_n=8,
            adversarial_refusal_rate=1.0,
            adversarial_n=2,
        ),
        AggregateMetrics(
            model="b",
            n_items=10,
            recall_at_k=0.8,
            recall_n=8,
            citation_validity_rate=0.7,
            citation_n=8,
            adversarial_refusal_rate=0.333,
            adversarial_n=2,
        ),
    ]
    floors = suggested_baselines(aggs)
    assert floors["min_recall_at_k"] == 0.9
    assert floors["min_citation_validity"] == 0.81
    # No max(0.5) clamp — 90% of best refusal (1.0) = 0.9
    assert floors["min_adversarial_refusal"] == 0.9
    # Low-performing-only set must not invent a 0.5 floor
    low = suggested_baselines(
        [
            AggregateMetrics(
                model="weak",
                n_items=12,
                recall_at_k=0.789,
                recall_n=38,
                citation_validity_rate=0.71,
                citation_n=38,
                adversarial_refusal_rate=0.333,
                adversarial_n=12,
            )
        ]
    )
    assert low["min_adversarial_refusal"] == 0.3
    table = render_comparison_table(aggs)
    assert "`a`" in table and "`b`" in table
    assert "Cite validity" in table
    empty = aggregate([], model="x")
    assert empty.n_items == 0
    assert empty.recall_at_k is None


def test_citation_validity_excludes_adversarial_refusals(tmp_path: Path) -> None:
    """Correct adversarial refuse must not count as a citation failure."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "golden.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "questions": [
                    {
                        "id": "ok-1",
                        "bucket": "doctrinal_synthesis",
                        "question": "faith q",
                        "gold_chunk_ids": ["bofm/alma/32/27"],
                    },
                    {
                        "id": "adv-1",
                        "bucket": "adversarial",
                        "question": "out of corpus",
                        "expect_refuse": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        root=tmp_path,
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "indexes",
        models_dir=tmp_path / "models",
        outputs_dir=tmp_path / "outputs",
    )
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "models.yaml").write_text("generator:\n  id: scripted\n", encoding="utf-8")
    (cfg / "rag.yaml").write_text(
        (ROOT / "configs" / "rag.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    for name in ("study_assistant.md", "lesson_assistant.md", "talk_assistant.md"):
        src = ROOT / "prompts" / name
        (prompts / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    retriever = _FakeRetriever(
        {
            "faith q": ["bofm/alma/32/27"],
            "out of corpus": [],
        }
    )
    gen = ScriptedGenerator(
        replies=["Faith grows as we experiment [[bofm/alma/32/27]]."]
    )
    result = run_eval(
        profile="default",
        models=["scripted"],
        include_local=False,
        settings=settings,
        retriever=retriever,
        generators={"scripted": gen},
        stem="cite-scope",
    )
    agg = result.aggregates[0]
    assert agg.citation_n == 1  # adversarial excluded
    assert agg.citation_validity_rate == 1.0
    assert agg.adversarial_refusal_rate == 1.0
    by_id = {(r.question_id, r.model): r for r in result.items}
    assert by_id[("adv-1", "scripted")].citation_valid is None
    assert by_id[("adv-1", "scripted")].top1_score is None  # empty retrieval
    assert "include_local=False" in result.md_path.read_text(encoding="utf-8")
