"""Load committed + optional local golden question sets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

BUCKETS = (
    "verse_lookup",
    "doctrinal_synthesis",
    "lesson_planning",
    "adversarial",
)


@dataclass(slots=True)
class GoldenQuestion:
    id: str
    bucket: str
    question: str
    gold_chunk_ids: list[str] = field(default_factory=list)
    expect_refuse: bool = False
    mode: str = "study"
    notes: str = ""
    source: str = "golden"  # golden | local

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, source: str) -> GoldenQuestion:
        qid = str(raw.get("id") or "").strip()
        if not qid:
            raise ValueError("golden question missing id")
        bucket = str(raw.get("bucket") or "").strip()
        if bucket not in BUCKETS:
            raise ValueError(f"question {qid}: unknown bucket {bucket!r}")
        question = str(raw.get("question") or "").strip()
        if not question:
            raise ValueError(f"question {qid}: empty question")
        gold = raw.get("gold_chunk_ids") or []
        if not isinstance(gold, list):
            raise ValueError(f"question {qid}: gold_chunk_ids must be a list")
        mode = str(raw.get("mode") or "study").strip().lower() or "study"
        expect_refuse = bool(raw.get("expect_refuse", bucket == "adversarial"))
        return cls(
            id=qid,
            bucket=bucket,
            question=question,
            gold_chunk_ids=[str(x) for x in gold],
            expect_refuse=expect_refuse,
            mode=mode,
            notes=str(raw.get("notes") or ""),
            source=source,
        )


def default_golden_path(root: Path) -> Path:
    return root / "eval" / "golden.yaml"


def default_local_golden_path(root: Path) -> Path:
    return root / "eval" / "golden.local.yaml"


def load_golden_file(path: Path, *, source: str) -> list[GoldenQuestion]:
    if not path.is_file():
        raise FileNotFoundError(f"golden file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    items = data.get("questions")
    if not isinstance(items, list) or not items:
        raise ValueError(f"{path}: questions must be a non-empty list")
    return [GoldenQuestion.from_mapping(item, source=source) for item in items]


def load_golden_set(
    root: Path,
    *,
    include_local: bool = True,
    buckets: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[GoldenQuestion]:
    """Load committed golden.yaml plus optional gitignored golden.local.yaml."""
    questions = load_golden_file(default_golden_path(root), source="golden")
    local_path = default_local_golden_path(root)
    if include_local and local_path.is_file():
        questions.extend(load_golden_file(local_path, source="local"))

    seen: set[str] = set()
    deduped: list[GoldenQuestion] = []
    for q in questions:
        if q.id in seen:
            raise ValueError(f"duplicate golden question id: {q.id}")
        seen.add(q.id)
        deduped.append(q)

    if buckets:
        allowed = {b.strip() for b in buckets if b and b.strip()}
        unknown = allowed - set(BUCKETS)
        if unknown:
            raise ValueError(f"unknown buckets: {sorted(unknown)}")
        deduped = [q for q in deduped if q.bucket in allowed]

    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        deduped = deduped[:limit]
    return deduped
