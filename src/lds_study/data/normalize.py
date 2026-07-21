"""Text normalization for scripture and prose before chunking."""

from __future__ import annotations

import re
import unicodedata

# Smart punctuation → ASCII
_TRANSLATE = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u2026": "...",
    }
)

# Do NOT strip [but], [1838], [Kirtland], etc. — those are canonical editorial insertions.
# Numeric footnotes / dagger markers apply on the prose extraction path only.
_PROSE_EXTRACTION_MARKERS = re.compile(
    r"(?:"
    r"\[\d+\]"
    r"|(?<!\w)\*\d*"
    r"|†\d*"
    r"|‡\d*"
    r")"
)

# Soft hyphen and PDF end-of-line hyphenation: "experi-\nment" → "experiment"
_SOFT_HYPHEN = "\u00ad"
_DEHYPHEN = re.compile(r"(\w)-\n(\w)")
_MULTISPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")

# Short apparatus-style heading lines (not full sentences — see _is_heading_line).
_HEADING_LINE = re.compile(
    r"^(?:"
    r"chapter\s+\d+"
    r"|section\s+\d+"
    r"|the\s+book\s+of\b[\w\s\-']{0,40}"
    r"|summary\b[\w\s\-']{0,40}"
    r"|introduction\b[\w\s\-']{0,40}"
    r")\s*$",
    re.IGNORECASE,
)


def _is_heading_line(line: str) -> bool:
    """True for short apparatus headings, false for real verse/prose sentences.

    Matthew 1:1 begins with \"The book of the generation...\" — that must not be dropped.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    # Real verses/sentences end with sentence punctuation; headings usually do not.
    if stripped[-1] in ".!?;:":
        return False
    return bool(_HEADING_LINE.match(stripped))


def normalize_text(
    text: str,
    *,
    drop_heading_lines: bool = True,
    strip_extraction_markers: bool = False,
) -> str:
    """NFC, punctuation normalize, de-hyphenate, optionally strip extraction markers.

    For scripture (nephi dump), leave ``strip_extraction_markers=False`` so canonical
    bracketed insertions like ``[but]`` and ``[1838]`` are preserved verbatim.
    For PDF/ePub prose, set it True to remove numeric footnotes and * / † / ‡ markers.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace(_SOFT_HYPHEN, "")
    text = text.translate(_TRANSLATE)
    text = _DEHYPHEN.sub(r"\1\2", text)
    if strip_extraction_markers:
        text = _PROSE_EXTRACTION_MARKERS.sub("", text)
    if drop_heading_lines:
        lines = []
        for line in text.splitlines():
            if _is_heading_line(line):
                continue
            lines.append(line)
        text = "\n".join(lines)
    text = _MULTISPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def normalize_scripture(text: str) -> str:
    """Normalize verse text without stripping canonical brackets or prose markers."""
    return normalize_text(text, drop_heading_lines=True, strip_extraction_markers=False)


def normalize_prose(text: str) -> str:
    """Normalize BYOF prose; strip numeric footnote / dagger markers from extraction."""
    return normalize_text(text, drop_heading_lines=True, strip_extraction_markers=True)


def is_empty_after_normalize(text: str) -> bool:
    return not normalize_text(text)
