"""Phrase-lookup smoke harness.

`lds index --smoke` runs these phrases against the full built index (plan gate).
Committed unit tests only prove harness wiring on a tiny fixture corpus — they do
**not** satisfy the plan's 10/10 full-corpus gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from lds_study.index.base import Retriever

console = Console()

DEFAULT_PHRASES = [
    {
        "phrase": "Adam fell that men might be; and men are, that they might have joy",
        "chunk_id": "bofm/2-nephi/2/25",
    },
    {
        "phrase": "I will go and do the things which the Lord hath commanded",
        "chunk_id": "bofm/1-nephi/3/7",
    },
    {
        "phrase": "experiment upon my words",
        "chunk_id": "bofm/alma/32/27",
    },
    {
        "phrase": "The Lord is my shepherd; I shall not want",
        "chunk_id": "ot/psalms/23/1",
    },
    {
        "phrase": "For God so loved the world, that he gave his only begotten Son",
        "chunk_id": "nt/john/3/16",
    },
    {
        "phrase": "Ye are the light of the world. A city that is set on an hill cannot be hid",
        "chunk_id": "nt/matthew/5/14",
    },
    {
        "phrase": "In the beginning God created the heaven and the earth",
        "chunk_id": "ot/genesis/1/1",
    },
    {
        "phrase": "natural man is an enemy to God",
        "chunk_id": "bofm/mosiah/3/19",
    },
    {
        "phrase": "men are that they might have joy",
        "chunk_id": "bofm/2-nephi/2/25",
    },
    {
        "phrase": "faith is not to have a perfect knowledge of things",
        "chunk_id": "bofm/alma/32/21",
    },
]


def load_phrase_fixtures(root: Path) -> list[dict[str, str]]:
    path = root / "tests" / "fixtures" / "index" / "phrase_smoke.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    return DEFAULT_PHRASES


def run_phrase_smoke(
    retriever: Retriever,
    *,
    root: Path,
    verbose: bool = False,
) -> tuple[int, int]:
    """Return (passed, total) where pass means expected chunk_id at rank 1 among seed hits."""
    phrases = load_phrase_fixtures(root)
    passed = 0
    for item in phrases:
        phrase = item["phrase"]
        expected = item["chunk_id"]
        result = retriever.retrieve(phrase, top_k=1)
        # Expanded neighbors may precede; prefer first non-expand hit, else first hit.
        seed = next((h for h in result.hits if h.source != "expand"), None)
        if seed is None and result.hits:
            seed = result.hits[0]
        got = seed.chunk.id if seed else None
        ok = got == expected
        if ok:
            passed += 1
        if verbose or not ok:
            mark = "OK" if ok else "FAIL"
            console.print(f"  [{mark}] expected={expected} got={got} :: {phrase[:60]}…")
    return passed, len(phrases)
