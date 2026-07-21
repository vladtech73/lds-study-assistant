# Index + RAG CLI (PR3) — Implementation Evaluation (Round 4)

*Evaluator: claude · 2026-07-20 · Round 4 · Reviews PR3 of `claude-2026-07-20.md` against the working tree (branch `pr3-index-rag-cli`, still 0 commits ahead of `main`). Follows [round 1](pr3-index-rag-cli-implementation-evaluation-claude-2026-07-20.md), [round 2](pr3-index-rag-cli-implementation-evaluation-claude-2026-07-20-2.md), [round 3](pr3-index-rag-cli-implementation-evaluation-claude-2026-07-20-3.md).*

## Verdict: Round-3 High is fixed correctly. No blocking findings remain — ship it, after committing it.

The refusal shortcut was fixed the conservative way I hoped for, and then some. `looks_like_honest_refusal` now requires a single claim paragraph, the phrase within the first 20 characters, and under 24 characters of residual prose ([citations.py:142-159](src/lds_study/rag/citations.py#L142-L159)); the `no_evidence` branch no longer echoes model text at all — it sets `answer=None` and renders a canned line plus the retrieved source list ([ask.py:144-160](src/lds_study/rag/ask.py#L144-L160)). Verified live: the bare refusal yields the canned line + sources at exit 3, and the exact hedge from round 3 ("Nelson taught covenant power… I do not find this in the indexed sources, but the summary is accurate") now routes to `unsupported`/exit 2 with the prose absent from output. `test_ask_hedge_refusal_is_unsupported` pins it. Rounds 3's findings 4, 5 and 7 are also all closed: CLI error handlers use `console.print("…failed:", str(exc), style="red")`, the stale ARCHITECTURE table row is corrected, the `pyproject.toml` indentation artifact is gone, and `EXIT_ERROR` was deleted rather than left dangling.

Two things are worth knowing before merge, neither blocking. `test_prompt_refusal_matches_detector` does not actually bind the prompt to the detector — I reworded `prompts/study_assistant.md` to "cannot locate this in the indexed sources" (wording the regex does not match) and the test still passed, because it asserts against hardcoded literals rather than the sentence it loaded. And `ask.py`'s expand-neighbor filter has a latent hole that activates precisely when PR4 raises `retrieval.min_score`: I set `min_score: 0.9` and confirmed a weak seed was dropped while its expansion neighbor survived into the context as a citable source, producing `status: ok` on a claim sourced to a verse whose anchor the retriever had rejected.

Four rounds in, the code is in good shape. The thing that has not moved at all is that PR3 has never been committed — 36 uncommitted entries, `git rev-list --count main..HEAD` = 0. That is now the largest risk to this work.

## Round-3 finding disposition

| # (R3) | Finding | Status |
|---|---|---|
| 1 | Refusal shortcut printed uncited prose as `no_evidence` | **Fixed, both halves.** (a) Detector tightened: single claim paragraph, match start ≤ 20, residual < 24 chars. (b) Branch no longer echoes — `answer=None`, `rendered=_no_evidence_listing(hits)` = `CANNED_NO_EVIDENCE` + sources. Live-verified both directions; `test_ask_hedge_refusal_is_unsupported` asserts `"President Nelson taught" not in result.rendered`. |
| 2 | Detector coupled to prompt wording with nothing binding them | **Partially fixed — the new test does not bind.** `test_prompt_refusal_matches_detector` added, but see finding 1 below. |
| 3 | Outline modes share `study`'s coverage bar; no outline-shaped test | **Open, unchanged.** `test_ask_lesson_mode_ok` ([tests:569-599](tests/test_pr3_index_rag.py#L569-L599)) still scripts a single-paragraph single-citation reply; `citation.min_coverage` still a lone global at `configs/rag.yaml:20`. Agreed PR4 deferral. |
| 4 | CLI error handlers printed exception text through rich markup | **Fixed.** `cli.py:93,134,191` now `console.print("… failed:", str(exc), style="red")` — no markup parsing of exception text. |
| 5 | `ARCHITECTURE.md` table row contradicted line 53 | **Fixed.** Line 48 now reads "Retriever protocol + Chroma dense store, BM25, hybrid (PR3)". |
| 6 | Chroma-only resume has no durability test | **Open, unchanged.** No reopen/round-trip test exists. Still a residual risk, not a demonstrated defect. |
| 7 | `pyproject` indent artifact, unused `EXIT_ERROR`, archive move, branch state | **Mostly fixed.** Indentation normalized; `EXIT_ERROR` removed entirely (`grep -rn "EXIT_ERROR" src/ tests/` → no matches). Still open: the `plans/archive/pr2-*` move is bundled, and the branch is still 0 commits ahead. |

## Completeness & accuracy by workstream

| Workstream (plan step) | Status | Evidence |
|---|---|---|
| Retriever protocol + rip-out seam (step 3) | Complete | `index/base.py` protocols; `chroma_store.py` correctly named; only two `llama-index-*` deps, both used. |
| Embed + Chroma persist, resumable (step 3) | Complete | `build.py:88-107`; resume via `existing_ids()`. Durability untested (finding 4). |
| BM25 parallel index (step 3) | Complete | `test_volume_filter_on_bm25` standalone at [tests:543](tests/test_pr3_index_rag.py#L543). |
| Hybrid RRF → rerank → top-8 → expand (step 3) | Complete | `hybrid.py:69-113` unchanged across all four rounds. |
| Query-time filters (step 3) | Complete | Five flags wired end to end. |
| VRAM discipline (step 3) | Complete | Device + process split; generator unload; CPU rerank default. |
| 10/10 phrase smoke gate (step 3 done-when) | Missing-but-honest | Harness correct, honestly scoped in code and README; still unrun on the real corpus. |
| Static system prompt, chunks in user role (step 4) | Complete | `prompts.py:16-27`. |
| Citation parse / validate / render (step 4) | Complete | Validator correct; output survives to stdout with a sabotage-proven test. |
| Four-path failure ladder + exit codes (step 4) | Complete | All four paths live-verified this round: `ok`/0, `unsupported`/2, `no_evidence`/3 (pre-generation and post-generation), `--strict` skip. Latent scoping issue at raised `min_score` → finding 2. |
| `study` / `lesson` / `talk` modes (step 4) | Complete (thin) | All three tested happy-path; none with outline-shaped output. |
| `music` / `serve` deferred | Deferred-as-planned | No change. |
| Copyright posture | Complete | `check_staged_data.py` → exit 0; nothing new tracked under `data/`, `indexes/`, `models/`. |
| Docs land with the code (step 8) | Complete | README quickstart, exit-code table, KV-cache note; ARCHITECTURE consistent. |

## Findings (ranked)

### 1. The prompt/detector coupling test does not couple anything. *(Low)*

`test_prompt_refusal_matches_detector` ([tests:358-373](tests/test_pr3_index_rag.py#L358-L373)) loads each prompt, then asserts the detector against **string literals written in the test**, not against the sentence it just loaded:

```python
for mode in MODE_FILES:
    prompt = load_system_prompt(mode, root=ROOT)
    assert "indexed sources" in prompt.lower()
    assert looks_like_honest_refusal("I do not find it in the indexed sources."), mode
    assert not looks_like_honest_refusal("Here is a claim about Nelson.\n\n…"), mode
```

The only thing tying the prompt to the regex is the `"indexed sources" in prompt` substring check. `_REFUSAL_RE` additionally requires `do not find`/`don't find` within 80 characters of it ([citations.py:134-136](src/lds_study/rag/citations.py#L134-L136)), and nothing checks for that.

**Verified.** I reworded `prompts/study_assistant.md:11` from "say you do not find it in the indexed sources" to "say you **cannot locate this** in the indexed sources" — wording the detector does not match — and ran the test:

```
1 passed, 22 deselected in 0.65s
```

Green, while the shipped behavior would have silently reverted to round 2's: the model's compliant refusal fails the gate, burns a regeneration, and is replaced by an `unsupported` source dump. The comment above `CANNED_NO_EVIDENCE` ("Keep in sync with prompts/* refusal wording (see test_prompt_refusal_matches_detector)") points at a test that cannot enforce it. Prompt file restored; sha1 verified (`fd175d9ad8df410c55724fc0524cefb1a826c3b6`).

**Remediation:** Extract the refusal sentence from each loaded prompt and feed *that* to the detector — e.g. take the line containing `indexed sources`, strip the leading `- If …, say `, and assert `looks_like_honest_refusal` on the result. Or drop phrase-matching for a sentinel the prompt emits (`NO_EVIDENCE` on its own line), which is trivially testable and immune to rewording.

### 2. Expand neighbors outlive their seeds once `min_score` is raised, letting the model cite a verse whose anchor was rejected. *(Low now, High the moment PR4 acts)*

`ask.py` re-applies `retrieval.min_score` to seed hits, then admits **every** expand hit unconditionally:

```python
# src/lds_study/rag/ask.py:114-122
qualify_ids = {h.chunk.id for h in qualifying_seeds}
hits: list[RetrievedHit] = []
for hit in retrieval.hits:
    if hit.source != "expand" and hit.chunk.id in qualify_ids:
        hits.append(hit)
    elif hit.source == "expand":
        # Neighbor pulled for a qualifying seed — include for context.
        hits.append(hit)
```

The comment asserts the invariant the code does not enforce: `RetrievedHit` carries no back-reference to the seed it was expanded from, so "pulled for a qualifying seed" is unverifiable at this point. `expand_context` scores neighbors at `seed.score * 0.5` ([expand.py:49](src/lds_study/index/expand.py#L49)), so a neighbor is always *below* its seed — meaning when a seed is dropped, its neighbors are dropped too if judged by the same threshold, but here they are not judged at all.

This is dormant today because `min_score: 0.0` and `HybridRetriever` already applied the same threshold, so `qualifying_seeds == seed_hits` always and the ask-level filter is dead code. It activates exactly when PR4 does what `configs/rag.yaml:14-16` says it will ("raise after PR4 eval"). Simulated with `min_score: 0.9`:

```
>>> ids offered to the model: ['bofm/alma/1/5', 'bofm/alma/1/6', 'bofm/mosiah/1/10']
>>> STATUS ok EXIT 0
    Claim from a dropped seed neighbor. [mosiah 1:10]
```

`bofm/mosiah/1/9` (score 0.3) was rejected as insufficiently relevant; its neighbor `bofm/mosiah/1/10` (score 0.15) stayed in the context, became a valid citable id, and the model's claim sourced to it passed the citation gate at exit 0. The citation is technically "valid" — the id was in the retrieved set — which is precisely why this slips past the validator.

**Remediation:** Give `RetrievedHit` a `seed_id: str | None` set by `expand_context`, and admit an expand hit only when `hit.seed_id in qualify_ids`. Add a test at a raised `min_score` asserting orphan neighbors are excluded. Cheap to do now; much harder to notice after PR4 changes the threshold and the symptom becomes "occasionally cites an odd verse."

### 3. Outline modes still share `study`'s coverage bar. *(Low — carried from R2/R3, agreed PR4 deferral)*

Unchanged. `test_ask_lesson_mode_ok` and `test_ask_talk_mode_ok` both script one-paragraph, one-citation replies, so they prove mode plumbing (`result.mode == "lesson"`) rather than that a real outline survives. `_claim_paragraphs` still counts a discussion-question block as a claim paragraph needing its own marker against a global `min_coverage: 0.8`.

**Remediation:** As before — one realistic multi-section reply per outline mode to pin intended behavior, and a per-mode `min_coverage` override if outline modes need a lower bar. Reasonable to let PR4's eval set the number first.

### 4. Chroma-only resume still has no durability test. *(Low — carried from R2/R3)*

Unchanged and still not reproduced as a defect. `grep -rn "reopen\|PersistentClient" tests/` → no matches. A ~10-line test (upsert a batch, drop the client without closing, reopen the directory, assert `count()` and a `query()` round-trip see it) would retire the last unknown in the resume path.

### 5. Full-corpus 10/10 smoke still unrun. *(Low — reporting gap, not a false claim)*

No `lds index --profile default --smoke` output exists in the repo. This has been correctly labeled everywhere since round 2 — `smoke.py`'s module docstring, the test names, and `README.md:57` all say the committed tests are wiring proofs — so nothing overclaims. But PR3's done-when ("10/10 at rank 1, peak VRAM logged below 15GB") is still unsatisfied on paper. I cannot run it here (needs GPU, Ollama, full corpus).

**Remediation:** Paste the real run into the PR description, noting that `--smoke` uses `IdentityReranker` and therefore validates `RRF → identity → top-1` rather than `ask`'s `RRF → cross-encoder → top-8`.

### 6. Two long-carried housekeeping items. *(Trivial)*

- The `plans/archive/pr2-*` move is still bundled into the PR3 working tree — fourth round carrying this.
- **Branch `pr3-index-rag-cli` is still 0 commits ahead of `main`**, with 36 uncommitted entries in `git status --short`. Four review rounds have now been performed against a working tree that has never been committed. Every round of fixes so far exists only as unstaged edits; a stray `git checkout` or a crashed editor loses all of it, and there is still no diff for a human reviewer to read.

## Net assessment

Round 4 is the cleanest of the four. The round-3 High was fixed with the conservative approach — tighten the detector *and* stop echoing — rather than just one of the two, and the hedge case is now pinned by a test that reproduces the exact probe from the last report. The four housekeeping items closed properly (deleting `EXIT_ERROR` rather than wiring it up was the right call).

Neither remaining finding blocks merge. Finding 1 is a test that gives false assurance about a coupling it does not check — worth ten minutes because the comment in `citations.py` actively points readers at it. Finding 2 is genuinely dormant: it cannot fire at `min_score: 0.0`, and the config explicitly says not to raise that until PR4. But it is much cheaper to fix now, while the reasoning is loaded, than to debug later as "sometimes cites a neighboring verse for no reason," and it is the last place where a citation can be technically valid while being substantively ungrounded — the exact property this PR exists to guarantee.

Looking across four rounds: the retrieval and validation layers have been correct since round 1, and every regression has been in what gets printed and under which status. Both remaining findings are in that same seam, which is a good argument for making finding 2's fix explicit (a `seed_id` field) rather than relying on another comment describing an invariant.

**Merge readiness: yes, with findings 1 and 2 as small pre- or post-merge follow-ups.** **Defer to PR4:** 3, 4, 5. **Do first, before anything else:** commit the work. A fifth review round against an uncommitted tree would be the least useful thing this loop could do next.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **55 passed in 6.10s** (45 → 48 → 53 → 55 across rounds)
- `.venv/Scripts/python.exe -m ruff check src tests scripts` → **All checks passed!**
- `.venv/Scripts/python.exe scripts/check_staged_data.py` → `OK — 0 path(s) checked; no allowlist violations`, exit 0
- **Bare-refusal probe:** scripted `"I do not find this in the indexed sources."` → printed `I don't find this in the indexed sources.` + `Retrieved sources:` block, `STATUS no_evidence EXIT 3`, `answer=None` — no model prose echoed.
- **Hedge probe (R3 finding 1 regression check):** the round-3 hedge string → `STATUS unsupported EXIT 2`, `prose leaked: False`.
- **Prompt-reword probe (finding 1):** rewrote `prompts/study_assistant.md:11` to "cannot locate this in the indexed sources" → `pytest -k prompt_refusal` still **passed** (1 passed, 22 deselected). File restored, sha1 verified (`fd175d9ad8df410c55724fc0524cefb1a826c3b6`).
- **Orphan-neighbor probe (finding 2):** `Settings` subclass forcing `retrieval.min_score = 0.9`; retriever returning a strong seed + neighbor and a weak seed (0.3) + neighbor (0.15) → context offered `['bofm/alma/1/5', 'bofm/alma/1/6', 'bofm/mosiah/1/10']` (weak seed absent, its neighbor present), model cited the orphan, result `STATUS ok EXIT 0`.
- Grep gates: `grep -rn "EXIT_ERROR" src/ tests/` → **no matches**. `grep -rn "reopen\|PersistentClient" tests/` → **no matches**. `grep -n "min_coverage" configs/rag.yaml src/lds_study/rag/*.py` → single global value, no per-mode override. `grep -n "failed" src/lds_study/cli.py` → all three handlers use `style="red"` with no markup interpolation.
- `git rev-list --count main..HEAD` → **0**; `git status --short` → **36** entries; nothing under `data/`, `indexes/`, `models/`.
- Not run (require GPU + full corpus + Ollama): `lds index --profile default --smoke`, live `lds ask`, `scripts/check_env.py`.
