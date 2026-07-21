# Index + RAG CLI (PR3) — Implementation Evaluation (Round 3)

*Evaluator: claude · 2026-07-20 · Round 3 · Reviews PR3 of `claude-2026-07-20.md` against the working tree (branch `pr3-index-rag-cli`, still 0 commits ahead of `main`). Follows [round 1](pr3-index-rag-cli-implementation-evaluation-claude-2026-07-20.md) and [round 2](pr3-index-rag-cli-implementation-evaluation-claude-2026-07-20-2.md).*

## Verdict: Round-2 Critical is fixed and guarded. One new High remains — the refusal shortcut can print uncited prose as an answer.

The markup bug is properly dead. `_emit` and `--show-context` now pass `markup=False`, `_plain_source_list` switched to `(id: …)` so no bracket is involved at all, and — the part that matters most — there is now a genuine stdout-level regression net. I sabotaged it (removed `markup=False` from the `ok` branch) and `test_ask_stdout_keeps_lowercase_chunk_id_citation` failed with exactly the round-2 symptom: `assert 'user/talk-oct2023-03/s2' in 'The speaker invites us to think celestial. \n'`. That is the first test in this PR that asserts on what the user actually sees, and it is the right one to have added. Round-2 findings 2, 4 and most of 8 are also closed: `test_volume_filter_on_bm25` is a standalone test again, `backend_llamaindex.py` is now `chroma_store.py` with the dead alias and the unused `llama-index-vector-stores-chroma` dependency both gone, `resolve_model_path` rejects partial snapshots (with a test), `talk` mode has a test, and the `--verbose` help text was corrected. 53 tests pass, ruff is clean, the copyright gate holds.

The problem is the fix for round-2 finding 3. Routing the model's honest refusal to `no_evidence` was the right instinct, but `looks_like_honest_refusal` is a substring regex over free text, and the branch **echoes the model's prose verbatim**. I confirmed live that a 40-word answer attributing a specific claim to President Nelson — with zero citations — prints in full, labeled `(status=no_evidence)`, exit 3, because it also contained the sentence "I do not find this in the indexed sources, but the above summary reflects the talk." That hedge is one of the most common shapes an LLM produces. The plan specifies `no_evidence` as "**refuse before generating** … no synthesized prose" and `unsupported` as "a plain source list **with no synthesized prose**"; this path satisfies neither. It is a smaller blast radius than round 2's, but it is the same class of defect — uncited prose reaching the user looking sourced — and it was introduced by the remediation.

Fix finding 1 before merge. Everything else is small or already-agreed deferral.

## Round-2 finding disposition

| # (R2) | Finding | Status |
|---|---|---|
| 1 | Citations stripped from stdout by rich markup; `MarkupError` crash | **Fixed and guarded.** `ask.py:220-232` uses `markup=False` on all model/BYOF text; `--show-context` likewise (`ask.py:90-95`); `_plain_source_list` now emits `(id: {chunk.id})` (`ask.py:209`). Verified live: `ok` answer keeps `[user/talk-oct2023-03/s2]`, refusal list keeps `(id: user/talk-oct2023-03/s2)`. Sabotage probe confirms the new test catches a regression. Residue → finding 4. |
| 2 | `test_volume_filter_on_bm25` absorbed into the model-path test | **Fixed.** Standalone again at [tests:483](tests/test_pr3_index_rag.py#L483); `test_resolve_model_path_prefers_local` is back to one concern. |
| 3 | Prompt-prescribed refusal always discarded, burning a retry | **Fixed, but the fix overreaches.** `looks_like_honest_refusal` ([citations.py:135-147](src/lds_study/rag/citations.py#L135-L147)) short-circuits to `no_evidence`/exit 3 with no retry; `test_ask_honest_refusal_is_no_evidence` asserts `attempts == 1` and no reply burn. → finding 1. |
| 4 | Dead `llama-index-vector-stores-chroma`; misnamed module | **Fixed.** Module renamed to `chroma_store.py`, `LlamaIndexChromaStore` alias deleted, dependency removed from `pyproject.toml`. Only `llama-index-core` + `llama-index-embeddings-huggingface` remain, both genuinely used by `embedder.py:51`. Stale doc line → finding 5. |
| 5 | `talk` untested; outline modes share `study`'s coverage bar | **Half fixed.** `test_ask_talk_mode_ok` added. No realistic multi-section outline test, and `citation.min_coverage` is still a single global value in `configs/rag.yaml:21`. → finding 3. |
| 6 | Full-corpus 10/10 smoke still unrun | **Open, unchanged.** No `--smoke` output recorded anywhere; `outputs/eval/` holds nothing for this. Correctly labeled everywhere, so this is a reporting gap, not a false claim. |
| 7 | Chroma-only resume durability untested | **Open.** No reopen/round-trip test exists (`grep` for `reopen`/`existing_ids` in tests finds only the `EmptyDense` stub). Still a residual risk, not a demonstrated defect. |
| 8 | `--verbose` help, `EXIT_ERROR`, partial snapshot, unused fixtures, archive move, branch state | **Mostly fixed.** Help text now "Log peak VRAM (device + process) at end of build / per batch"; `resolve_model_path` partial-snapshot guard added with `test_resolve_model_path_rejects_partial_snapshot`; unused `tmp_path`/`monkeypatch` fixtures dropped from `test_ask_ok_path` and `test_index_build_hash_embedder_and_hybrid_retrieve`. Still open: `EXIT_ERROR` unused, archive move bundled, branch 0 commits ahead. |

## Completeness & accuracy by workstream

| Workstream (plan step) | Status | Evidence |
|---|---|---|
| Retriever protocol + rip-out seam (step 3) | Complete | `index/base.py` protocols; `chroma_store.py` name now matches reality. |
| Embed + Chroma persist, resumable (step 3) | Complete | `build.py:88-107`; resume via `existing_ids()`. Durability untested (finding 6). |
| BM25 parallel index (step 3) | Complete | Unchanged; `test_volume_filter_on_bm25` restored. |
| Hybrid RRF → rerank → top-8 → expand (step 3) | Complete | `hybrid.py:69-113` unchanged across all three rounds. |
| Query-time filters (step 3) | Complete | All five flags wired; BM25 filter coverage restored. |
| VRAM discipline (step 3) | Complete | Device + process split; `--verbose` help now accurate. |
| 10/10 phrase smoke gate (step 3 done-when) | Missing-but-honest | Harness correct, honestly scoped, still unrun on the real corpus. |
| Static system prompt, chunks in user role (step 4) | Complete | `prompts.py:16-27`. |
| Citation parse / validate / render (step 4) | Complete | Validator correct; renderer output now survives to stdout, with a test. |
| Four-path failure ladder + exit codes (step 4) | **Partial** | Four paths exist and are tested, but `no_evidence` can now carry synthesized prose — finding 1. |
| `study` / `lesson` / `talk` modes (step 4) | Complete (thin) | All three have a happy-path test; none uses outline-shaped output. |
| `music` / `serve` deferred | Deferred-as-planned | No change. |
| Copyright posture | Complete | `check_staged_data.py` → exit 0; nothing new tracked under `data/`, `indexes/`, `models/`. |
| Docs land with the code (step 8) | Complete | README quickstart + exit-code table + KV-cache note; one stale ARCHITECTURE line (finding 5). |

## Findings (ranked)

### 1. The refusal shortcut prints uncited synthesized prose and calls it `no_evidence`. *(High)*

`run_ask` checks `looks_like_honest_refusal(answer)` **before** the citation gate and returns immediately with the model's text as both `answer` and `rendered`:

```python
# src/lds_study/rag/ask.py:143-157
if looks_like_honest_refusal(answer):
    result = AskResult(
        status="no_evidence",
        exit_code=EXIT_NO_EVIDENCE,
        ...
        answer=answer,
        rendered=answer,
```

The detector is a bounded substring search:

```python
# src/lds_study/rag/citations.py:135-137
_REFUSAL_RE = re.compile(
    r"(?is)\b(?:i\s+)?(?:do\s+not|don't)\s+find\b.{0,80}\bindexed\s+sources\b"
)
```

Its only other guard is `if parse_markers(text): return False` — so it fires on **any** marker-free answer containing that phrase anywhere, at any length. Verified live with the real `configs/rag.yaml`:

```
--- long uncited prose that happens to contain the refusal phrase ---
President Nelson taught in October 2023 that covenant keeping brings power. He
also promised specific blessings to temple attenders.

I do not find this in the indexed sources, but the above summary reflects the
talk.
(status=no_evidence)
>>> STATUS no_evidence EXIT 3 attempts 1
```

Two specific claims attributed to a named living apostle, zero citations, printed in full and shipped with exit 3.

Why this matters beyond the general principle: `"I don't find X in the sources, but here's what I know…"` is a standard LLM hedging pattern, not a contrived input — arguably *more* likely than a bare refusal, since the prompt tells the model to refuse but the model still wants to be helpful. And the plan is explicit about both branches: `no_evidence` is "**Refuse before generating**", and `unsupported` returns "the retrieval results as a plain source list **with no synthesized prose**." There is no path in the plan where uncited model prose is displayed. Before this change the answer would have failed the gate, retried, and landed on `unsupported` with a source list — correct behavior. The remediation traded a wasted generation for a groundedness hole.

It also silently widens `no_evidence` semantics: round 2's `configs/rag.yaml:14-16` note says `no_evidence` is "rare until PR4 measures a real floor," which is true of the pre-generation `min_score` branch but no longer true of the system as a whole. Anything PR4 measures as an adversarial-refusal rate will now be counting two different things under one status.

**Remediation:** Keep the routing, drop the echo and tighten the match. Concretely: (a) require the refusal to *be* the answer, not contain it — e.g. `len(_claim_paragraphs(text)) <= 1` and the match starting within the first sentence; (b) do not set `rendered=answer` on this branch — print the canned "I don't find this in the indexed sources." line plus the retrieved source list, matching the `unsupported` treatment; (c) add the probe above as a test asserting `status == "unsupported"` for hedge-shaped output.

### 2. `looks_like_honest_refusal` is coupled to prompt wording with nothing binding them. *(Low)*

The regex requires the literal token `indexed sources` preceded by `do not find`/`don't find` within 80 characters. That matches all three prompt files today:

```
prompts/study_assistant.md:11  … say you do not find it in the indexed sources.
prompts/lesson_assistant.md:11 … say you do not find it in the indexed sources.
prompts/talk_assistant.md:11   … say you do not find it in the indexed sources.
```

Nothing enforces that. Reword a prompt to "say you cannot locate this in the indexed material" — a plausible edit, since `prompts/` is explicitly a versioned, editable surface — and the detector silently stops firing, reverting to the round-2 behavior (wasted retry, refusal discarded, source dump) with no test failure and no warning.

**Remediation:** Replace phrase-matching with a machine-readable sentinel the prompt emits (e.g. a bare `NO_EVIDENCE` line), which is both robust and testable; or, if keeping the regex, add a test that loads each `prompts/*.md`, extracts the refusal sentence, and asserts `looks_like_honest_refusal` matches it — so a prompt edit breaks the build rather than the behavior.

### 3. Outline modes still share `study`'s coverage bar, and no test uses outline-shaped output. *(Low — carried from R2)*

`test_ask_lesson_mode_ok` ([tests:509-538](tests/test_pr3_index_rag.py#L509-L538)) and `test_ask_talk_mode_ok` both script a **single-paragraph, single-citation** reply. They prove mode plumbing (`result.mode == "lesson"`), not that a real lesson outline survives the gate. `_claim_paragraphs` still counts a discussion-question block or a bulleted outline as a claim paragraph needing its own valid marker, and `citation.min_coverage: 0.8` (`configs/rag.yaml:21`) is still global — so a plausible lesson outline (heading + cited exposition + uncited question list + uncited closing thought) scores 0.5 and refuses.

**Remediation:** One test per outline mode with a realistic multi-section reply, pinning whatever the intended behavior is. If outline modes need a lower bar, add a per-mode `min_coverage` override rather than discovering the mismatch at runtime.

### 4. CLI error handlers still print exception text through rich markup. *(Low)*

The `_emit` path was fixed, but the surrounding error handlers were not:

```python
# src/lds_study/cli.py:93, 134, 191
console.print(f"[red]prepare failed:[/red] {exc}")
console.print(f"[red]index failed:[/red] {exc}")
console.print(f"[red]ask failed:[/red] {exc}")
```

Exception text is not always repo-authored. `OllamaGenerator.complete` raises `RuntimeError(f"Ollama HTTP {exc.code}: {detail}")` where `detail` is the server's response body ([generate.py:52-54](src/lds_study/rag/generate.py#L52-L54)), and `RuntimeError(f"Ollama returned empty content: {body!r}")` embeds a raw response repr; `chunks_io` raises `ValueError(f"{path}:{line_no}: invalid JSON")` with a filesystem path. Verified:

```
c.print(f'[red]ask failed:[/red] {RuntimeError("Ollama HTTP 400: {\"error\":\"unexpected [/token] in template\"}")}')
→ RAISED: MarkupError closing tag '[/token]' at position 61
```

A `MarkupError` here escapes `typer.Exit(code=1)` as a traceback, so the failure path loses its exit code — the same contract break as round 2, just in the handler instead of the happy path.

**Remediation:** `console.print("ask failed:", str(exc), style="red")`, or `escape(str(exc))`. Same for `prepare` and `index`.

### 5. `docs/ARCHITECTURE.md` contradicts itself about the backend. *(Trivial)*

Line 48 still reads `Retriever protocol + LlamaIndex/Chroma backend, BM25, hybrid (PR3)` while line 53, added in round 2, correctly says LlamaIndex is used only for the embedding wrapper. The module it refers to is now `chroma_store.py` and contains no LlamaIndex at all.

**Remediation:** Update line 48 to "Retriever protocol + Chroma dense store, BM25, hybrid (PR3)".

### 6. Chroma-only resume still has no durability test. *(Low — carried from R2)*

Unchanged from round 2: removing `embed_checkpoint.json` was correct, but resume now rests entirely on Chroma keeping its id metadata and vector segment consistent across an abrupt exit. Still not reproduced as a defect; still uncovered. A ~10-line test (upsert, drop the client without closing, reopen the directory, assert `count()` and a `query()` round-trip see the batch) would retire it.

### 7. Smaller items. *(Trivial)*

- `pyproject.toml:26` — `    "llama-index-core>=0.11",` is indented four spaces where every sibling uses two. Valid TOML, but it looks like an edit artifact from removing the line above it.
- `EXIT_ERROR` ([ask.py:30](src/lds_study/rag/ask.py#L30)) is still defined and never used; `cli.py` hardcodes `typer.Exit(code=1)` in three places.
- The `plans/archive/pr2-*` move is still bundled into the PR3 working tree (third round carrying this).
- Branch `pr3-index-rag-cli` is **still 0 commits ahead of `main`**. Three review rounds in, PR3 has never existed as a diff — 35 entries in `git status --short`, all uncommitted. Whatever lands, it should land as commits before a fourth round.

## Net assessment

This round closed the Critical cleanly and, more importantly, closed it *with a test that fails when the fix is removed* — which is what round 2 said was missing and is now the strongest thing in the PR's verification story. The module rename, dependency cleanup, restored filter test, partial-snapshot guard, and help-text correction are all straightforward wins with no side effects that I could find.

The one substantive miss is that finding 3's remediation solved the cost problem (wasted regeneration) by creating a groundedness problem (uncited prose displayed as an answer). That is worth calling out as a pattern: across three rounds, every regression this PR has produced has been in the *output* layer rather than the retrieval or validation layers. The validator has been correct since round 1; what keeps failing is what gets printed and under which status. Finding 1's fix should therefore be conservative — route on the refusal, but print the canned line and the source list, not the model's text.

**Fix before merge:** 1. **Cheap, worth doing with it:** 2 and 4 — both are one-line-ish and both protect contracts that already exist. **Defer to PR4:** 3, 6, and the still-unrun full-corpus smoke. **Cleanup:** 5, 7.

Then commit it. A fourth round against an uncommitted working tree is not a good use of the loop.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **53 passed in 6.09s** (45 → 48 → 53 across rounds)
- `.venv/Scripts/python.exe -m ruff check src tests scripts` → **All checks passed!**
- `.venv/Scripts/python.exe scripts/check_staged_data.py` → `OK — 0 path(s) checked; no allowlist violations`, exit 0
- **Markup-fix sabotage probe:** removed `markup=False` from the `ok` branch of `_emit` → `test_ask_stdout_keeps_lowercase_chunk_id_citation` **FAILED** with `assert 'user/talk-oct2023-03/s2' in 'The speaker invites us to think celestial. \n'` (1 failed / 20 passed). File restored, sha1 verified (`320fc2d33271d13c8ce117a1c013364584ae4cb9`).
- **Refusal-list probe:** `unsupported` path now prints `- user/talk-oct2023-03/s2 (id: user/talk-oct2023-03/s2)` — ids survive.
- **Hedge-shaped refusal probe (finding 1):** 40-word uncited answer containing "I do not find this in the indexed sources, but…" → printed verbatim, `STATUS no_evidence EXIT 3 attempts 1`.
- **CLI error markup probe (finding 4):** `console.print(f'[red]ask failed:[/red] {exc}')` with `[/token]` in the exception text → `MarkupError`.
- **Prompt/regex coupling check:** all three `prompts/*.md` refusal lines match `_REFUSAL_RE` today; no test binds them.
- Grep gates: `grep -rn "llama_index" src/` → only `embedder.py:40,51`. `grep -rn "backend_llamaindex\|LlamaIndexChromaStore"` → **no matches**. `grep -rn "chroma_store" src/ tests/` → `build.py:15`, `tests:13`. `grep -n "^def test_" tests/…` → 21 tests, `test_volume_filter_on_bm25` present at line 483.
- `git rev-list --count main..HEAD` → **0**; `git status --short` → 35 entries; nothing under `data/`, `indexes/`, `models/`.
- Not run (require GPU + full corpus + Ollama): `lds index --profile default --smoke`, live `lds ask`, `scripts/check_env.py`.
