"""PR2 fixture-driven acceptance tests for prepare / chunk / export."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
import yaml

from lds_study.config import Settings
from lds_study.data.chunk_prose import chunk_prose
from lds_study.data.chunk_scripture import chunk_scripture_records, verse_record_to_chunk
from lds_study.data.export import count_restricted, write_exportable_jsonl
from lds_study.data.manifest import (
    ManifestError,
    UnverifiedSourceError,
    assert_source_ingestible,
    filter_exportable,
    load_sources_yaml,
)
from lds_study.data.models import SourceRecord
from lds_study.data.normalize import normalize_prose, normalize_scripture, normalize_text
from lds_study.data.prepare import prepare_from_records, run_prepare
from lds_study.data.sources.public_scripture import load_verse_json, sha256_file
from lds_study.data.sources.user_files import _extract_epub, _extract_pdf, load_user_files

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
NEPHI_ARTIFACT = (
    ROOT / "data" / "raw" / "public" / "nephi-scriptures" / "lds-scriptures-json.txt"
)


@pytest.fixture
def alma_records() -> list[dict]:
    return load_verse_json(FIX / "scripture" / "alma_32.json")


@pytest.fixture
def known_verses() -> list[dict]:
    return load_verse_json(FIX / "scripture" / "known_verses.json")


def test_alma_32_verse_count_and_ids(alma_records: list[dict]) -> None:
    source = SourceRecord(
        id="fixture-alma",
        type="scripture",
        loader="public_scripture",
        path_or_url="tests/fixtures/scripture/alma_32.json",
        license="public-domain",
        license_url="https://scriptures.nephi.org/",
        verified_on="2026-07-20",
        redistributable=True,
    )
    chunks, stats = prepare_from_records(alma_records, source=source)
    assert len(chunks) == 43
    assert stats.empty_dropped == 0
    ids = {c.id for c in chunks}
    assert "bofm/alma/32/27" in ids
    assert "bofm/alma/32/1" in ids
    assert "bofm/alma/32/43" in ids
    for chunk in chunks:
        assert chunk.volume == "bofm"
        assert chunk.book == "alma"
        assert chunk.chapter == 32
        assert chunk.canonical_ref.startswith("Alma 32:")
        assert "Chapter" not in chunk.text


def test_known_verses_match_expected_text_literal(known_verses: list[dict]) -> None:
    """Compare against committed expected_text — not normalize(input) (circular)."""
    assert len(known_verses) >= 20
    for record in known_verses:
        assert "expected_text" in record, f"missing expected_text for {record.get('verse_title')}"
        chunk = verse_record_to_chunk(record, source_id="known", redistributable=True)
        assert chunk is not None
        assert chunk.text == record["expected_text"]


def test_canonical_brackets_preserved(known_verses: list[dict]) -> None:
    by_ref = {r["verse_title"]: r for r in known_verses}
    for ref in ("1 John 2:23", "Joseph Smith--History 1:2"):
        record = by_ref[ref]
        chunk = verse_record_to_chunk(record, source_id="known", redistributable=True)
        assert chunk is not None
        assert chunk.text == record["expected_text"]
        assert "[" in chunk.text  # [but] / [1838] must survive


def test_normalize_strips_numeric_footnotes_in_prose_only() -> None:
    raw = (
        "Chapter 1\n"
        "In the beginning God created the heaven and the earth.[1]\n"
        "And the earth was without form,* and void†.\n"
    )
    prose = normalize_prose(raw)
    assert "Chapter 1" not in prose
    assert "[1]" not in prose
    assert "*" not in prose
    assert "†" not in prose
    assert "In the beginning" in prose

    # Scripture path must keep short editorial brackets.
    assert "[but]" in normalize_scripture("x [but] y")
    assert "[1838]" in normalize_scripture("year [1838] now")
    # Numeric footnotes still optional to leave in scripture (nephi has none);
    # we only strip them on the prose path.
    assert "[1]" in normalize_scripture("text[1] more")


def test_normalize_keeps_matthew_1_1() -> None:
    """Matthew 1:1 starts with 'The book of…' — must not be treated as a heading."""
    text = (
        "The book of the generation of Jesus Christ, the son of David, "
        "the son of Abraham."
    )
    assert normalize_scripture(text) == text


def test_normalize_dehyphenates_pdf_line_breaks() -> None:
    assert normalize_text("experi-\nment upon the word") == "experiment upon the word"


def test_prose_keeps_colon_lead_ins() -> None:
    text = (
        "The Savior taught three things:\n\n"
        "First, love God. Second, love your neighbor.\n\n"
        "President Nelson closed with this invitation:\n"
    )
    chunks, empty = chunk_prose(
        text,
        source_id="user-byof",
        source_type="talk",
        redistributable=False,
        doc_stem="sample",
    )
    joined = " ".join(c.text for c in chunks)
    assert "The Savior taught three things:" in joined
    assert "President Nelson closed with this invitation:" in joined
    assert empty == 0
    assert chunks
    assert chunks[0].window_index == 1
    assert chunks[0].char_offset is not None


def test_prose_chunk_ids_unique_across_same_stem(tmp_path: Path) -> None:
    (tmp_path / "2023").mkdir()
    (tmp_path / "2024").mkdir()
    (tmp_path / "2023" / "talk.txt").write_text(
        "Faith invites us to act with diligence and hope.\n", encoding="utf-8"
    )
    (tmp_path / "2024" / "talk.txt").write_text(
        "Charity never faileth and is the pure love of Christ.\n", encoding="utf-8"
    )
    # Same stem, different extension in one folder — must also stay unique.
    (tmp_path / "talk.txt").write_text("Plain text talk body about faith.\n", encoding="utf-8")
    (tmp_path / "talk.md").write_text("# Markdown\n\nMarkdown talk body about hope.\n", encoding="utf-8")
    source = SourceRecord(
        id="user-byof",
        type="talk",
        loader="user_files",
        path_or_url=str(tmp_path),
        license="copyright",
        license_url="https://example.invalid/terms",
        verified_on="2026-07-20",
        redistributable=False,
    )
    chunks, _ = load_user_files(source, root=tmp_path)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    assert any("2023-talk-txt" in i for i in ids)
    assert any("2024-talk-txt" in i for i in ids)
    assert any("/talk-txt/" in i for i in ids)
    assert any("/talk-md/" in i for i in ids)


def test_prepare_rejects_duplicate_chunk_ids() -> None:
    from lds_study.data.models import Chunk
    from lds_study.data.prepare import _assert_unique_chunk_ids

    chunks = [
        Chunk(
            id="a/1",
            text="x",
            source_id="s",
            source_type="talk",
            redistributable=False,
            source_path="2023/talk.txt",
        ),
        Chunk(
            id="a/1",
            text="y",
            source_id="s",
            source_type="talk",
            redistributable=False,
            source_path="2024/talk.txt",
        ),
    ]
    with pytest.raises(ManifestError, match="2023/talk.txt"):
        _assert_unique_chunk_ids(chunks)


def test_epub_metadata_and_chunks(tmp_path: Path) -> None:
    epub_path = FIX / "prose" / "sample_talk.epub"
    text, meta = _extract_epub(epub_path)
    assert meta.get("title") == "Think on These Things (Fixture)"
    assert meta.get("author") == "Jane Example"
    assert str(meta.get("date", "")).startswith("2023")
    assert "experiment upon the word" in text.lower() or "faith" in text.lower()

    source = SourceRecord(
        id="fixture-epub",
        type="talk",
        loader="user_files",
        path_or_url=str(tmp_path),
        license="copyright",
        license_url="https://example.invalid/terms",
        verified_on="2026-07-20",
        redistributable=False,
    )
    dest = tmp_path / "sample_talk.epub"
    dest.write_bytes(epub_path.read_bytes())
    chunks, stats = load_user_files(source, root=tmp_path)
    assert stats.chunk_count >= 1
    assert all(c.title == "Think on These Things (Fixture)" for c in chunks)
    assert all(c.date and c.date.startswith("2023") for c in chunks)
    assert all(c.redistributable is False for c in chunks)


def test_pdf_metadata_and_text_fixture() -> None:
    pdf_path = FIX / "prose" / "sample_lesson.pdf"
    text, meta = _extract_pdf(pdf_path)
    assert meta.get("title") == "Come Follow Me Fixture Lesson"
    assert meta.get("author") == "Curriculum Fixture"
    assert meta.get("date") == "2024-01-08"
    # Extractable body (de-hyphenation is covered separately in
    # test_normalize_dehyphenates_pdf_line_breaks).
    assert "Come Follow Me" in text
    assert "Alma 32" in text
    assert "experiment" in text.lower()


def test_restricted_never_in_export(tmp_path: Path) -> None:
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    src_txt = FIX / "prose" / "restricted_talk.txt"
    src_meta = FIX / "prose" / "restricted_talk.meta.json"
    (user_dir / "restricted_talk.txt").write_text(
        src_txt.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (user_dir / "restricted_talk.meta.json").write_text(
        src_meta.read_text(encoding="utf-8"), encoding="utf-8"
    )

    scripture = SourceRecord(
        id="fixture-alma",
        type="scripture",
        loader="public_scripture",
        path_or_url="n/a",
        license="public-domain",
        license_url="https://scriptures.nephi.org/",
        verified_on="2026-07-20",
        redistributable=True,
    )
    alma = load_verse_json(FIX / "scripture" / "alma_32.json")
    scripture_chunks, _ = prepare_from_records(alma, source=scripture)

    user_source = SourceRecord(
        id="user-byof",
        type="talk",
        loader="user_files",
        path_or_url=str(user_dir),
        license="copyright",
        license_url="https://example.invalid/terms",
        verified_on="2026-07-20",
        redistributable=False,
    )
    user_chunks, _ = load_user_files(user_source, root=tmp_path)
    assert user_chunks
    assert count_restricted(user_chunks) == len(user_chunks)

    combined = scripture_chunks + user_chunks
    export_path = tmp_path / "export.jsonl"
    written = write_exportable_jsonl(combined, export_path)
    assert written == len(scripture_chunks)
    lines = export_path.read_text(encoding="utf-8").strip().splitlines()
    for line in lines:
        row = json.loads(line)
        assert row["redistributable"] is True
        assert row["source_id"] != "user-byof"
    assert filter_exportable(combined) == scripture_chunks


def test_unverified_source_refused() -> None:
    source = SourceRecord(
        id="new-mirror",
        type="scripture",
        loader="public_scripture",
        path_or_url="https://example.invalid/x.json",
        license="unverified",
        license_url=None,
        verified_on=None,
        redistributable=True,
    )
    with pytest.raises(UnverifiedSourceError, match="unverified"):
        assert_source_ingestible(source)


def test_prepare_fixture_scripture_via_sources_yaml(tmp_path: Path) -> None:
    """End-to-end prepare against Alma 32 fixture (offline, no network)."""
    data_dir = tmp_path / "data"
    (data_dir / "raw" / "public").mkdir(parents=True)
    (data_dir / "raw" / "user").mkdir(parents=True)
    (data_dir / "processed").mkdir(parents=True)

    configs = tmp_path / "configs"
    configs.mkdir()
    sources = {
        "sources": [
            {
                "id": "fixture-alma",
                "type": "scripture",
                "loader": "public_scripture",
                "path_or_url": str(FIX / "scripture" / "alma_32.json"),
                "license": "public-domain",
                "license_url": "https://scriptures.nephi.org/",
                "verified_on": "2026-07-20",
                "redistributable": True,
                "notes": "offline fixture",
            }
        ]
    }
    (configs / "sources.yaml").write_text(
        yaml.dump(sources, sort_keys=False), encoding="utf-8"
    )
    (configs / "rag.yaml").write_text(
        (ROOT / "configs" / "rag.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (configs / "models.yaml").write_text(
        (ROOT / "configs" / "models.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    settings = Settings(root=tmp_path, data_dir=Path("data"))
    result = run_prepare(settings=settings, scripture_only=True, show_stats=False)
    assert len(result.chunks) == 43
    assert result.empty_total == 0
    assert result.chunks_path.exists()
    lines = result.chunks_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 43
    row = json.loads(lines[26])  # verse 27 is index 26
    assert row["id"] == "bofm/alma/32/27"
    assert "experiment upon my words" in row["text"]


def test_prepare_epub_via_sources_yaml_end_to_end(tmp_path: Path) -> None:
    """Plan gate: ePub under BYOF + run_prepare adds sections with title/date."""
    data_dir = tmp_path / "data"
    user_dir = data_dir / "raw" / "user"
    user_dir.mkdir(parents=True)
    (data_dir / "raw" / "public").mkdir(parents=True)
    (data_dir / "processed").mkdir(parents=True)

    epub_dest = user_dir / "sample_talk.epub"
    epub_dest.write_bytes((FIX / "prose" / "sample_talk.epub").read_bytes())

    configs = tmp_path / "configs"
    configs.mkdir()
    sources = {
        "sources": [
            {
                "id": "fixture-alma",
                "type": "scripture",
                "loader": "public_scripture",
                "path_or_url": str(FIX / "scripture" / "alma_32.json"),
                "license": "public-domain",
                "license_url": "https://scriptures.nephi.org/",
                "verified_on": "2026-07-20",
                "redistributable": True,
            },
            {
                "id": "user-byof",
                "type": "talk",
                "loader": "user_files",
                "path_or_url": "data/raw/user",
                "license": "copyright",
                "license_url": "https://example.invalid/terms",
                "verified_on": "2026-07-20",
                "redistributable": False,
            },
        ]
    }
    (configs / "sources.yaml").write_text(
        yaml.dump(sources, sort_keys=False), encoding="utf-8"
    )
    (configs / "rag.yaml").write_text(
        (ROOT / "configs" / "rag.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (configs / "models.yaml").write_text(
        (ROOT / "configs" / "models.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    settings = Settings(root=tmp_path, data_dir=Path("data"))
    result = run_prepare(settings=settings, show_stats=False)

    assert len(result.chunks) > 43
    byof = [c for c in result.chunks if c.source_id == "user-byof"]
    assert byof
    assert all(c.title == "Think on These Things (Fixture)" for c in byof)
    assert all(c.date and c.date.startswith("2023") for c in byof)
    assert all(c.redistributable is False for c in byof)
    assert any("sample-talk-epub" in c.id for c in byof)

    lines = result.chunks_path.read_text(encoding="utf-8").strip().splitlines()
    rows = [json.loads(line) for line in lines]
    assert any(r["source_id"] == "user-byof" for r in rows)

    from lds_study.data.export import write_exportable_jsonl

    export_path = tmp_path / "export.jsonl"
    written = write_exportable_jsonl(result.chunks, export_path)
    assert written == 43
    export_rows = [
        json.loads(line) for line in export_path.read_text(encoding="utf-8").splitlines()
    ]
    assert all(r["redistributable"] is True for r in export_rows)
    assert all(r["source_id"] != "user-byof" for r in export_rows)


def test_repo_sources_yaml_loads() -> None:
    sources = load_sources_yaml(ROOT / "configs" / "sources.yaml")
    assert {s.id for s in sources} >= {"nephi-scriptures", "user-byof"}
    by_id = {s.id: s for s in sources}
    assert by_id["nephi-scriptures"].redistributable is True
    assert by_id["user-byof"].redistributable is False
    assert_source_ingestible(by_id["nephi-scriptures"])
    assert_source_ingestible(by_id["user-byof"])


def test_verse_counts_table_committed() -> None:
    data = yaml.safe_load((ROOT / "configs" / "verse_counts.yaml").read_text(encoding="utf-8"))
    assert data["total"] == 41995
    assert data["volumes"]["bofm"] == 6604
    assert data["sha256"] == (
        "8797555ccdf4a4d3f5846211aa6ff2b5bb74e97c3264ce48e2ec0933b13bd7e8"
    )


def test_full_dump_matches_verse_counts_when_present() -> None:
    """Opt-in local gate: skip in CI when the 18MB artifact is absent."""
    if not NEPHI_ARTIFACT.exists():
        pytest.skip("nephi scripture artifact not downloaded")
    expected = yaml.safe_load(
        (ROOT / "configs" / "verse_counts.yaml").read_text(encoding="utf-8")
    )
    assert sha256_file(NEPHI_ARTIFACT) == expected["sha256"]
    records = load_verse_json(NEPHI_ARTIFACT)
    volume_map = {
        "Old Testament": "ot",
        "New Testament": "nt",
        "Book of Mormon": "bofm",
        "Doctrine and Covenants": "dc",
        "Pearl of Great Price": "pgp",
    }
    counts = Counter(volume_map[r["volume_title"]] for r in records)
    assert dict(counts) == expected["volumes"]
    assert sum(counts.values()) == expected["total"]

    source = SourceRecord(
        id="nephi-scriptures",
        type="scripture",
        loader="public_scripture",
        path_or_url=str(NEPHI_ARTIFACT),
        license="public-domain",
        license_url="https://scriptures.nephi.org/",
        verified_on="2026-07-20",
        redistributable=True,
    )
    chunks, stats = prepare_from_records(records, source=source)
    assert stats.empty_dropped == 0
    assert len(chunks) == expected["total"]
    by_vol = Counter(c.volume for c in chunks)
    assert dict(by_vol) == expected["volumes"]


def test_chunk_scripture_rejects_heading_pollution(alma_records: list[dict]) -> None:
    polluted = dict(alma_records[0])
    polluted["scripture_text"] = "Chapter 32\n" + polluted["scripture_text"] + "[1]"
    chunks, empty = chunk_scripture_records(
        [polluted], source_id="x", redistributable=True
    )
    assert empty == 0
    assert len(chunks) == 1
    assert "Chapter 32" not in chunks[0].text
    # Scripture path keeps numeric brackets too (nephi has none; fidelity > strip).
    assert "[1]" in chunks[0].text
