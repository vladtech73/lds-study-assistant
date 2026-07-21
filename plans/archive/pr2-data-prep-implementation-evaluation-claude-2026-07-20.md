# PR2 — Data Prep + Fixtures — Implementation Evaluation

*Evaluator: claude · 2026-07-20 · Reviews the uncommitted PR2 working tree against `claude-2026-07-20.md` (step 2 / PR2).*

## Verdict: Substantially complete and unusually well-evidenced, but two silent text-corruption bugs and one chunk-id collision should be fixed before PR3 builds on this output.

Every PR2 deliverable named in the plan exists and runs: `configs/sources.yaml` carries a real
verified mirror, the sha256 manifest works end-to-end against a genuine 18MB download, and
`lds prepare --scripture-only` produced exactly 41,995 verse chunks matching the committed
`configs/verse_counts.yaml` per-volume table (I re-derived those counts from the raw dump —
they are correct, not remembered). 25 tests pass offline, ruff is clean.

The problems are in the normalizer and the prose chunker, not the plumbing. Normalization
deletes canonical bracketed text from 2 real verses; prose chunking silently discards
paragraphs that end in a colon and collides chunk ids across same-named files. The
"character-for-character" verse test is circular and would not catch any of this.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| `sources.yaml` with verified licenses | Complete | [configs/sources.yaml](configs/sources.yaml) — 2 entries with `license`, `license_url`, `verified_on`, `redistributable`, `expected_sha256`; mirror choice documented in [docs/LEGAL.md](docs/LEGAL.md) with residual-risk paragraph. Resolves the plan's "public-domain mirror choice (gates PR2)" open question. |
| `data/manifest.py` license enforcement | Complete | [manifest.py:32-49](src/lds_study/data/manifest.py#L32-L49) refuses `unverified` **and** missing `license_url`/`verified_on` (stricter than the plan). No override flag anywhere — grep for `allow.restricted` returns nothing. |
| sha256 download manifest + `--refresh` | Complete, live-verified | [data/raw/public/MANIFEST.json](data/raw/public/MANIFEST.json) holds url + sha256 + `retrieved_at`; recomputed digest of the on-disk artifact matches `configs/sources.yaml` `expected_sha256` exactly. Drift raises in three places ([public_scripture.py:109-135](src/lds_study/data/sources/public_scripture.py#L109-L135), [:220-228](src/lds_study/data/sources/public_scripture.py#L220-L228)). |
| `sources/public_scripture.py` | Complete | Local-path, URL, dir and zip paths handled; apparatus is absent from the dump by construction and stripped again in normalize. |
| `sources/user_files.py` (BYOF) | Complete | `.epub/.pdf/.html/.htm/.txt/.md` dispatch, ePub OPF metadata, PDF `/CreationDate` parse, `.meta.json` sidecar fallback. |
| `normalize.py` | **Partial — corrupts 2 canonical verses** | See Finding 1. |
| `chunk_scripture.py` | Complete | Verse-atomic, id `bofm/alma/32/27` exactly as specified, `canonical_ref` from mirror `verse_title`. |
| `chunk_prose.py` | **Partial** | Section split + overlap windows work, but drops colon-terminated paragraphs (Finding 2) and emits colliding ids (Finding 3); `paragraph_anchor` is a window index, not a source anchor (Finding 5). |
| `lds prepare` CLI | Complete | [cli.py](src/lds_study/cli.py) — `--stats`, `--refresh`, `--scripture-only`, `--source`; exits 1 with a readable message on `UnverifiedSourceError`/`ManifestError`. |
| Fixture-driven acceptance tests | **Partial** | 13 PR2 tests, all offline/no-GPU. Fixtures are genuine (byte-identical to the real dump — I diffed all 63 records). But the character-for-character test is circular (Finding 4) and no test binds prepare output to `verse_counts.yaml` (Finding 6). |
| Restricted-never-exported test | Complete | [test_pr2_prepare.py:137-185](tests/test_pr2_prepare.py#L137-L185) — asserts every exported row is `redistributable: true` and no `user-byof` rows survive. |
| Stats report | Complete for scripture, weak for prose | `prepare_stats.json` shows `empty_dropped_total: 0`, token histogram per source. Prose content loss is not counted (Finding 2). |
| Docs updated with the code | Complete | README quickstart, `data/README.md`, `docs/LEGAL.md` mirror table — no "PR2 arrives later" text left stale. |

## Findings (ranked)

### 1. Footnote-marker regex deletes canonical bracketed words from scripture text. *(High)*

[normalize.py:24-32](src/lds_study/data/normalize.py#L24-L32) strips `\[\w{1,3}\]` as a
footnote marker. In this dump, brackets are also used for **canonical editorial insertions**,
and the pattern eats the short ones:

```
1 John 2:23  raw: "...hath not the Father: [but] he that acknowledgeth..."
             out: "...hath not the Father: he that acknowledgeth..."
JS-H 1:2     raw: "...as they at present exist, being now [1838] the eighth year..."
             out: "...as they at present exist, being now the eighth year..."
```

Verified across the full corpus: 5 verses contain `[`, 2 are silently altered. The behavior is
also *inconsistent* — D&C 109:2 `[Kirtland]`, D&C 110:14 `[Elijah]` and D&C 131:2's long
bracket survive only because they exceed 3 word characters. For a product whose central promise
is verbatim quotation with exact citation, emitting a verse that differs from the text it cites
is the exact failure mode the plan's risk section calls "the core product risk."

Worse, the test suite *enforces* the bug: `assert "[" not in chunk.text`
([test_pr2_prepare.py:64](tests/test_pr2_prepare.py#L64)) and
`assert "[a]" not in chunks[0].text` ([:280](tests/test_pr2_prepare.py#L280)).

**Remediation:** restrict the bracket rule to superscript/footnote-letter forms actually
produced by extraction (e.g. only `\[\d+\]`, and only in prose loaded from PDF/ePub — the nephi
dump has no footnote markers to strip in the first place). Add a regression test pinning
1 John 2:23 and JS-H 1:2 to their raw text. The `(?<!\w)\*\d*` rule is unexercised on this
corpus (0 verses contain `*`) — keep it prose-only too.

### 2. Prose chunker silently discards any paragraph ending in a colon. *(High)*

[chunk_prose.py:36-44](src/lds_study/data/chunk_prose.py#L36-L44) treats any line ≤80 chars
that ends in `:` as a heading and `continue`s — the line's text never enters `buf`. Conference
prose is full of lead-ins like *"President Nelson closed with this invitation:"*. Reproduced:

```
input  : "The Savior taught three things:" / <paragraph> / "President Nelson closed with this invitation:"
chunks : 1 chunk, heading="The Savior taught three things", text=<paragraph only>
lost   : both colon lines absent from every chunk text; the trailing one produces no chunk at all
empty_dropped = 0
```

So `--stats` reports zero drops while text has been removed — the opposite of the plan's
"so silent extraction failures are visible." A trailing colon-line at end of document
disappears entirely (flush finds an empty body).

**Remediation:** require a stronger heading signal (markdown `#`, all-caps, or a following
blank line *and* no terminal colon mid-sentence); at minimum, keep detected heading lines in
the section body text as well as in `heading`, and count discarded lines into
`PrepareStats.empty_dropped`.

### 3. Prose chunk ids collide across identically-named files. *(High)*

[user_files.py:78](src/lds_study/data/sources/user_files.py#L78) derives `doc_stem` from
`path.stem` only, and `chunk_prose` numbers `part` from 1 per file, so the id is
`{source_id}/{stem}/{n}`. Two files with the same stem in different subdirectories produce
identical ids. Reproduced with `2023/talk.txt` and `2024/talk.txt` → both `user-byof/talk/1`,
1 unique id for 2 chunks. Gospel Library exports routinely repeat stems (per-year folders,
`01.txt`, `nelson.html`).

This is latent now but breaks PR3 directly: `citations.py` verifies emitted `[[id]]` markers
against the retrieved set, and a duplicate id resolves a citation to the wrong talk — false
attribution presented as validated.

**Remediation:** build `doc_stem` from the path relative to the BYOF root (slugified, e.g.
`2023-talk`), or append a short content hash. Add a `prepare`-level assertion that
`len({c.id}) == len(chunks)` and fail loudly on collision.

### 4. The "character-for-character" verse test is circular. *(High)*

[test_pr2_prepare.py:67-75](tests/test_pr2_prepare.py#L67-L75) asserts
`chunk.text == normalize_text(record["scripture_text"])` — both sides run the same normalizer
over the same input, so the assertion is a tautology. It passes for any normalizer, including
one that deletes every third word. The plan required "~20 known verses match **reference text**
character-for-character"; this does not test that.

The fixtures themselves are good — I verified all 20 records and all 43 Alma records are
byte-identical to the mirror dump — so the fix is cheap.

**Remediation:** commit an `expected_text` field (or a sibling expected-chunks JSON) in
`known_verses.json` holding the hand-checked target string, and compare `chunk.text` against
that literal. This is also the test that would have caught Finding 1.

### 5. `paragraph_anchor` does not anchor to a paragraph. *(Low)*

[chunk_prose.py:113](src/lds_study/data/chunk_prose.py#L113) sets
`paragraph_anchor = f"{doc_stem}-p{part}"`, where `part` is a running section/window counter.
It cannot be used to locate the text in the user's source file, which is what the plan's
"carry paragraph anchors for citation" is for. Related: windows are re-joined with `" ".join`
([:96](src/lds_study/data/chunk_prose.py#L96)), flattening paragraph breaks so the information
needed to reconstruct anchors is destroyed at the same time.

**Remediation:** either record a real offset (character index or paragraph ordinal within the
source document) or rename the field to `window_index` so PR3 does not build citation
rendering on a false promise.

### 6. No test binds `prepare` output to the committed verse-count table. *(Low)*

`configs/verse_counts.yaml` is the plan's stated gate ("assert against a committed per-volume
count table, not a remembered ~41k"), but
[test_verse_counts_table_committed](tests/test_pr2_prepare.py#L262-L268) only asserts the YAML
file contains the numbers the test hardcodes — it never compares against a prepare run. The
real check happened manually (and passes: I recounted the dump — ot 23145 / nt 7957 /
bofm 6604 / dc 3654 / pgp 635 = 41995, matching the file exactly), but nothing re-runs it.

**Remediation:** add an opt-in test that `pytest.skip`s when
`data/raw/public/nephi-scriptures/…` is absent and otherwise asserts per-volume counts and the
artifact sha256. Offline CI stays green; a local full prepare regains the gate.

### 7. PDF fixture proves metadata only; the PDF text path is untested. *(Low)*

`sample_lesson.pdf` (765 bytes) has no extractable text — the code comments say so
([user_files.py:158](src/lds_study/data/sources/user_files.py#L158)) — and
[test_pdf_metadata](tests/test_pr2_prepare.py#L129-L134) asserts title/author/date only. So
de-hyphenation (`_DEHYPHEN`, the one normalizer rule that exists specifically for PDF
extraction) has no test at all, and the plan's "one small PDF … with expected chunk output"
is only half met.

**Remediation:** generate a fixture PDF with an embedded base-14 font containing a
line-broken `experi-\nment`, and assert both the de-hyphenated chunk text and the metadata.

### 8. `load_user_files` returns silently when the BYOF directory is missing. *(Trivial)*

[user_files.py:58-60](src/lds_study/data/sources/user_files.py#L58-L60) returns empty stats with
no message. On a fresh clone `data/raw/user/` exists, so this mostly affects misconfigured
`path_or_url` — a typo'd path looks like "no user files yet."

**Remediation:** emit a one-line warning naming the resolved path.

### 9. Legal posture is stronger than the plan required. *(Noted — no action)*

`assert_source_ingestible` rejects missing `license_url`/`verified_on` in addition to
`license: unverified`; `docs/LEGAL.md` records the mirror's apparatus omissions and states the
"no Official Declarations in this dump" finding explicitly (I confirmed: the dump has no OD
records). The `--allow-restricted` escape hatch is absent, and `filter_exportable` has no
parameter that could reintroduce it. This is the part of PR2 that most needed to be right, and
it is.

## Net assessment

Merge-ready on structure, not on text fidelity. Findings 1–3 all corrupt or mis-key the corpus
that PR3's retriever and citation validator will treat as ground truth, and each is cheap to
fix now and expensive to discover later through a wrong citation. Finding 4 is what let 1 and 2
through, so fix it in the same pass — a real expected-text fixture is the regression net the
plan actually asked for.

Findings 5–8 can ride into PR3 as long as 5 is renamed rather than silently relied upon.
Nothing here requires re-litigating a plan decision; the mirror choice, the id scheme, and the
no-override legal enforcement are all landed as specified.

Suggested order before PR3: Finding 4 (real expected text) → Finding 1 (verified by 4) →
Finding 3 (id uniqueness assertion) → Finding 2 (heading heuristic + counted drops).

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **25 passed in 2.94s**, no network, no GPU
- `.\.venv\Scripts\python.exe -m ruff check .` → **All checks passed**
- `sha256sum data/raw/public/nephi-scriptures/lds-scriptures-json.txt` →
  `8797555c…bd7e8`, matches `configs/sources.yaml`, `configs/verse_counts.yaml`,
  `docs/LEGAL.md`, and `MANIFEST.json` — the pinned hash is real, not asserted
- Recounted the raw dump by volume → ot 23145 / nt 7957 / bofm 6604 / dc 3654 / pgp 635,
  total 41995 = `configs/verse_counts.yaml` and `data/processed/prepare_stats.json`
  (`chunk_count: 41995`, `empty_dropped: 0`) exactly
- Diffed all 43 `alma_32.json` and all 20 `known_verses.json` fixture records against the
  dump → **0 mismatches** (fixtures are genuine, not hand-written)
- Ran `normalize_text` over all 41,995 verses → 2 altered (Finding 1); 5 verses contain `[`,
  0 contain `*`
- Reproduced the colon-heading content loss and the `user-byof/talk/1` id collision with
  standalone scripts (Findings 2, 3)
- `git status` → no tracked files added under `data/`, `indexes/`, `models/`, `outputs/`;
  `data/processed/chunks.jsonl` (41,995 lines) and the 18MB artifact are correctly ignored
- Grep gates: no `allow.restricted` / override flag in `src/`; `filter_exportable` is the only
  export path and is unconditional
