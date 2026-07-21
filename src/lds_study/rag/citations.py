"""Citation parse / validate / render — never silent-strip invalid markers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lds_study.data.models import Chunk

DEFAULT_MARKER_PATTERN = r"\[\[([^\]]+)\]\]"


@dataclass(slots=True)
class CitationReport:
    markers: list[str]
    valid: list[str]
    invalid: list[str]
    coverage: float
    claim_paragraphs: int
    cited_paragraphs: int
    rendered: str
    raw_answer: str


@dataclass(slots=True)
class CitationConfig:
    min_coverage: float = 0.8
    max_regenerate: int = 1
    marker_pattern: str = DEFAULT_MARKER_PATTERN


def parse_markers(text: str, pattern: str = DEFAULT_MARKER_PATTERN) -> list[str]:
    return re.findall(pattern, text)


def render_human_ref(chunk: Chunk) -> str:
    """Human-readable citation label."""
    if chunk.canonical_ref:
        return chunk.canonical_ref
    if chunk.source_type == "scripture" and chunk.book and chunk.chapter and chunk.verse:
        return f"{chunk.book} {chunk.chapter}:{chunk.verse}"
    parts: list[str] = []
    if chunk.author:
        parts.append(chunk.author)
    if chunk.title:
        title = f'"{chunk.title}"'
        if chunk.date:
            title = f"{title}, {chunk.date}"
        parts.append(title)
    elif chunk.date:
        parts.append(chunk.date)
    if parts:
        return ", ".join(parts)
    return chunk.id


def render_answer_with_refs(
    answer: str,
    chunks_by_id: dict[str, Chunk],
    pattern: str = DEFAULT_MARKER_PATTERN,
) -> str:
    """Replace [[id]] with human refs; leave unknown markers intact (no stripping)."""

    def repl(match: re.Match[str]) -> str:
        cid = match.group(1)
        chunk = chunks_by_id.get(cid)
        if chunk is None:
            return match.group(0)
        return f"[{render_human_ref(chunk)}]"

    return re.sub(pattern, repl, answer)


def _claim_paragraphs(text: str) -> list[str]:
    """Split into substantive paragraphs (skip blanks and markdown headings-only)."""
    paras: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        cleaned = block.strip()
        if not cleaned:
            continue
        # Skip pure heading lines
        lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
        if lines and all(ln.startswith("#") for ln in lines):
            continue
        paras.append(cleaned)
    return paras


def validate_citations(
    answer: str,
    retrieved_ids: set[str],
    chunks_by_id: dict[str, Chunk],
    *,
    config: CitationConfig | None = None,
) -> CitationReport:
    cfg = config or CitationConfig()
    markers = parse_markers(answer, cfg.marker_pattern)
    valid = [m for m in markers if m in retrieved_ids]
    invalid = [m for m in markers if m not in retrieved_ids]

    paras = _claim_paragraphs(answer)
    cited = 0
    for para in paras:
        para_markers = parse_markers(para, cfg.marker_pattern)
        if any(m in retrieved_ids for m in para_markers):
            cited += 1
    if paras:
        coverage = cited / len(paras)
    else:
        # Fail closed: empty / heading-only / whitespace answers are not "fully cited".
        coverage = 0.0

    rendered = render_answer_with_refs(answer, chunks_by_id, cfg.marker_pattern)
    return CitationReport(
        markers=markers,
        valid=valid,
        invalid=invalid,
        coverage=coverage,
        claim_paragraphs=len(paras),
        cited_paragraphs=cited,
        rendered=rendered,
        raw_answer=answer,
    )


def passes_citation_gate(report: CitationReport, config: CitationConfig) -> bool:
    """Require ≥1 valid citation and coverage, with no invalid markers."""
    if report.invalid:
        return False
    if not report.valid:
        return False
    return report.coverage >= config.min_coverage


_REFUSAL_RE = re.compile(
    r"(?is)\b(?:i\s+)?(?:do\s+not|don't)\s+find\b.{0,80}\bindexed\s+sources\b"
)

# Keep in sync with prompts/* refusal wording (see test_prompt_refusal_matches_detector).
CANNED_NO_EVIDENCE = "I don't find this in the indexed sources."


def looks_like_honest_refusal(answer: str) -> bool:
    """True only when the answer *is* an uncited refusal — not a hedge wrapping one.

    Requires a single claim paragraph, the refusal phrase near the start, and little
    residual prose outside the matched phrase (blocks "I don't find…, but here's…").
    """
    text = answer.strip()
    if not text:
        return False
    if parse_markers(text):
        return False
    paras = _claim_paragraphs(text)
    if len(paras) != 1:
        return False
    para = paras[0]
    match = _REFUSAL_RE.search(para)
    if match is None or match.start() > 20:
        return False
    residual = (para[: match.start()] + para[match.end() :]).strip(" \t\r\n.;,:—-")
    return len(residual) < 24


def corrective_instruction(report: CitationReport, valid_ids: list[str]) -> str:
    parts = [
        "Your previous answer failed citation validation.",
        "Regenerate the entire answer.",
        "Use ONLY [[chunk_id]] markers from this valid id list:",
        ", ".join(valid_ids) if valid_ids else "(none)",
    ]
    if report.invalid:
        parts.append(
            "Do not use these invalid markers: " + ", ".join(sorted(set(report.invalid)))
        )
    parts.append(
        f"Every claim-bearing paragraph needs a valid citation "
        f"(coverage was {report.coverage:.2f})."
    )
    return "\n".join(parts)
