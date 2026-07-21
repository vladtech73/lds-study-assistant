"""`lds ask` orchestration — retrieve → generate → cite → regenerate/refuse."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from rich.console import Console

from lds_study.config import Settings, get_settings
from lds_study.data.models import Chunk
from lds_study.index.base import RetrievalFilters, RetrievalResult, RetrievedHit, Retriever
from lds_study.index.build import load_retriever
from lds_study.rag.citations import (
    CANNED_NO_EVIDENCE,
    CitationConfig,
    CitationReport,
    corrective_instruction,
    looks_like_honest_refusal,
    passes_citation_gate,
    validate_citations,
)
from lds_study.rag.generate import Generator, build_ollama_generator
from lds_study.rag.prompts import build_user_message, format_context_block, load_system_prompt

console = Console()

EXIT_OK = 0
EXIT_UNSUPPORTED = 2
EXIT_NO_EVIDENCE = 3


@dataclass(slots=True)
class AskResult:
    status: str  # ok | unsupported | no_evidence
    exit_code: int
    question: str
    mode: str
    answer: str | None
    rendered: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)
    citation: dict[str, Any] | None = None
    attempts: int = 0
    peak_vram_gb: float | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def run_ask(
    question: str,
    *,
    mode: str = "study",
    profile: str = "default",
    strict: bool = False,
    show_context: bool = False,
    as_json: bool = False,
    filters: RetrievalFilters | None = None,
    verbose: bool = False,
    settings: Settings | None = None,
    retriever: Retriever | None = None,
    generator: Generator | None = None,
    emit: bool = True,
    retrieval: RetrievalResult | None = None,
) -> AskResult:
    settings = settings or get_settings()
    models_cfg = settings.load_yaml("models.yaml")
    rag_cfg = settings.load_yaml("rag.yaml")
    ask_cfg = rag_cfg.get("ask") or {}
    cite_raw = rag_cfg.get("citation") or {}
    retrieval_cfg = rag_cfg.get("retrieval") or {}

    mode = (mode or ask_cfg.get("default_mode") or "study").strip().lower()
    temperature = float(ask_cfg.get("temperature", 0.2))
    retry_temperature = float(ask_cfg.get("retry_temperature", 0.0))
    min_score = float(retrieval_cfg.get("min_score", 0.0))

    cite_cfg = CitationConfig(
        min_coverage=float(cite_raw.get("min_coverage", 0.8)),
        max_regenerate=int(cite_raw.get("max_regenerate", 1)),
        marker_pattern=str(cite_raw.get("marker_pattern") or r"\[\[([^\]]+)\]\]"),
    )

    if retrieval is None:
        if retriever is None:
            retriever = load_retriever(profile=profile, settings=settings, verbose=verbose)
        if generator is None:
            generator = build_ollama_generator(models_cfg, settings.ollama_host)
        retrieval = retriever.retrieve(question, filters=filters)
    else:
        if generator is None:
            generator = build_ollama_generator(models_cfg, settings.ollama_host)

    seed_hits = [h for h in retrieval.hits if h.source != "expand"]
    qualifying_seeds = [h for h in seed_hits if h.score >= min_score]

    if show_context:
        for hit in retrieval.hits:
            row = _source_row(hit.chunk)
            console.print(
                f"{row['id']}  {row.get('ref') or ''}\n{row['text'][:500]}\n",
                markup=False,
            )

    if not qualifying_seeds:
        result = AskResult(
            status="no_evidence",
            exit_code=EXIT_NO_EVIDENCE,
            question=question,
            mode=mode,
            answer=None,
            rendered=None,
            sources=[_source_row(h.chunk) for h in retrieval.hits],
            attempts=0,
            peak_vram_gb=retrieval.peak_vram_gb,
        )
        if emit:
            _emit(result, as_json=as_json)
        return result

    # Keep seed hits plus expand neighbors whose seed still qualifies.
    qualify_ids = {h.chunk.id for h in qualifying_seeds}
    hits: list[RetrievedHit] = []
    for hit in retrieval.hits:
        if hit.source != "expand" and hit.chunk.id in qualify_ids:
            hits.append(hit)
        elif hit.source == "expand" and hit.seed_id in qualify_ids:
            hits.append(hit)

    source_rows = [_source_row(h.chunk) for h in hits]
    system = load_system_prompt(mode, root=settings.effective_root)
    context = format_context_block(hits)
    user = build_user_message(question, context)
    retrieved_ids = {h.chunk.id for h in hits}
    chunks_by_id = {h.chunk.id: h.chunk for h in hits}

    max_attempts = 1 if strict else (1 + max(0, cite_cfg.max_regenerate))
    report: CitationReport | None = None
    answer = ""
    attempts = 0

    for attempt in range(max_attempts):
        attempts = attempt + 1
        temp = temperature if attempt == 0 else retry_temperature
        user_msg = user
        if attempt > 0 and report is not None:
            user_msg = f"{user}\n\n{corrective_instruction(report, sorted(retrieved_ids))}"
        answer = generator.complete(system=system, user=user_msg, temperature=temp)
        report = validate_citations(answer, retrieved_ids, chunks_by_id, config=cite_cfg)
        if looks_like_honest_refusal(answer):
            # Never echo model prose on this path — canned line + retrieved sources only.
            listing = _no_evidence_listing(hits)
            result = AskResult(
                status="no_evidence",
                exit_code=EXIT_NO_EVIDENCE,
                question=question,
                mode=mode,
                answer=None,
                rendered=listing,
                sources=source_rows,
                citation=_cite_dict(report),
                attempts=attempts,
                peak_vram_gb=retrieval.peak_vram_gb,
            )
            if emit:
                _emit(result, as_json=as_json)
            return result
        if passes_citation_gate(report, cite_cfg):
            result = AskResult(
                status="ok",
                exit_code=EXIT_OK,
                question=question,
                mode=mode,
                answer=report.raw_answer,
                rendered=report.rendered,
                sources=source_rows,
                citation=_cite_dict(report),
                attempts=attempts,
                peak_vram_gb=retrieval.peak_vram_gb,
            )
            if emit:
                _emit(result, as_json=as_json)
            return result

    listing = _plain_source_list(hits)
    result = AskResult(
        status="unsupported",
        exit_code=EXIT_UNSUPPORTED,
        question=question,
        mode=mode,
        answer=None,
        rendered=listing,
        sources=source_rows,
        citation=_cite_dict(report) if report else None,
        attempts=attempts,
        peak_vram_gb=retrieval.peak_vram_gb,
    )
    if emit:
        _emit(result, as_json=as_json)
    return result


def _source_row(chunk: Chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "ref": chunk.canonical_ref,
        "source_type": chunk.source_type,
        "text": chunk.text,
        "author": chunk.author,
        "title": chunk.title,
        "date": chunk.date,
    }


def _cite_dict(report: CitationReport) -> dict[str, Any]:
    return {
        "markers": report.markers,
        "valid": report.valid,
        "invalid": report.invalid,
        "coverage": report.coverage,
        "claim_paragraphs": report.claim_paragraphs,
        "cited_paragraphs": report.cited_paragraphs,
    }


def _append_sources(lines: list[str], hits: list[RetrievedHit]) -> None:
    lines.append("Retrieved sources:")
    lines.append("")
    for hit in hits:
        chunk = hit.chunk
        ref = chunk.canonical_ref or chunk.id
        lines.append(f"- {ref} (id: {chunk.id})")
        lines.append(f"  {chunk.text}")
        lines.append("")


def _no_evidence_listing(hits: list[RetrievedHit]) -> str:
    lines = [CANNED_NO_EVIDENCE, ""]
    _append_sources(lines, hits)
    return "\n".join(lines).rstrip() + "\n"


def _plain_source_list(hits: list[RetrievedHit]) -> str:
    lines = [
        "I could not produce a fully supported answer from the indexed sources.",
        "",
    ]
    _append_sources(lines, hits)
    return "\n".join(lines).rstrip() + "\n"


def _emit(result: AskResult, *, as_json: bool) -> None:
    if as_json:
        console.print_json(data=result.to_json())
        return
    # Model / BYOF / citation text must not go through rich markup — lowercase
    # [chunk/ids] and stray [/tags] would be stripped or raise MarkupError.
    if result.status == "ok":
        console.print(result.rendered or result.answer or "", markup=False)
    elif result.status == "no_evidence":
        console.print(result.rendered or CANNED_NO_EVIDENCE, markup=False)
        console.print("(status=no_evidence)", style="yellow")
    else:
        console.print(result.rendered or "", markup=False)
        console.print("(status=unsupported)", style="yellow")
