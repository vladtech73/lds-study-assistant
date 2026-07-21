# Index + RAG CLI (PR3) — Implementation Evaluation (Round 2)

*Evaluator: claude · 2026-07-20 · Round 2 · Reviews PR3 of `claude-2026-07-20.md` against the working tree (branch `pr3-index-rag-cli`, still 0 commits ahead of `main`). Follows up on [round 1](pr3-index-rag-cli-implementation-evaluation-claude-2026-07-20.md).*

## Verdict: Round-1 findings were addressed well — but the fix round exposed a Critical citation-stripping bug in the output layer.

Nine of the eleven actionable round-1 findings are genuinely fixed, and fixed properly rather than papered over. The dense-retrieval regression net now works (I re-ran the sabotage probe: forcing `ChromaDenseStore.query` to return `[]` now **fails** `test_dense_only_retrieve_returns_hash_neighbor`, where in round 1 the whole suite passed). The citation gate fails closed on empty and heading-only answers and additionally requires ≥1 valid marker. VRAM reporting switched to `mem_get_info()` device occupancy. `pull-models` snapshots are now actually loaded via the new `index/model_paths.py`. README documents `index`, `ask`, the flag set, and the exit-code table. The misleading "10/10" test names were renamed to `*_harness_wiring` with honest docstrings — the right call. 48 tests pass, ruff is clean.

Against that: `lds ask` prints its answer through `rich.Console.print` with markup enabled, and rich eats bracketed lowercase tokens. I confirmed live that a BYOF talk chunk lacking `canonical_ref`/`title`/`author` produces `status: ok` with `rendered` = `"…think celestial. [user/talk-oct2023-03/s2]"` while the terminal shows **"The speaker invites us to think celestial."** — the citation deleted. That is the exact failure mode the plan singles out as unacceptable ("stripping leaves prose that reads as sourced but is not, which is worse than an obvious failure"), reached through the display layer instead of the validator. The same mechanism deletes every chunk id from the `unsupported` refusal's source list, and model text containing a stray `[/tag]` raises an uncaught `MarkupError` that destroys the 0/2/3 exit-code contract.

Two smaller regressions came in with the fixes: `test_volume_filter_on_bm25` was absorbed into an unrelated test and no longer exists by name, and the round-1 gate hardening now guarantees the model's own prompt-prescribed refusal wording can never be returned.

Fix finding 1 before merge. It is a two-line change and it is the plan's central product guarantee.

## Round-1 finding disposition

| # (R1) | Finding | Status |
|---|---|---|
| 1 | Dense path untested; bare `except Exception → []` | **Fixed.** `test_dense_only_retrieve_returns_hash_neighbor` ([tests:109-137](tests/test_pr3_index_rag.py#L109-L137)) is a real net — verified it fails under sabotage. `backend_llamaindex.py:116-128` now splits expected soft-misses from unexpected failures and logs both. |
| 2 | 10/10 smoke gate self-referential | **Reframed as asked.** Tests renamed `test_bm25_phrase_smoke_harness_wiring` / `test_phrase_smoke_harness_wiring_bm25_only`; `smoke.py` module docstring states plainly that the committed tests "do **not** satisfy the plan's 10/10 full-corpus gate." No code change needed; gate still unrun (see finding 6). |
| 2b | README said "Index + ask arrive in PR3" | **Fixed.** `README.md:52-73` adds `index`/`ask` quickstart, flag list, and the status/exit-code table. |
| 3 | Empty answer passed the citation gate as `ok` | **Fixed, and over-delivered.** `citations.py:113-116` fails closed on `paras == []`; `passes_citation_gate` now also requires `report.valid`. Covered by `test_citation_empty_answer_fails_gate`. Verified: `''`, `'   '`, `'## Summary'` → `coverage=0.0, PASSES=False`. Side effect → finding 3 below. |
| 4 | Peak VRAM measured allocator only; `verbose or True` | **Fixed.** `vram.py` splits `device_vram_used_gb()` (`mem_get_info`, total−free) from `process_vram_allocated_gb()`; `log_peak_vram` prints both under `--verbose` and returns device occupancy. `build.py:112` now `log_peak_vram(verbose, …)`. |
| 5 | `ask`/`index` re-downloaded weights `pull-models` had cached | **Fixed.** New [model_paths.py](src/lds_study/index/model_paths.py); `build_embedder` and `build_reranker` resolve `models/{org--name}` first, pass `local_files_only=True` when local, and warn loudly when falling back to the hub. Covered by `test_resolve_model_path_prefers_local`. |
| 6 | `ARCHITECTURE.md` claimed a LlamaIndex confinement the code broke | **Fixed.** `docs/ARCHITECTURE.md:54-56` now states LlamaIndex is used only for the embedding wrapper, dense is plain `chromadb`, sparse is `rank-bm25`, and index dirs are pickle-bearing and not portable. `as_llama_index_vector_store()` deleted. Residue → finding 4. |
| 7 | `min_score` compared against three incompatible scales | **Documented, not fixed.** `configs/rag.yaml:14-16` now says the value is compared post-rerank and warns the scales differ. Acceptable deferral to PR4; the `no_evidence` unreachability is unchanged. |
| 8 | `lesson`/`talk` modes untested | **Half fixed.** `test_ask_lesson_mode_ok` added; `talk` still has no test. No per-mode `min_coverage` override. |
| 9 | `kv_cache_quant` inert | **Fixed as documentation.** `configs/models.yaml:13` marks it server-side only; `README.md:73` gives `OLLAMA_KV_CACHE_TYPE=q8_0`. Correct resolution. |
| 10 | Per-batch checkpoint rewrote the full id set | **Fixed.** `CHECKPOINT_NAME` and the checkpoint file are gone; `_embed_batches` resumes from `store.existing_ids()` upstream. Residual → finding 7. |
| 11 | BM25 pickle | **Fixed as documentation**, as recommended — noted in `ARCHITECTURE.md:56`. |
| 12 | Prompt injection via chunk text | Unchanged — still Noted, still acceptable for single-user v1. |
| 13 | Archive move mixed into the diff | Not done — the two `plans/archive/pr2-*` files are still in the working tree alongside PR3. |
| 14 | Redundant `strict` short-circuit | **Fixed.** The `if strict: break` is gone; `max_attempts = 1 if strict` carries it. |

## Completeness & accuracy by workstream

| Workstream (plan step) | Status | Evidence |
|---|---|---|
| Retriever protocol + rip-out seam (step 3) | Complete | `index/base.py` protocols unchanged; docs now describe the real dependency surface. |
| Embed + Chroma persist, resumable (step 3) | Complete | `build.py:88-107`; resume via `existing_ids()`. |
| BM25 parallel index (step 3) | Complete | Unchanged from round 1. |
| Hybrid RRF → rerank → top-8 → expand (step 3) | Complete | `hybrid.py:69-113` unchanged. |
| Query-time filters (step 3) | Complete, **coverage regressed** | Filters work; the test that asserted BM25 filter behavior lost its identity — finding 2. |
| VRAM discipline (step 3) | Complete | Generator unload + CPU rerank + device-level reporting. |
| 10/10 phrase smoke gate (step 3 done-when) | Missing-but-honest | Harness correct and honestly scoped; no full-corpus run recorded — finding 6. |
| Static system prompt, chunks in user role (step 4) | Complete | `prompts.py:16-27`. |
| Citation parse / validate / render (step 4) | **Partial — Critical** | Validator is correct; the *renderer's consumer* deletes citations — finding 1. |
| Four-path failure ladder + exit codes (step 4) | **Partial** | Paths correct and tested; exit contract breakable by `MarkupError` (finding 1) and the honest-refusal path is unreachable (finding 3). |
| `study` / `lesson` / `talk` modes (step 4) | Partial | `talk` still untested. |
| `music` / `serve` deferred | Deferred-as-planned | No change. |
| Copyright posture | Complete | `scripts/check_staged_data.py` → exit 0; nothing new tracked under `data/`, `indexes/`, `models/`. |
| Docs land with the code (step 8) | Complete | README + ARCHITECTURE + config comments all updated this round. |

## Findings (ranked)

### 1. `lds ask` silently deletes citations from its terminal output, and can crash on model text. *(Critical)*

`_emit` renders answers through rich with markup enabled:

```python
# src/lds_study/rag/ask.py:219-228
if result.status == "ok":
    console.print(result.rendered or result.answer or "")
...
else:
    console.print(result.rendered or "")
```

Rich parses `[...]` as markup. Any bracketed token beginning with a lowercase letter, `#`, `/`, or `@` is consumed and never printed. Verified directly:

```
c.print('- Alma 32:27 ([bofm/alma/32/27])')            → "- Alma 32:27 ()"
c.print('invalid marker [[bofm/alma/32/99]] visible')  → "invalid marker [] visible"
c.print('ref [user/talk-2023-10-nelson/3]')            → "ref "
c.print('answer with [/bad] closing tag')              → raises MarkupError
```

Three reachable consequences, all confirmed end to end:

**(a) Citations vanish from `status: ok` answers.** `render_human_ref` falls back to `return chunk.id` ([citations.py:54](src/lds_study/rag/citations.py#L54)) whenever a chunk has no `canonical_ref`, `author`, `title`, or `date` — i.e. exactly the BYOF conference-talk and Come, Follow Me chunks whose metadata extraction came up empty, which PR2's own stats report exists to flag. Running `run_ask` with such a chunk:

```
STATUS: ok | rendered field: 'The speaker invites us to think celestial. [user/talk-oct2023-03/s2]'
terminal output:            'The speaker invites us to think celestial.'
```

The user sees confident, sourced-sounding prose with no citation and `exit 0`. The plan's rationale for never stripping is verbatim: *"stripping leaves prose that reads as sourced but is not, which is worse than an obvious failure."* The validator honors that; the printer does not.

**(b) The refusal source list loses every chunk id.** `_plain_source_list` emits `f"- {ref} ([{chunk.id}])"` ([ask.py:209](src/lds_study/rag/ask.py#L209)). Live `unsupported` run:

```
- Alma 32:27 ()
  x
(status=unsupported)
```

The plan positions this list as the auditable fallback when synthesis is refused. Every id in it is deleted.

**(c) Uncaught `MarkupError` breaks the exit-code contract.** Model output — or, via `--show-context`, raw chunk text ([ask.py:90-95](src/lds_study/rag/ask.py#L90-L95), which prints `row['text'][:500]` unescaped) — containing an unbalanced `[/…]` raises `rich.errors.MarkupError`. `cli.py` catches only `(FileNotFoundError, ValueError, RuntimeError)`, so this escapes as a traceback and the documented 0/2/3 exit codes are lost. This is also the global security baseline's "sanitize model output before rendering" rule: LLM and BYOF-file text is being fed to a markup interpreter.

**Remediation:** Print answer, source-list, and `--show-context` text with `console.print(text, markup=False)` (or `rich.markup.escape`), keeping markup only for the framing labels the code itself writes. Add a test asserting a metadata-less chunk's citation survives to captured stdout — the current tests only inspect the `rendered` field, which is why this passed 48/48.

### 2. `test_volume_filter_on_bm25` was deleted and its assertions buried inside an unrelated test. *(High)*

Round 1's suite had a standalone `test_volume_filter_on_bm25`. It is gone:

```
$ grep -rn "test_volume_filter" tests/   → (no matches)
```

Its body now sits at the tail of `test_resolve_model_path_prefers_local` ([tests:357-373](tests/test_pr3_index_rag.py#L357-L373)), after the model-path assertions and separated from them by nothing:

```python
def test_resolve_model_path_prefers_local(tmp_path: Path) -> None:
    ...
    assert path == str(snap)
    chunks = _scripture_chunks()          # ← unrelated BM25 filter test starts here
    bm25 = BM25Index.build(chunks)
    ...
    assert all(cid in allowed for cid, _ in ranked)
```

Two problems. The name no longer describes what the test asserts, so a future failure reports "model path" when retrieval filtering broke. And because pytest stops at the first failing assertion, any regression in `resolve_model_path` silently disables the filter coverage underneath it. This looks like a merge accident during the finding-5 fix, not a decision.

**Remediation:** Split it back into `test_resolve_model_path_prefers_local` and `test_volume_filter_on_bm25`.

### 3. The gate guarantees the model's prompt-prescribed refusal wording is always discarded. *(High)*

All three prompt files instruct: *"If the retrieved sources do not support an answer, say you do not find it in the indexed sources."* The round-1 fix to `passes_citation_gate` added `if not report.valid: return False` ([citations.py:130-131](src/lds_study/rag/citations.py#L130-L131)). A compliant refusal carries no markers, so `valid == []` and the gate rejects it. Verified end to end with the real `configs/rag.yaml`:

```
STATUS unsupported  EXIT 2  ATTEMPTS 2
I could not produce a fully supported answer from the indexed sources.
Retrieved sources: …
```

So when the model does exactly what it was told, the system: burns a second full generation at temperature 0, throws away the correct answer, and substitutes a canned source dump. The final exit code (2) is defensible under the plan's table, but the behavior is not what the prompt contract promises, and it doubles generation cost on precisely the queries where the model behaved best. It is also invisible — no test covers a well-formed uncited refusal.

**Remediation:** Detect the refusal case explicitly — if the answer carries no markers *and* matches the configured refusal phrasing (or, more robustly, have the prompt emit a machine-readable `NO_EVIDENCE` sentinel), short-circuit to `status: no_evidence` / exit 3 without a retry. Add a test.

### 4. `llama-index-vector-stores-chroma` is now a dead base dependency, and the module name contradicts its own docstring. *(Low)*

`as_llama_index_vector_store()` was correctly deleted this round, so no code imports `llama_index.vector_stores.chroma` anywhere:

```
$ grep -rn "llama_index" src/  →  embedder.py:40 (docstring), embedder.py:51 (import)
$ grep -n  "llama-index"  pyproject.toml  →  lines 26, 27, 28
```

`llama-index-vector-stores-chroma>=0.2` (line 27) is pulled into every install for nothing. `llama-index-core` survives only as a transitive requirement of the embeddings package.

Meanwhile the file is still called `backend_llamaindex.py` while its docstring reads *"Chroma dense store (chromadb PersistentClient; no LlamaIndex VectorStore)"*, and it still exports `LlamaIndexChromaStore = ChromaDenseStore` — an alias to a class that has nothing to do with LlamaIndex.

**Remediation:** Drop `llama-index-vector-stores-chroma` from `pyproject.toml`; rename the module to `chroma_store.py` and delete the alias (only `build.py` and the test file import it). Consider dropping the last LlamaIndex dependency by using `sentence_transformers.SentenceTransformer` directly in `embedder.py` — `sentence-transformers` is now a declared direct dependency anyway (`pyproject.toml:31`).

### 5. `talk` mode still has no test, and outline modes still share `study`'s coverage bar. *(Low)*

`test_ask_lesson_mode_ok` landed; `mode="talk"` remains unexercised. And the round-1 concern about `min_coverage: 0.8` fighting outline-shaped output was not addressed — `_claim_paragraphs` still counts a block of discussion questions or a bulleted outline as a claim paragraph needing its own valid marker, and `citation.min_coverage` is still a single global value. The new lesson test uses a one-paragraph reply, so it does not probe the shape that would actually fail.

**Remediation:** Add `test_ask_talk_mode_ok`, plus one lesson test with a realistic multi-section outline (heading + cited exposition + uncited question list) to pin the intended behavior. If outline modes need a lower bar, add a per-mode `min_coverage` override in `rag.yaml`.

### 6. The plan's real 10/10 gate is still unrun. *(Low — carried forward, now honestly labeled)*

This is no longer a false-confidence problem — the renames and docstrings are exactly right, and `smoke.py`'s module docstring says so in the source. But PR3's done-when ("10/10 hand-picked phrases at rank 1, peak VRAM logged below 15GB") remains unsatisfied: no `lds index --profile default --smoke` output exists anywhere in the repo, and I cannot run it here (needs GPU, Ollama, and the full corpus). The README correctly flags that the smoke path uses `IdentityReranker`, so even when run it will validate `RRF → identity → top-1` rather than the `RRF → cross-encoder → top-8` pipeline `ask` uses.

**Remediation:** Paste the real `--smoke` run into the PR description with the VRAM line, and note the reranker caveat. Not a code change.

### 7. Dropping the embed checkpoint makes resume depend entirely on Chroma's own durability. *(Low)*

The round-1 fix removed `embed_checkpoint.json` and now resumes purely from `store.existing_ids()` ([build.py:89-93](src/lds_study/index/build.py#L89-L93)). That is the right call — it removes the O(n²) rewrite and the stale-checkpoint divergence. The new dependency is that a hard kill mid-embed leaves Chroma's id metadata and its HNSW segment consistent with each other; if ids are readable from the metadata store but their vectors were not yet flushed, a resumed build would skip them and produce a silently short index.

I did not reproduce a loss, and Chroma's write-ahead log is designed to cover exactly this, so I am flagging it as a residual risk of the change rather than a defect.

**Remediation:** One test — upsert a batch, discard the client without closing, reopen the directory, and assert `count()` and a `query()` round-trip both see the batch. Cheap insurance for the resume path.

### 8. Smaller items. *(Trivial)*

- `resolve_model_path` ([model_paths.py:26-28](src/lds_study/index/model_paths.py#L26-L28)) treats any non-empty directory as a complete snapshot. A `pull-models` run interrupted after one shard leaves a partial dir that is then loaded with `local_files_only=True`, failing with a confusing offline error instead of re-fetching. Check for `config.json` at minimum.
- `--verbose` help on `index` still reads "Log peak VRAM per batch" ([cli.py](src/lds_study/cli.py)); it now also gates the end-of-build VRAM line.
- `EXIT_ERROR` ([ask.py:29](src/lds_study/rag/ask.py#L29)) is defined and never used — `cli.py` hardcodes `typer.Exit(code=1)`.
- `test_ask_ok_path(tmp_path)` and `test_index_build_hash_embedder_and_hybrid_retrieve(..., monkeypatch)` take fixtures they never use.
- Carried from round 1 finding 13: the `plans/archive/pr2-*` move is still bundled into the PR3 working tree.
- Branch `pr3-index-rag-cli` is still **0 commits ahead of `main`** — the whole of PR3 remains uncommitted and there is still no reviewable diff.

## Net assessment

Round 2 is a good fix round. The remediations were taken seriously rather than minimally: the dense-path net is real (I sabotaged it and it caught the sabotage), the citation gate was hardened past what I asked for, VRAM reporting was rebuilt rather than annotated, and the two findings whose right answer was "document it, don't code it" (`kv_cache_quant`, BM25 pickle) were resolved that way instead of with busywork. The honest renaming of the smoke tests is the single best change in the round — it removes a claim the repo could not back.

What blocks merge is one bug the fix round did not touch because nothing pointed at it: the output layer. `lds ask` validates citations rigorously and then hands the result to a markup interpreter that eats them. It is invisible to the test suite because every assertion inspects `AskResult.rendered` rather than what reaches stdout, and invisible in the `study`-over-scripture happy path because capitalized refs like `Alma 32:27` survive while lowercase chunk ids do not — so it degrades exactly on the BYOF conference-talk corpus that justifies the project.

**Fix before merge:** 1 (two-line change plus a stdout-level test), 2 (untangle the merged test). **Worth fixing before merge, cheap:** 3 — the prompt and the gate currently contradict each other. **Defer to PR4:** 5, 6, and the carried-over `min_score` scale question. **Cleanup whenever:** 4, 7, 8.

Once finding 1 is fixed, add at least one test that asserts on captured console output rather than on the result dataclass. The class of bug it would have caught is the one this PR is least able to afford.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **48 passed in 6.02s** (was 45 in round 1)
- `.venv/Scripts/python.exe -m ruff check src tests scripts` → **All checks passed!**
- `.venv/Scripts/python.exe scripts/check_staged_data.py` → exit 0, no allowlist violations
- **Dense-path sabotage probe (re-run):** forced `ChromaDenseStore.query` to `return []` → `test_dense_only_retrieve_returns_hash_neighbor` **FAILED** (`assert [] ` on `RetrievalResult(hits=[])`), 1 failed / 15 passed. Round 1's equivalent probe passed 13/13. File restored, sha1 verified (`6f488170dda5841264b3bbc5ffbbb0c4a755a5dd`).
- **Citation-stripping probe (finding 1a):** `run_ask` with a `Chunk` lacking `canonical_ref`/`title`/`author` → `STATUS: ok`, `rendered='…think celestial. [user/talk-oct2023-03/s2]'`, terminal output `'The speaker invites us to think celestial.'` — citation absent.
- **Refusal-list probe (finding 1b):** `unsupported` path printed `- Alma 32:27 ()` — chunk id deleted.
- **Rich markup probe:** `[bofm/alma/32/27]` → consumed; `[[bofm/alma/32/99]]` → `[]`; `[user/talk-…]` → consumed; `[Alma 32:27]` → survives (uppercase); `[/bad]` → raises `MarkupError`.
- **Honest-refusal probe (finding 3):** `validate_citations('I do not find this in the indexed sources.', …)` → `valid=[], invalid=[], coverage=0.0, PASSES=False`; full `run_ask` → `STATUS unsupported, EXIT 2, ATTEMPTS 2`.
- **Empty-answer gate (R1 finding 3 regression check):** `''`, `'   '`, `'## Summary'` → `coverage=0.0`, gate `False`.
- Grep gates: `grep -rn "test_volume_filter" tests/` → **no matches**. `grep -rn "llama_index" src/` → only `embedder.py:40,51`. `grep -n "llama-index" pyproject.toml` → lines 26-28 (`vector-stores-chroma` now unimported).
- `git rev-list --count main..HEAD` → **0**; `git status --short` → 11 modified/deleted, 20 untracked; nothing under `data/`, `indexes/`, `models/`.
- Not run (require GPU + full corpus + Ollama): `lds index --profile default --smoke`, live `lds ask`, `scripts/check_env.py`.
