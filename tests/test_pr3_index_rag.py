"""PR3 — index + RAG unit tests (offline; HashEmbedder + ScriptedGenerator)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lds_study.config import Settings
from lds_study.data.chunk_scripture import chunk_scripture_records
from lds_study.data.models import Chunk
from lds_study.index.chroma_store import ChromaDenseStore
from lds_study.index.base import RetrievalResult, RetrievedHit
from lds_study.index.bm25_index import BM25Index
from lds_study.index.build import run_index
from lds_study.index.chunks_io import chunks_by_id
from lds_study.index.embedder import HashEmbedder
from lds_study.index.expand import expand_context
from lds_study.index.hybrid import HybridRetriever, reciprocal_rank_fusion
from lds_study.index.rerank import IdentityReranker
from lds_study.index.smoke import load_phrase_fixtures, run_phrase_smoke
from lds_study.rag.ask import EXIT_NO_EVIDENCE, EXIT_OK, EXIT_UNSUPPORTED, run_ask
from lds_study.rag.citations import CitationConfig, passes_citation_gate, validate_citations
from lds_study.rag.generate import ScriptedGenerator

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _scripture_chunks() -> list[Chunk]:
    records: list[dict] = []
    records.extend(json.loads((FIXTURES / "scripture" / "alma_32.json").read_text(encoding="utf-8")))
    for item in json.loads((FIXTURES / "scripture" / "known_verses.json").read_text(encoding="utf-8")):
        records.append({k: v for k, v in item.items() if k != "expected_text"})
    chunks, _empty = chunk_scripture_records(
        records, source_id="fixture", redistributable=True
    )
    # known_verses overlaps Alma 32 — keep unique ids for index tests.
    by_id = {c.id: c for c in chunks}
    return list(by_id.values())


def test_rrf_prefers_shared_high_ranks() -> None:
    dense = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    bm25 = [("b", 12.0), ("a", 11.0), ("d", 10.0)]
    fused = reciprocal_rank_fusion([dense, bm25], k=60)
    assert fused[0][0] in {"a", "b"}
    ids = [cid for cid, _ in fused]
    assert ids.index("b") < ids.index("c")


def test_expand_context_neighbors() -> None:
    chunks = {
        "bofm/alma/32/26": Chunk(
            id="bofm/alma/32/26",
            text="v26",
            source_id="s",
            source_type="scripture",
            redistributable=True,
            volume="bofm",
            book="alma",
            chapter=32,
            verse=26,
        ),
        "bofm/alma/32/27": Chunk(
            id="bofm/alma/32/27",
            text="v27",
            source_id="s",
            source_type="scripture",
            redistributable=True,
            volume="bofm",
            book="alma",
            chapter=32,
            verse=27,
        ),
        "bofm/alma/32/28": Chunk(
            id="bofm/alma/32/28",
            text="v28",
            source_id="s",
            source_type="scripture",
            redistributable=True,
            volume="bofm",
            book="alma",
            chapter=32,
            verse=28,
        ),
    }
    hits = [RetrievedHit(chunk=chunks["bofm/alma/32/27"], score=1.0, source="hybrid")]
    out = expand_context(hits, chunks, neighbor_window=1)
    ids = [h.chunk.id for h in out]
    assert ids[0] == "bofm/alma/32/27"
    assert "bofm/alma/32/26" in ids
    assert "bofm/alma/32/28" in ids


def test_bm25_phrase_smoke_harness_wiring() -> None:
    """Fixture-scale BM25 wiring proof — not the plan's full-corpus 10/10 gate."""
    chunks = _scripture_chunks()
    bm25 = BM25Index.build(chunks)
    phrases = load_phrase_fixtures(ROOT)
    assert len(phrases) == 10
    for item in phrases:
        ranked = bm25.query(item["phrase"], top_k=1)
        assert ranked, f"no BM25 hit for {item['phrase']!r}"
        assert ranked[0][0] == item["chunk_id"], item["phrase"]


def test_dense_only_retrieve_returns_hash_neighbor(tmp_path: Path) -> None:
    """Dense path must contribute hits when BM25 is empty (regression for finding 1)."""
    chunks = _scripture_chunks()
    # Seed Chroma with hash vectors for a distinctive Alma verse + distractors.
    target = next(c for c in chunks if c.id == "bofm/alma/32/27")
    others = [c for c in chunks if c.id != target.id][:20]
    store = ChromaDenseStore(tmp_path / "chroma")
    embedder = HashEmbedder(dim=32)
    batch = [target, *others]
    store.upsert(batch, embedder.embed([c.text for c in batch]))

    class EmptyBM25:
        def query(self, text, *, top_k, allowed_ids=None):
            return []

    retriever = HybridRetriever(
        dense=store,
        bm25=EmptyBM25(),  # type: ignore[arg-type]
        embedder=embedder,
        chunks_by_id=chunks_by_id(batch),
        reranker=IdentityReranker(),
        dense_top_k=10,
        bm25_top_k=10,
        final_top_k=1,
        neighbor_window=0,
    )
    got = retriever.retrieve(target.text, top_k=1)
    assert got.hits
    assert got.hits[0].chunk.id == "bofm/alma/32/27"


def test_index_build_hash_embedder_and_hybrid_retrieve(tmp_path: Path) -> None:
    chunks = _scripture_chunks()
    chunks_path = tmp_path / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.to_json()) + "\n")

    settings = Settings(root=ROOT, index_dir=tmp_path / "indexes")
    result = run_index(
        profile="test",
        rebuild=True,
        smoke=False,
        settings=settings,
        embedder=HashEmbedder(dim=32),
        chunks_path=chunks_path,
        batch_size=16,
    )
    assert result.chunk_count == len(chunks)

    store = ChromaDenseStore(result.profile_dir / "chroma")
    bm25 = BM25Index.load(result.profile_dir / "bm25.pkl")
    retriever = HybridRetriever(
        dense=store,
        bm25=bm25,
        embedder=HashEmbedder(dim=32),
        chunks_by_id=chunks_by_id(chunks),
        reranker=IdentityReranker(),
        dense_top_k=20,
        bm25_top_k=20,
        final_top_k=3,
        neighbor_window=0,
    )
    # Exact distinctive phrase should surface via BM25 even with hash dense vectors.
    got = retriever.retrieve("experiment upon my words", top_k=1)
    assert got.hits
    assert got.hits[0].chunk.id == "bofm/alma/32/27"


def test_citation_ok_and_render() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )
    answer = "Try an experiment upon the word. [[bofm/alma/32/27]]"
    report = validate_citations(
        answer, {"bofm/alma/32/27"}, {"bofm/alma/32/27": chunk}
    )
    assert passes_citation_gate(report, CitationConfig())
    assert "Alma 32:27" in report.rendered
    assert "[[bofm/alma/32/27]]" not in report.rendered


def test_citation_invalid_marker_not_stripped() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="x",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )
    answer = "Claim. [[bofm/alma/32/99]]"
    report = validate_citations(
        answer, {"bofm/alma/32/27"}, {"bofm/alma/32/27": chunk}
    )
    assert report.invalid == ["bofm/alma/32/99"]
    assert "[[bofm/alma/32/99]]" in report.rendered
    assert not passes_citation_gate(report, CitationConfig())


def test_ask_ok_path() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment upon my words",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(
        replies=["Desire to believe and experiment upon the word. [[bofm/alma/32/27]]"]
    )
    result = run_ask(
        "What did Alma teach about experimenting?",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "ok"
    assert result.exit_code == EXIT_OK
    assert result.attempts == 1


def test_ask_stdout_keeps_lowercase_chunk_id_citation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Citations that fall back to lowercase chunk ids must survive terminal output."""
    import lds_study.rag.ask as ask_mod
    from rich.console import Console

    recorded = Console(record=True, force_terminal=True, width=120)
    monkeypatch.setattr(ask_mod, "console", recorded)

    chunk = Chunk(
        id="user/talk-oct2023-03/s2",
        text="think celestial",
        source_id="user-byof",
        source_type="talk",
        redistributable=False,
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(
        replies=["The speaker invites us to think celestial. [[user/talk-oct2023-03/s2]]"]
    )
    result = run_ask(
        "What did the talk invite?",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=False,
    )
    assert result.status == "ok"
    assert "user/talk-oct2023-03/s2" in (result.rendered or "")
    text = recorded.export_text()
    assert "user/talk-oct2023-03/s2" in text
    assert "think celestial" in text


def test_ask_honest_refusal_is_no_evidence() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(
        replies=["I do not find this in the indexed sources."]
    )
    result = run_ask(
        "what did the prophet say last Tuesday",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "no_evidence"
    assert result.exit_code == EXIT_NO_EVIDENCE
    assert result.attempts == 1
    assert result.answer is None
    assert result.rendered is not None
    assert "I don't find this in the indexed sources." in result.rendered
    assert "id: bofm/alma/32/27" in result.rendered
    assert gen.replies == []  # no retry burn


def test_ask_hedge_refusal_is_unsupported() -> None:
    """Uncited prose that merely *contains* the refusal phrase must not be echoed."""
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    hedge = (
        "President Nelson taught in October 2023 that covenant keeping brings power. "
        "He also promised specific blessings to temple attenders.\n\n"
        "I do not find this in the indexed sources, but the above summary reflects the talk."
    )
    gen = ScriptedGenerator(replies=[hedge, hedge])
    result = run_ask(
        "what did President Nelson teach last conference",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "unsupported"
    assert result.exit_code == EXIT_UNSUPPORTED
    assert result.answer is None
    assert result.rendered is not None
    assert "President Nelson taught" not in result.rendered
    assert "Retrieved sources:" in result.rendered


def test_prompt_refusal_matches_detector() -> None:
    """Bind each prompt's refusal instruction to the detector (not hardcoded literals)."""
    import re

    from lds_study.rag.citations import looks_like_honest_refusal
    from lds_study.rag.prompts import MODE_FILES, load_system_prompt

    for mode in MODE_FILES:
        prompt = load_system_prompt(mode, root=ROOT)
        refusal = _extract_prompt_refusal_clause(prompt)
        # Model answers in first person; prompts say "say you …".
        spoken = re.sub(r"(?i)^you\s+", "I ", refusal).rstrip(".") + "."
        assert looks_like_honest_refusal(spoken), f"{mode}: {spoken!r}"
        assert not looks_like_honest_refusal(
            "Here is a claim about Nelson.\n\n"
            f"{spoken} but the above summary reflects the talk."
        ), mode


def _extract_prompt_refusal_clause(prompt: str) -> str:
    for line in prompt.splitlines():
        if "indexed sources" not in line.lower():
            continue
        lower = line.lower()
        if "say " not in lower:
            continue
        start = lower.index("say ") + len("say ")
        clause = line[start:].strip()
        # Trim trailing sentences after the refusal clause.
        if ". " in clause:
            clause = clause.split(". ", 1)[0].strip()
        return clause.rstrip(".")
    raise AssertionError("prompt has no 'say … indexed sources' refusal instruction")


def test_ask_orphan_expand_neighbor_excluded_at_raised_min_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neighbors of below-threshold seeds must not remain citable."""
    strong = Chunk(
        id="bofm/alma/1/5",
        text="strong seed",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        volume="bofm",
        book="alma",
        chapter=1,
        verse=5,
        canonical_ref="Alma 1:5",
    )
    strong_n = Chunk(
        id="bofm/alma/1/6",
        text="strong neighbor",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        volume="bofm",
        book="alma",
        chapter=1,
        verse=6,
        canonical_ref="Alma 1:6",
    )
    weak = Chunk(
        id="bofm/mosiah/1/9",
        text="weak seed",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        volume="bofm",
        book="mosiah",
        chapter=1,
        verse=9,
        canonical_ref="Mosiah 1:9",
    )
    orphan = Chunk(
        id="bofm/mosiah/1/10",
        text="orphan neighbor",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        volume="bofm",
        book="mosiah",
        chapter=1,
        verse=10,
        canonical_ref="Mosiah 1:10",
    )

    class StubRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[
                    RetrievedHit(chunk=strong, score=1.0, source="hybrid"),
                    RetrievedHit(
                        chunk=strong_n, score=0.5, source="expand", seed_id=strong.id
                    ),
                    RetrievedHit(chunk=weak, score=0.3, source="hybrid"),
                    RetrievedHit(
                        chunk=orphan, score=0.15, source="expand", seed_id=weak.id
                    ),
                ]
            )

    class CapturingGen:
        def __init__(self) -> None:
            self.last_user = ""

        def complete(self, *, system: str, user: str, temperature: float) -> str:
            self.last_user = user
            return "From Alma. [[bofm/alma/1/5]]"

    real_load = Settings.load_yaml

    def load_yaml(self: Settings, name: str):
        data = real_load(self, name)
        if name == "rag.yaml":
            data = dict(data)
            retrieval = dict(data.get("retrieval") or {})
            retrieval["min_score"] = 0.9
            data["retrieval"] = retrieval
        return data

    monkeypatch.setattr(Settings, "load_yaml", load_yaml)
    gen = CapturingGen()
    result = run_ask(
        "q",
        settings=Settings(root=ROOT),
        retriever=StubRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "ok"
    assert "bofm/mosiah/1/10" not in gen.last_user
    assert "bofm/mosiah/1/9" not in gen.last_user
    assert "bofm/alma/1/5" in gen.last_user
    assert "bofm/alma/1/6" in gen.last_user
    assert all(s["id"] != "bofm/mosiah/1/10" for s in result.sources)


def test_ask_talk_mode_ok() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(
        replies=["Talk outline: invite listeners to experiment. [[bofm/alma/32/27]]"]
    )
    result = run_ask(
        "Help me prepare a talk on Alma 32",
        mode="talk",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "ok"
    assert result.mode == "talk"


def test_ask_regenerate_then_ok() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(
        replies=[
            "Bad citation. [[fake/id]]",
            "Corrected. [[bofm/alma/32/27]]",
        ]
    )
    result = run_ask(
        "q",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "ok"
    assert result.attempts == 2
    assert gen.calls is not None and gen.calls[1]["temperature"] == 0.0


def test_ask_unsupported_after_retry() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(replies=["Still bad [[nope]]", "Still bad [[nope]]"])
    result = run_ask(
        "q",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "unsupported"
    assert result.exit_code == EXIT_UNSUPPORTED
    assert result.answer is None
    assert result.rendered and "Retrieved sources" in result.rendered


def test_ask_strict_skips_retry() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(replies=["Bad [[nope]]", "would-not-be-used"])
    result = run_ask(
        "q",
        strict=True,
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "unsupported"
    assert result.attempts == 1
    assert len(gen.replies) == 1  # second reply unused


def test_ask_no_evidence() -> None:
    class EmptyRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(hits=[])

    result = run_ask(
        "what did the prophet say last Tuesday",
        settings=Settings(root=ROOT),
        retriever=EmptyRetriever(),
        generator=ScriptedGenerator(replies=["should not run"]),
        as_json=True,
    )
    assert result.status == "no_evidence"
    assert result.exit_code == EXIT_NO_EVIDENCE


def test_resolve_model_path_prefers_local(tmp_path: Path) -> None:
    from lds_study.index.model_paths import resolve_model_path

    models = tmp_path / "models"
    snap = models / "BAAI--bge-m3"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    settings = Settings(root=tmp_path, models_dir=models)
    path, is_local = resolve_model_path("BAAI/bge-m3", settings=settings)
    assert is_local
    assert path == str(snap)


def test_resolve_model_path_rejects_partial_snapshot(tmp_path: Path) -> None:
    from lds_study.index.model_paths import resolve_model_path

    models = tmp_path / "models"
    snap = models / "BAAI--bge-m3"
    snap.mkdir(parents=True)
    (snap / "shard.bin").write_text("partial", encoding="utf-8")
    settings = Settings(root=tmp_path, models_dir=models)
    path, is_local = resolve_model_path("BAAI/bge-m3", settings=settings)
    assert not is_local
    assert path == "BAAI/bge-m3"


def test_volume_filter_on_bm25() -> None:
    chunks = _scripture_chunks()
    bm25 = BM25Index.build(chunks)
    by_id = chunks_by_id(chunks)
    allowed = {cid for cid, c in by_id.items() if c.volume == "bofm"}
    ranked = bm25.query("shepherd", top_k=5, allowed_ids=allowed)
    assert all(cid in allowed for cid, _ in ranked)


def test_citation_empty_answer_fails_gate() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="x",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )
    ids = {"bofm/alma/32/27"}
    by_id = {"bofm/alma/32/27": chunk}
    for blank in ("", "   ", "## Summary"):
        report = validate_citations(blank, ids, by_id)
        assert report.coverage == 0.0
        assert not passes_citation_gate(report, CitationConfig()), blank


def test_ask_lesson_mode_ok() -> None:
    chunk = Chunk(
        id="bofm/alma/32/27",
        text="experiment",
        source_id="s",
        source_type="scripture",
        redistributable=True,
        canonical_ref="Alma 32:27",
    )

    class FixedRetriever:
        def retrieve(self, query: str, *, filters=None, top_k=None):
            return RetrievalResult(
                hits=[RetrievedHit(chunk=chunk, score=1.0, source="hybrid")]
            )

    gen = ScriptedGenerator(
        replies=[
            "Outline: invite the class to experiment upon the word. [[bofm/alma/32/27]]"
        ]
    )
    result = run_ask(
        "Prepare a short Alma 32 lesson",
        mode="lesson",
        settings=Settings(root=ROOT),
        retriever=FixedRetriever(),
        generator=gen,
        as_json=True,
    )
    assert result.status == "ok"
    assert result.mode == "lesson"


def test_phrase_smoke_harness_wiring_bm25_only() -> None:
    """Offline harness wiring with empty dense — not the full-corpus BGE-M3 gate."""
    chunks = _scripture_chunks()

    class EmptyDense:
        def existing_ids(self):
            return set()

        def upsert(self, chunks, embeddings):
            return None

        def query(self, embedding, *, top_k, filters=None):
            return []

        def count(self):
            return 0

    bm25 = BM25Index.build(chunks)
    retriever = HybridRetriever(
        dense=EmptyDense(),
        bm25=bm25,
        embedder=HashEmbedder(dim=8),
        chunks_by_id=chunks_by_id(chunks),
        reranker=IdentityReranker(),
        dense_top_k=50,
        bm25_top_k=50,
        final_top_k=1,
        neighbor_window=0,
    )
    passed, total = run_phrase_smoke(retriever, root=ROOT, verbose=False)
    assert (passed, total) == (10, 10)
