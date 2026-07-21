# Index + RAG CLI (PR3) — Implementation Evaluation

*Evaluator: claude · 2026-07-20 · Round 1 · Reviews PR3 of `claude-2026-07-20.md` against the working tree (branch `pr3-index-rag-cli`, all changes uncommitted).*

## Verdict: Structurally complete, but the quality gates do not measure what the plan asked them to measure.

Every PR3 artifact named in the plan exists and is wired end to end: `index/base.py` protocols, Chroma dense store, BM25, RRF hybrid, neighbor expansion, prompts for all three v1 modes, citation validate/render, the four-path ask ladder with exit codes 0/2/3, and `lds index` / `lds ask` on the Typer CLI. 45 tests pass, ruff is clean, and the copyright gate still holds. What is *not* sound is the verification story. The dense retrieval path can be stubbed to return nothing and the entire PR3 suite still passes (proved below); the "10/10 phrase smoke" runs against a 60-verse fixture corpus that contains the answer verses and almost nothing else; the citation gate passes an empty answer with `status: ok`; and the peak-VRAM number the plan uses as a 15GB gate measures the PyTorch allocator only, which is ~0 during `ask` because the generator lives in Ollama.

Two concrete pre-merge defects sit beneath that: `lds ask` will re-download BGE-M3 and the reranker from Hugging Face even after `lds pull-models` put them in `models/`, and `README.md` still tells the reader "Index + ask arrive in PR3" with no `ask` usage, exit codes, or `--strict` documented — which is the plan's own success criterion ("on a fresh clone"). Fix findings 1–5 before merge; the rest can ride to PR4.

## Completeness & accuracy by workstream

| Workstream (plan step) | Status | Evidence |
|---|---|---|
| **Retriever protocol + rip-out seam** (step 3, "LlamaIndex surface area") | Partial | [base.py](src/lds_study/index/base.py) defines `DenseStore`/`Embedder`/`Reranker`/`Retriever` protocols cleanly. But `docs/ARCHITECTURE.md:57` claims "LlamaIndex is confined to `index/backend_llamaindex.py`" while [embedder.py:51](src/lds_study/index/embedder.py#L51) imports `llama_index.embeddings.huggingface`. See finding 6. |
| **Embed + Chroma persist, resumable** (step 3) | Complete | [build.py:236-273](src/lds_study/index/build.py#L236-L273) checkpoints per batch; `ChromaDenseStore` persists under `indexes/{profile}/chroma/`. Verified live: upsert → query → metadata filter all return correct ids (manual probe, chromadb 1.5.9). |
| **BM25 parallel index** (step 3) | Complete | [bm25_index.py](src/lds_study/index/bm25_index.py), pickled to `indexes/{profile}/bm25.pkl` with a `.meta.json` sidecar. |
| **Hybrid RRF → rerank → top-8 → expand** (step 3) | Complete | [hybrid.py:69-113](src/lds_study/index/hybrid.py#L69-L113); [expand.py](src/lds_study/index/expand.py) reconstructs neighbor ids as `{volume}/{book}/{chapter}/{verse}`, matching PR2's `chunk_id()`. |
| **Query-time filters** (step 3) | Complete | `volume` / `book` / `source_type` / `date_from` / `date_to` on both the Chroma `where` clause and a Python-side id allowlist; all five surfaced as `lds ask` flags (`cli.py`). |
| **VRAM discipline** (step 3) | Partial | Generator unload before embed is real ([vram.py:39-53](src/lds_study/index/vram.py#L39-L53)); reranker defaults to CPU via `rag.retrieval.reranker_device`; embedder and reranker are never co-resident (index smoke uses `IdentityReranker`). But the reported number is wrong — finding 4. `kv_cache_quant` in `models.yaml` is never read — finding 9. |
| **10/10 phrase smoke gate** (step 3 done-when) | **Missing as specified** | Gate exists ([smoke.py](src/lds_study/index/smoke.py)) but the committed tests run it over a ~60-verse fixture set built from the same 22 verses the phrases target — findings 1 and 2. |
| **Static system prompt, chunks in user role** (step 4) | Complete | [prompts.py:16-27](src/lds_study/rag/prompts.py#L16-L27) loads from `prompts/*.md`; `build_user_message` puts context in the user turn. All three v1 modes present. |
| **Citation parse / validate / render** (step 4) | Partial | [citations.py](src/lds_study/rag/citations.py) never strips invalid markers (test-proven, `test_citation_invalid_marker_not_stripped`). But the coverage gate has an open bottom — finding 3. |
| **Four-path failure ladder + exit codes** (step 4) | Partial | All four paths implemented in [ask.py:86-174](src/lds_study/rag/ask.py#L86-L174) and unit-tested against `ScriptedGenerator`. The `no_evidence` path is unreachable in the shipped config — finding 5. |
| **`study` / `lesson` / `talk` modes** (step 4) | Partial | Prompt files exist; **no test exercises `lesson` or `talk`**, and the 0.8 coverage gate is a poor fit for outline output — finding 8. |
| **`music` and `serve` stayed deferred** (out of scope) | Deferred-as-planned | No `serve` command, no hymn code. `cli.py` still stubs `eval` for PR4. |
| **Copyright posture unchanged** | Complete | `.gitignore` allowlist intact; `scripts/check_staged_data.py` → exit 0, no violations. Nothing under `data/`, `indexes/`, `models/` newly tracked. |
| **Docs land with the code** (step 8) | **Missing** | `README.md:53` — "Index + ask arrive in PR3." Finding 2b. |

## Findings (ranked)

### 1. The entire dense-retrieval path is untested — it can return nothing and every test still passes. *(Critical)*

`ChromaDenseStore.query` is the only consumer of the embedder at query time, and it swallows every exception:

```python
# src/lds_study/index/backend_llamaindex.py:116-120
try:
    result = self._collection.query(**kwargs)
except Exception:
    # Empty collection or filter mismatch
    return []
```

A bare `except Exception → []` means a schema change, a malformed `where` clause, a dimension mismatch, or a corrupt collection all degrade silently to BM25-only. Nothing logs, nothing warns, and `lds ask` still answers — just with worse retrieval that no one can see.

The tests do not catch this because none of them depend on dense results. `test_phrase_smoke_harness_bm25_dominant` uses an explicit `EmptyDense` stub ([test_pr3_index_rag.py:341-352](tests/test_pr3_index_rag.py#L341-L352)), and `test_index_build_hash_embedder_and_hybrid_retrieve` asserts a hit on `"experiment upon my words"` — an exact BM25 substring match — so BM25 alone satisfies it.

**Verified.** I temporarily forced `ChromaDenseStore.query` to `return []` unconditionally and re-ran the PR3 suite:

```
13 passed in 2.61s
```

(File restored; sha1 confirmed identical to the pre-edit copy.)

So PR3's headline feature — hybrid dense+sparse retrieval — has zero regression coverage. The dense store itself does work; I verified it by hand (upsert 3 chunks with `HashEmbedder`, query returns them ranked, `volume` filter returns `[]` for a non-matching value). The defect is that nothing keeps it working.

**Remediation:** (a) Replace the bare `except Exception` with a narrow catch plus a `console.print` warning that names the exception, so silent BM25-only degradation is visible; (b) add a test that asserts a dense-only hit — build a `HybridRetriever` with `bm25_top_k=0` (or a stub BM25 returning `[]`) over the fixture corpus and assert the correct id comes back through Chroma.

### 2. The "10/10 phrase smoke" gate is self-referential — it proves plumbing, not retrieval. *(High)*

The plan's PR3 gate is "a smoke query for a distinctive phrase returns the correct verse at rank 1 for 10/10 hand-picked phrases" over the built index (~41k verses). What is committed is a 10-phrase list in `tests/fixtures/index/phrase_smoke.json` whose target ids are:

`bofm/2-nephi/2/25`, `bofm/1-nephi/3/7`, `bofm/alma/32/27`, `ot/psalms/23/1`, `nt/john/3/16`, `nt/matthew/5/14`, `ot/genesis/1/1`, `bofm/mosiah/3/19`, `bofm/2-nephi/2/25`, `bofm/alma/32/21`

Every one of those verses is in `tests/fixtures/scripture/known_verses.json` (22 verses), and `_scripture_chunks()` ([test_pr3_index_rag.py:31-41](tests/test_pr3_index_rag.py#L31-L41)) builds the test corpus from exactly that file plus `alma_32.json`. So `test_bm25_phrase_smoke_10_of_10` and `test_phrase_smoke_harness_bm25_dominant` search a ~60-verse haystack for phrases that are near-verbatim substrings of the 22 needles that were placed there. 10/10 is not evidence of anything.

The test file is honest about this in a docstring ("Real BGE-M3 10/10 is exercised via `lds index --smoke` after a full embed"), which is the right disclosure — but it means the plan's gate is **unmet**, not met, and the PR should say so rather than let a green suite imply otherwise.

Compounding it: `lds index --smoke` builds its retriever with `IdentityReranker()` ([build.py:139-153](src/lds_study/index/build.py#L139-L153)) to avoid co-resident weights. That is defensible VRAM hygiene, but it means the one gate that *does* run against the real corpus validates a pipeline (`RRF → identity → top-1`) that `lds ask` never uses (`RRF → cross-encoder → top-8`).

**Remediation:** Rename the fixture tests to something like `test_phrase_smoke_harness_wiring` so the name does not claim the gate; record an actual `lds index --profile default --smoke` run against the full corpus in the PR description (with the caveat that it used the identity reranker); and add a second `--smoke-rerank` mode, or defer the real 10/10 claim to PR4's eval where the reranker is in the loop.

### 2b. `README.md` still says index and ask do not exist. *(High)*

`README.md:53`: *"`prepare` writes `data/processed/chunks.jsonl` (gitignored). Index + ask arrive in PR3."* The Quick start block stops at `prepare`. Nothing in `README.md` or `docs/` documents `lds ask` usage, `--strict`, `--show-context`, `--json`, `--volume/--book/--source-type/--date-from/--date-to`, or what exit codes 2 and 3 mean. The only mention anywhere is a single string in an ASCII diagram (`docs/ARCHITECTURE.md:16`, "or refuse (exit 2/3)").

This matters because the plan's stated success criterion is a *fresh clone* reaching a cited answer, and step 8 requires "docs land with the code they describe."

**Remediation:** Extend the Quick start with `lds index --profile default` and a worked `lds ask` example including its citation output, and add a short "Answer statuses and exit codes" table mirroring the plan's step-4 table.

### 3. An answer with no citations at all passes the citation gate as `status: ok`. *(High)*

`validate_citations` computes coverage as:

```python
# src/lds_study/rag/citations.py:107
coverage = (cited / len(paras)) if paras else (1.0 if not markers else 0.0)
```

`_claim_paragraphs` drops blank blocks and heading-only blocks. So when the model returns an empty string, whitespace, or a bare heading, `paras == []` and `markers == []` → coverage `1.0`, `invalid == []` → `passes_citation_gate` returns `True` → `AskResult(status="ok", exit_code=0)`.

Verified:

```
''           coverage=1.0 paras=0 PASSES=True
'## Summary' coverage=1.0 paras=0 PASSES=True
'   '        coverage=1.0 paras=0 PASSES=True
'Alma taught faith is a seed.'  coverage=0.0 PASSES=False   (correct)
```

`OllamaGenerator.complete` raises on empty content, which shields the common case — but the gate is the safety property here, and it is defined so that "produced nothing" and "produced a heading" are indistinguishable from "fully cited." That is exactly the false-confidence failure mode the plan's step-4 table was written to prevent.

**Remediation:** Fail closed — if `paras` is empty *or* `valid` is empty while the answer contains non-whitespace prose, treat it as a coverage failure (`0.0`) rather than a pass. Add the three cases above as unit tests.

### 4. Reported "peak VRAM" measures the PyTorch allocator only, so the plan's 15GB gate is measuring the wrong thing. *(High)*

```python
# src/lds_study/index/vram.py:24
return float(torch.cuda.max_memory_allocated()) / (1024**3)
```

`max_memory_allocated()` reports tensors allocated by *this process's* PyTorch caching allocator. It excludes: the CUDA context (~0.3–0.6GB), allocator-reserved-but-unallocated blocks, any non-PyTorch CUDA consumer, and — decisively — **Ollama, which holds the ~9GB generator in a separate process**.

Consequences:
- During `lds ask` with the default `reranker_device: cpu`, nothing is on the GPU in-process, so `AskResult.peak_vram_gb` is `0.0`, not `None`. `run_ask` faithfully reports 0.0 GiB while ~9GB is resident in Ollama. That is worse than reporting nothing.
- `build.py:117` writes `log_peak_vram(verbose or True, ...)` — `verbose or True` is unconditionally `True`, so `lds index` always prints the number regardless of `--verbose`. Dead condition, and it prints the misleading figure by default.
- The plan's done-when — "with peak VRAM logged below 15GB" — cannot be satisfied or falsified by this metric.

**Remediation:** Report device-level occupancy with `torch.cuda.mem_get_info()` (`total - free`) as the headline number, keep `max_memory_allocated()` as a secondary in-process figure, and label both. Fix `verbose or True` → `verbose`.

### 5. `lds ask` and `lds index` ignore the weights `lds pull-models` downloaded, and will hit the network. *(High)*

`scripts`/`pull_models.py` snapshots the embedder and reranker into `models/BAAI--bge-m3` and `models/BAAI--bge-reranker-v2-m3` (`pull_models.py:77-83`). But PR3's loaders pass the **repo id**, not that path:

- [embedder.py:105-116](src/lds_study/index/embedder.py#L105-L116) — `model_id = section.get("id") or "BAAI/bge-m3"` → `HuggingFaceEmbedding(model_name="BAAI/bge-m3")`
- [rerank.py:61-68](src/lds_study/index/rerank.py#L61-L68) — `CrossEncoder("BAAI/bge-reranker-v2-m3")`

So both re-resolve through the HF hub cache, duplicating ~4–5GB of downloads and requiring network on first `index`/`ask` even on a machine that already ran `pull-models`. `HuggingFaceEmbedder` even accepts a `local_files_only` flag ([embedder.py:47](src/lds_study/index/embedder.py#L47)) that `build_embedder` never sets.

This collides with two plan constraints: "Model download happens *in scripts*, never manually … into a gitignored `models/`", and "runs entirely on one RTX 5070 Ti 16GB, no cloud calls."

**Remediation:** Resolve `models_dir / id.replace("/", "--")` first and pass that local path when it exists, falling back to the hub id with an explicit warning; thread `local_files_only=True` when the local snapshot is present.

### 6. `docs/ARCHITECTURE.md` states an invariant the code violates. *(Low)*

`docs/ARCHITECTURE.md:57`: *"LlamaIndex is confined to `index/backend_llamaindex.py` behind `index/base.py`."* False — [embedder.py:51](src/lds_study/index/embedder.py#L51) does `from llama_index.embeddings.huggingface import HuggingFaceEmbedding`. That is the rip-out seam the plan's "LlamaIndex surface area" section exists to protect, and it is now leaking into a second module.

Separately, the plan named four LlamaIndex things in use (`TextNode`, `ChromaVectorStore`, `VectorIndexRetriever`, BM25 retriever). The implementation uses **none** of them: `chromadb` is driven directly, `rank_bm25` directly, no `TextNode`. `as_llama_index_vector_store()` ([backend_llamaindex.py:133-137](src/lds_study/index/backend_llamaindex.py#L133-L137)) is dead code, and `llama-index-vector-stores-chroma` is now a dead base dependency. The only real LlamaIndex usage is the HF embedding wrapper — itself a thin shim over `sentence-transformers`.

This is a *good* deviation (less framework), but the docs and `pyproject.toml` now overstate the dependency.

**Remediation:** Either move the embedder to `sentence-transformers` directly and drop all three `llama-index-*` deps, or restate the invariant honestly as "LlamaIndex is used only in `backend_llamaindex.py` and `embedder.py`." Remove `as_llama_index_vector_store()` if nothing calls it.

### 7. `min_score` compares against three incompatible score scales. *(Low)*

`retrieval.min_score` gates the `no_evidence` path, and PR4 is meant to raise it off 0.0. But the value it is compared against ([hybrid.py:107](src/lds_study/index/hybrid.py#L107)) depends entirely on which reranker is installed:

| Configuration | Score range at the `min_score` comparison |
|---|---|
| No reranker | RRF scores, ≈ `1/(60+1)` = 0.016 down |
| `IdentityReranker` (index smoke, tests) | `n, n-1, … 1` — integers up to the pool size |
| `CrossEncoderReranker` (production `ask`) | Whatever `CrossEncoder.predict` emits for this checkpoint — sigmoid `(0,1)` or raw logits including negatives |

A single number cannot be meaningful across all three, and nothing documents which one `min_score` is expressed in. Whatever PR4 measures will therefore silently mean something different in `lds index --smoke` than in `lds ask`.

Related: because the default is `0.0` and Chroma returns `top_k` results for *any* query regardless of relevance, the dense leg always produces hits, so **the `no_evidence` path (exit 3) is unreachable in the shipped config**. The plan's adversarial case ("what did the prophet say last Tuesday") will land on `unsupported` (exit 2) instead — which the plan permits ("`no_evidence` or `unsupported`"), so this is not a contract break, but it does mean the exit-3 branch is dead outside `test_ask_no_evidence`, which reaches it only by stubbing a retriever that returns `[]`.

**Remediation:** Normalize reranker output to a fixed `[0,1]` scale in `Reranker` implementations (document it in the protocol docstring), and note in `rag.yaml` which scale `min_score` is in. Have PR4 set it from measured cross-encoder scores.

### 8. `lesson` and `talk` modes are shipped with zero tests and a coverage gate that fights their output shape. *(Low)*

`prompts/lesson_assistant.md` asks for "a short lesson outline with discussion questions," but `_claim_paragraphs` counts every non-heading block — including a block of discussion questions or a bulleted outline — as a claim paragraph needing a valid marker. At `min_coverage: 0.8`, a lesson outline with an uncited questions section and an uncited closing thought fails the gate, retries once, then refuses with exit 2. No test covers `mode="lesson"` or `mode="talk"` at all; every `run_ask` test uses the default `study`.

**Remediation:** Add one `run_ask` test per mode with a representative scripted outline reply; if outline modes legitimately need a lower bar, give `citation.min_coverage` a per-mode override in `rag.yaml` rather than discovering the mismatch at runtime.

### 9. `kv_cache_quant` is configured but never reaches the generator. *(Low)*

`configs/models.yaml` sets `kv_cache_quant: "q8_0"`, and the plan's hardware constraint calls for "quantized KV cache (Q8) in the Ollama/llama.cpp options." `OllamaGenerator.complete` sends only `temperature` and `num_ctx` ([generate.py:33-36](src/lds_study/rag/generate.py#L33-L36)). `num_ctx` capping landed; KV quantization did not.

Ollama exposes KV cache type as a **server-level** setting (`OLLAMA_KV_CACHE_TYPE`), not a per-request option, so this may not be fixable from the client at all — but the config key currently reads as wired when it is inert.

**Remediation:** Either document `OLLAMA_KV_CACHE_TYPE=q8_0` in the README hardware section and mark the key `# server-side; set via env` like the existing `quant: # documentation-only` comment, or drop the key.

### 10. Per-batch checkpoint rewrites the full id set, and can silently no-op a rebuild. *(Low)*

[build.py:267-270](src/lds_study/index/build.py#L267-L270) writes `json.dumps({"completed_ids": sorted(done_ids)})` after **every** batch. At ~41k chunks and `batch_size: 32` that is ~1,280 writes of a list growing to ~1MB — roughly O(n²) bytes, several hundred MB of pointless IO on a full scripture embed.

It is also redundant: `store.existing_ids()` already reads completion state from Chroma itself (`build.py:93`), which is the durable source of truth. Worse, the two can disagree — if `indexes/{profile}/chroma/` is removed but `embed_checkpoint.json` survives (a plausible manual cleanup), `existing` is empty so `pending` is everything, but `remaining = [c for c in chunks if c.id not in done_ids]` is empty, and the build reports success over an empty dense store. `--rebuild` is safe because it deletes the whole profile directory.

**Remediation:** Drop the file checkpoint and resume from `store.existing_ids()`; or keep it but delete it on successful completion and validate it against `store.count()` before trusting it.

### 11. BM25 index is loaded via `pickle`. *(Low / Noted)*

[bm25_index.py:60-64](src/lds_study/index/bm25_index.py#L60-L64) does `pickle.load` on `indexes/{profile}/bm25.pkl`. The file is locally generated and gitignored, so exposure is low, but per the global security baseline this is arbitrary-code-execution-on-deserialize if an index directory is ever shared, copied from a colleague, or restored from an untrusted backup.

**Remediation:** No action required for v1; if index sharing is ever considered, persist the tokenized corpus + ids as JSONL and rebuild `BM25Okapi` at load. Worth one line in `docs/ARCHITECTURE.md` saying index directories are not portable/untrusted-safe.

### 12. Retrieved chunk text is interpolated into the context block without delimiting. *(Noted)*

[prompts.py:30-43](src/lds_study/rag/prompts.py#L30-L43) formats each hit as `### [[{chunk.id}]] — {ref}` followed by raw `chunk.text`. Chunk text originates from BYOF ePub/PDF/HTML under `data/raw/user/`, which the plan classifies as untrusted input. A crafted file could emit its own `### [[bofm/alma/32/27]]` header inside its body and impersonate a scripture source in the context block.

Retrieved text is correctly in the **user** role (never the system prompt), and this is a single-user local tool, so impact is self-inflicted. But the citation validator only checks that an id is in the retrieved set — it cannot detect that the *text* attributed to that id was forged.

**Remediation:** No action for v1. If BYOF ever accepts files from third parties, escape or fence chunk text (e.g. strip `[[`/`]]` and leading `#` from chunk bodies before formatting).

### 13. Scope: the PR3 working tree also relocates PR2 evaluation reports. *(Trivial)*

`git status` shows two `plans/draft/pr2-*-implementation-evaluation-*.md` deleted and re-added under `plans/archive/`. Unrelated to PR3; it will muddy the PR diff.

**Remediation:** Commit the archive move separately.

### 14. `strict` short-circuit is redundant. *(Trivial)*

[ask.py:129](src/lds_study/rag/ask.py#L129) sets `max_attempts = 1 if strict else …`, so the loop already runs once; the `if strict: break` at line 157-158 can never change control flow. Harmless, but it reads as if two mechanisms are needed.

**Remediation:** Drop one of the two.

## Net assessment

PR3 delivers the architecture the plan asked for, and the parts I could exercise directly — Chroma upsert/query/filtering, RRF, neighbor expansion, the regenerate-then-refuse ladder, exit-code propagation, the copyright gate — behave correctly. The citation contract's headline property (never silently strip an invalid marker) is real and test-proven. Nothing here is a behavior change dressed as a refactor, and nothing deferred crept back in.

The problem is that the PR presents as verified when its two named gates are not. The 10/10 phrase smoke measures a fixture corpus built from its own answers; the test suite passes with dense retrieval fully disabled; the VRAM number the 15GB gate reads is 0.0 during `ask`; and the citation gate green-lights an empty answer. Merging as-is means PR4's eval baselines get built on top of a retrieval stack whose dense half has no regression net.

**Fix before merge:** 1 (dense coverage + stop swallowing exceptions), 3 (empty-answer gate hole), 5 (weights re-download breaks the offline claim), 2b (README). **Reframe before merge, no code needed:** 2 — say plainly in the PR description that the 10/10 gate is fixture-scale wiring proof and that the real-corpus run used the identity reranker. **Defer to PR4:** 4, 7, 8 (all three are things `lds eval` should settle with measurements rather than guesses). **Cleanup whenever:** 6, 9, 10, 13, 14.

One process note: branch `pr3-index-rag-cli` is 0 commits ahead of `main` — the whole of PR3 is uncommitted working tree. Nothing is reviewable as a diff yet.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **45 passed in 6.01s**
- `.venv/Scripts/python.exe -m ruff check src tests scripts` → **All checks passed!**
- `.venv/Scripts/python.exe scripts/check_staged_data.py` → exit 0, "0 path(s) checked; no allowlist violations"
- **Dense-path coverage probe:** forced `ChromaDenseStore.query` to `return []` unconditionally → `pytest -q tests/test_pr3_index_rag.py` → **13 passed**. File restored, sha1 verified identical (`8ef44233cdd634000b3658b5c7940215b0c5514e`).
- **Live Chroma probe:** `ChromaDenseStore` upsert of 3 `HashEmbedder`-embedded chunks → `count()` = 3, `query()` returned correct ranking, `RetrievalFilters(volume="bofm")` returned 3 rows, `volume="nope"` returned `[]`.
- **Citation gate probe:** `validate_citations` on `''`, `'## Summary'`, `'   '` → all `coverage=1.0, PASSES=True`; on uncited prose → `coverage=0.0, PASSES=False`.
- **Dependency probe:** `sentence-transformers 5.6.0` and `torch 2.11.0+cu128` present transitively via `llama-index-embeddings-huggingface` (`requires: sentence-transformers>=2.6.1`) — the undeclared direct import in `rerank.py` resolves today, but only by luck of a transitive pin.
- Grep gates: `grep -rn "exit code|no_evidence|unsupported|--strict|show-context" README.md docs/` → 1 hit, `docs/ARCHITECTURE.md:16` only. `grep -n "llama_index" src/lds_study/index/*.py` → `backend_llamaindex.py:135`, `embedder.py:51`.
- Fixture cross-check: all 10 `tests/fixtures/index/phrase_smoke.json` target ids present in the 22-verse `tests/fixtures/scripture/known_verses.json`.
- `git rev-list --count main..HEAD` → **0**; `git status --short` → 7 modified/deleted, 17 untracked, none under `data/`, `indexes/`, or `models/`.
- Not run (require GPU + full corpus + Ollama): `lds index --profile default --smoke`, `lds ask`, `scripts/check_env.py`.
