"""Load versioned system prompts from prompts/ (never splice retrieved chunks here)."""

from __future__ import annotations

from pathlib import Path

from lds_study.config import repo_root

MODE_FILES = {
    "study": "study_assistant.md",
    "lesson": "lesson_assistant.md",
    "talk": "talk_assistant.md",
}


def load_system_prompt(mode: str = "study", *, root: Path | None = None) -> str:
    key = mode.strip().lower()
    if key not in MODE_FILES:
        raise ValueError(f"Unknown ask mode {mode!r}; expected one of {sorted(MODE_FILES)}")
    base = root or repo_root()
    path = base / "prompts" / MODE_FILES[key]
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt file: {path}")
    text = path.read_text(encoding="utf-8").strip()
    # Drop markdown comment header lines starting with '# ' that are file meta only?
    # Keep full file — models benefit from the disclaimer lines.
    return text


def format_context_block(hits: list) -> str:
    """Format retrieved hits for the user/tool role."""
    lines: list[str] = ["Retrieved sources (cite with [[chunk_id]]):", ""]
    for hit in hits:
        chunk = hit.chunk
        ref = chunk.canonical_ref or chunk.title or chunk.id
        lines.append(f"### [[{chunk.id}]] — {ref}")
        if chunk.author:
            lines.append(f"Author: {chunk.author}")
        if chunk.source_type:
            lines.append(f"Type: {chunk.source_type}")
        lines.append(chunk.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_user_message(question: str, context_block: str) -> str:
    return (
        f"{context_block}\n"
        f"Question: {question}\n\n"
        "Answer using only the retrieved sources above. "
        "Cite each claim with [[chunk_id]] markers."
    )
