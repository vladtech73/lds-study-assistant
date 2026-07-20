"""Export helpers — restricted sources are unconditionally excluded."""

from __future__ import annotations

import json
from pathlib import Path

from lds_study.data.manifest import filter_exportable
from lds_study.data.models import Chunk


def write_exportable_jsonl(chunks: list[Chunk], path: Path) -> int:
    """
    Write only redistributable=True chunks.

    There is no flag to include restricted material. Restricted records are dropped
    with a counted return value of how many were written.
    """
    allowed = filter_exportable(chunks)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for chunk in allowed:
            fh.write(json.dumps(chunk.to_json(), ensure_ascii=False) + "\n")
    return len(allowed)


def count_restricted(chunks: list[Chunk]) -> int:
    return sum(1 for c in chunks if not c.redistributable)
