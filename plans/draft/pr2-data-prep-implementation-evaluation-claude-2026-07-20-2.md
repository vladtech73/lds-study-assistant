# PR2 — Data Prep + Fixtures — Implementation Evaluation (round 2)

*Evaluator: claude · 2026-07-20 · Second pass over `claude-2026-07-20.md` (step 2 / PR2) after the
round-1 remediations landed at 19:01–19:03. Supersedes
[`pr2-data-prep-implementation-evaluation-claude-2026-07-20.md`](pr2-data-prep-implementation-evaluation-claude-2026-07-20.md).*

## Verdict: All four High findings from round 1 are genuinely fixed and independently verified. PR2 is ready to merge; one residual id-collision case and two doc/comment overclaims are worth a small follow-up.

The verse-corruption bug is gone at the corpus level, not just in the test: all **41,995** verses
now pass through `normalize_scripture` **byte-unchanged** (was 2 altered). The circular
character-for-character test has been replaced with a literal `expected_text` comparison, and
all 22 committed expected strings are byte-identical to the raw mirror dump — so the test now
has an independent baseline rather than re-deriving the answer. Colon lead-ins survive prose
chunking, prose ids are path-derived, and `run_prepare` hard-fails on duplicate ids before
writing. 31 tests pass offline (was 25); ruff clean.

What remains is narrow: same-stem-different-extension files still collide (now a loud failure
rather than silent corruption), `char_offset` is an offset into derived text rather than the
source file, and one test docstring claims coverage the fixture does not provide.

## Round-1 findings — disposition

| # | Round-1 finding | Status | Verification |
|---|---|---|---|
| 1 | Footnote regex deleted `[but]` / `[1838]` | **Fixed** | Bracket stripping moved behind `strip_extraction_markers`, off for scripture ([normalize.py:68-107](src/lds_study/data/normalize.py#L68-L107)); `chunk_scripture.py:64` calls `normalize_scripture`. Re-ran the full dump: **0 of 41,995 verses altered**. On-disk `chunks.jsonl` regenerated at 19:04 — `nt/1-john/2/23` now reads `…hath not the Father: [but] he that acknowledgeth…`. Pinned by [test_canonical_brackets_preserved](tests/test_pr2_prepare.py#L82-L89); the old `assert "[" not in chunk.text` assertions are gone. |
| 2 | Colon-terminated paragraphs silently discarded | **Fixed** | Colon-as-heading rule removed; only markdown `#` and all-caps lines split ([chunk_prose.py:49-58](src/lds_study/data/chunk_prose.py#L49-L58)). Heading text is now re-inserted into the section body ([:33-35](src/lds_study/data/chunk_prose.py#L33-L35)) and body-less headings are counted into `empty_dropped` ([:37-39](src/lds_study/data/chunk_prose.py#L37-L39)). My round-1 repro now returns both colon lines in chunk text. |
| 3 | Prose chunk ids collided across folders | **Fixed (mostly — see Finding A)** | `_doc_stem` slugifies the path relative to the BYOF root ([user_files.py:206-214](src/lds_study/data/sources/user_files.py#L206-L214)); `2023/talk.txt` → `user-byof/2023-talk/1`. Belt-and-braces `_assert_unique_chunk_ids` runs before `_write_jsonl` ([prepare.py:86](src/lds_study/data/prepare.py#L86), [:161-174](src/lds_study/data/prepare.py#L161-L174)). |
| 4 | "Character-for-character" test was circular | **Fixed** | [test_known_verses_match_expected_text_literal](tests/test_pr2_prepare.py#L72-L79) compares to a committed `expected_text`. I checked all 22 records: `expected_text == raw dump text` **22/22**, and each input record is byte-identical to the mirror. The baseline is real. |
| 5 | `paragraph_anchor` was not a paragraph anchor | **Fixed by renaming** | Field split into `window_index` + `char_offset` ([models.py](src/lds_study/data/models.py)). Honest naming; see Finding B on the remaining semantic gap. |
| 6 | Nothing bound prepare output to `verse_counts.yaml` | **Fixed** | [test_full_dump_matches_verse_counts_when_present](tests/test_pr2_prepare.py#L356-L390) verifies artifact sha256, per-volume counts, and that a real `prepare_from_records` over all 41,995 records reproduces the table — `pytest.skip` when the 18MB artifact is absent, so CI stays offline. It ran (not skipped) on this machine. |
| 7 | PDF fixture proved metadata only | **Mostly fixed** | Fixture regenerated with extractable text (`"Come Follow Me Fixture Lesson\nStudy Alma 32 and discuss experiment upon the word with your family."`), and `_DEHYPHEN` now has a direct unit test ([:122-123](tests/test_pr2_prepare.py#L122-L123)). See Finding C. |
| 8 | Missing-BYOF-dir returned silently | **Fixed** | Warns with the resolved path ([user_files.py:58-66](src/lds_study/data/sources/user_files.py#L58-L66)). |
| 9 | Legal posture stronger than required | **Noted — unchanged** | No override flag; `filter_exportable` still the single unconditional export path. |

## Findings (ranked)

### A. Files sharing a stem but differing in extension still collide — and the error message misdiagnoses it. *(Low)*

`_doc_stem` drops the suffix (`rel.stem`), so `talk.txt` and `talk.md` in the *same* folder both
produce `user-byof/talk`. Reproduced:

```
talk.txt + talk.md  →  ['user-byof/talk/1', 'user-byof/talk/1']   1 unique id of 2
```

This is now caught — `_assert_unique_chunk_ids` raises before anything is written, so it fails
loudly rather than corrupting retrieval. But the layout is plausible (Gospel Library exports
often ship `.html` alongside `.txt`), and the raised message says *"Use distinct relative paths
under the BYOF root"* — which is exactly what the user already has. They would have to read the
source to work out that the extension is the problem.

**Remediation:** include the suffix in the stem when it would otherwise collide (or
unconditionally: `2023-talk-txt`), and name the offending file paths in the `ManifestError`
rather than only the duplicated chunk ids.

### B. `char_offset` is an offset into derived text, not the source document. *(Low)*

[chunk_prose.py:119-139](src/lds_study/data/chunk_prose.py#L119-L139) computes the offset inside
the *normalized, heading-prepended, section-concatenated* body and accumulates `len(body_norm) + 2`
per section. It cannot be used to seek into the user's ePub/PDF/HTML. Two smaller wrinkles:
`find(piece[:40])` returns `-1` (clamped to 0) whenever normalization altered the window text,
and overlapping windows resolve to the first match.

The `Chunk` docstring compounds this — `window_index` is annotated *"not a source-paragraph
locator — see char_offset"*, which implies `char_offset` **is** one. That is the same overclaim
round 1 flagged, moved one field over.

**Remediation:** amend the comment to state plainly that `char_offset` indexes the normalized
concatenated body and is stable only within one `prepare` run; if PR3 needs a real source
locator, capture it during extraction instead of reconstructing it after normalization.

### C. The PDF test docstring claims de-hyphenation coverage the fixture does not contain. *(Trivial)*

[test_pdf_metadata_and_text_fixture:219](tests/test_pr2_prepare.py#L219) says *"Text fixture
embeds extractable content including a soft line-break hyphen,"* but the extracted text has no
hyphen break — I dumped it. The assertion is also a three-way `or` that would pass on the title
line alone. De-hyphenation *is* covered by the separate unit test at line 122, so this is a
comment accuracy issue, not a coverage gap.

**Remediation:** drop the "soft line-break hyphen" clause, or add `experi-\nment` to the fixture
PDF and assert the de-hyphenated result from the extraction path.

### D. `_NUMERIC_FOOTNOTE` is dead code. *(Trivial)*

[normalize.py:25](src/lds_study/data/normalize.py#L25) is defined but never referenced —
`_PROSE_EXTRACTION_MARKERS` inlines the same `\[\d+\]` alternative. Ruff does not flag
module-level constants.

**Remediation:** delete it, or reference it inside `_PROSE_EXTRACTION_MARKERS`.

### E. The ePub round-trip still bypasses `run_prepare`. *(Trivial — carried from round 1)*

The plan's gate reads *"adding a single ePub to `data/raw/user/` and re-running adds its sections
with correct title/date metadata."* [test_epub_metadata_and_chunks](tests/test_pr2_prepare.py#L186-L210)
exercises `load_user_files` against a `tmp_path`, never the `run_prepare` → `sources.yaml` →
`user-byof` wiring. The scripture equivalent of this test exists
([test_prepare_fixture_scripture_via_sources_yaml](tests/test_pr2_prepare.py#L289)); the BYOF one does not.

**Remediation:** extend the existing end-to-end test with a second `user_files` source entry
pointing at a tmp BYOF dir containing the ePub, asserting both metadata and that the restricted
chunks land in `chunks.jsonl` but not in an export.

### F. Scripture normalization is now essentially a no-op — worth stating. *(Noted — no action)*

With `strip_extraction_markers=False`, the only rules that can fire on the nephi dump are NFC,
smart punctuation, soft hyphens, and `_is_heading_line`, and none of them alter any of the 41,995
verses. That is the correct outcome for a verbatim-quotation product, and the heading/marker
machinery still earns its place on the BYOF prose path. No change needed — recording it so a
future reader does not "optimize" the scripture path by re-enabling marker stripping.

## Net assessment

Merge. The three defects that would have propagated into PR3's retriever and citation validator —
corrupted verse text, silently dropped prose, ambiguous chunk ids — are fixed, and each fix is
backed by a test that would fail if it regressed. The full-corpus gate (Finding 6) is the most
valuable addition: it turns the plan's per-volume count table from a document into a check.

Findings A–E are all cosmetic or defensive and none should block PR3. If any is worth doing now
it is **A**, because it costs one line in `_doc_stem` and removes a confusing hard failure from a
BYOF layout a user is likely to produce on their first real ingest.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **31 passed in 3.49s** (was 25), offline, no GPU
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed**
- Ran `normalize_scripture` over all 41,995 dump verses → **0 altered** (round 1: 2 altered)
- Verified all 22 `known_verses.json` records: input text byte-identical to the mirror dump, and
  `expected_text` byte-identical to the raw dump text **22/22** — the new baseline is independent,
  not `normalize()` output
- Confirmed `1 John 2:23` and `Joseph Smith--History 1:2` are present in the fixture with their
  brackets intact, and that the regenerated `data/processed/chunks.jsonl` (19:04) carries `[but]`
- `test_full_dump_matches_verse_counts_when_present` **ran** (artifact present) — sha256, per-volume
  counts, and a full 41,995-chunk prepare all match `configs/verse_counts.yaml`
- Re-ran the round-1 repros: colon lead-ins now retained; `2023/talk.txt` vs `2024/talk.txt` →
  distinct ids
- New repro: `talk.txt` + `talk.md` → 1 unique id of 2, caught by `_assert_unique_chunk_ids` (Finding A)
- Dumped `sample_lesson.pdf` extraction → real text, no hyphen break (Finding C)
- Grep gates: `_NUMERIC_FOOTNOTE` referenced only at its definition; no `allow.restricted` or
  override flag anywhere in `src/`
- `git status -- data indexes models outputs` → only `data/README.md` (allowlisted); the 18MB
  artifact and 15MB `chunks.jsonl` remain ignored
