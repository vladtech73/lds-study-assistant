# Eval Harness (PR4) — Implementation Evaluation

*Evaluator: claude · 2026-07-21 · Reviews PR4 of `claude-2026-07-20.md` against the uncommitted working tree (vs `HEAD` = `cd16b2f`).*

## Verdict: Mergeable — the harness is real and the gate is met, but the baselines it wrote into `configs/rag.yaml` are wrong and would misfire in PR5

The `lds eval` command exists, runs, and produced a genuine two-model comparison committed at
[outputs/eval/2026-07-21.md](outputs/eval/2026-07-21.md) — the arithmetic in that table
reconciles exactly against its own per-item rows, so it is a real run, not a hand-written
placeholder. The 50-question golden set is present, four-bucketed, scripture-only, and
gitignore/copyright hygiene is intact. The blocking problems are in the *metric design and the
values derived from it*: `min_adversarial_refusal: 0.5` is above what either model actually
achieved, `citation_validity_rate` is anti-correlated with refusal by construction, and the
one Decisions-appendix question PR4 was chartered to close (`retrieval.min_score`) was left
open because the harness captures no score data. Nothing here is a correctness bug in shipped
`ask` behavior, so this is safe to land — but findings 1–3 should be fixed before PR5 consumes
these numbers.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **`eval/golden.yaml` — ~50 questions, 4 buckets, public-domain only** | Complete | [eval/golden.yaml](eval/golden.yaml): 50 questions; 15 verse_lookup / 13 doctrinal_synthesis / 10 lesson_planning / 12 adversarial. All 27 distinct `gold_chunk_ids` match the id grammar emitted by [chunk_scripture.py:54-55](src/lds_study/data/chunk_scripture.py#L54-L55) (`bofm/1-nephi/3/7`, `dc/dc/19/23`, `ot/psalms/23/1`, `pgp/moses/1/39` all verified against `volume_slug`/`book_slug`). No restricted sources referenced. |
| **`golden.local.yaml` gitignored escape hatch** | Complete | [.gitignore:41](.gitignore#L41); loaded in [golden.py:86-89](src/lds_study/eval/golden.py#L86-L89); `--no-local` flag exists. See finding 4 for the gate gap. |
| **`lds eval` command** | Complete | [cli.py:188-256](src/lds_study/cli.py#L188-L256); `_not_yet` stub removed. `eval --help` exits 0; `--buckets nope` fails cleanly with `unknown buckets: ['nope']`. |
| **Metrics: recall@k, citation validity, adversarial refusal, manual 1–5 column** | Partial | [metrics.py](src/lds_study/eval/metrics.py) implements all four; `quality_manual` is emitted as a blank column with no path to merge human scores back into a re-run. Citation validity is mis-specified (finding 2). |
| **`outputs/eval/{date}.md` written; JSON local-only** | Complete | [report.py:16-19](src/lds_study/eval/report.py#L16-L19). `git check-ignore -v` confirms `.md` un-ignored via `.gitignore:37`, `.json` ignored via `.gitignore:32`. |
| **Gate: comparison table for ≥2 generators committed under `outputs/eval/`** | Complete | `qwen2.5:14b` vs `qwen3:14b`, n=50 each. Verified the aggregates against the per-item rows by hand: recall 30/38 = 78.9% (both), citation 35/50 = 70.0% and 36/50 = 72.0%, adversarial 4/12 = 33.3% (both). Report contains no corpus text. |
| **Gate: thresholds written into `configs/rag.yaml` as PR5 regression baseline** | Partial — written, but one value is wrong | [configs/rag.yaml:30-37](configs/rag.yaml#L30-L37). See finding 1. |
| **Decisions appendix: "`min_coverage` starting value — PR4's eval sets the real number"** | Missing | `min_coverage` is still `0.8` with the comment downgraded from "guess until PR4 sets the real baseline" to "may be tightened after PR4 comparison." Nothing measured it. |
| **Plan text: compare Qwen2.5-14B, Qwen3-14B, *and* gpt-oss-20b** | Partial | Only 2 of the 3 named candidates were run. The `--models` default silently truncates: [run.py:163-165](src/lds_study/eval/run.py#L163-L165) takes `shortlist[:2]` while [configs/models.yaml:29-33](configs/models.yaml#L29-L33) lists three. |
| **Offline tests, no GPU, no network** | Complete | [tests/test_pr4_eval.py](tests/test_pr4_eval.py), 5 tests, `_FakeRetriever` + pre-existing `ScriptedGenerator`. `pytest -q` → **61 passed in 6.09s**. `ruff check src tests scripts` → **All checks passed**. |
| **Docs (README, MODEL_CARD, ARCHITECTURE, eval/README)** | Complete | All four updated with the new command and a link to the report. |

## Findings (ranked)

### 1. `min_adversarial_refusal: 0.5` is a floor neither evaluated model can clear, and its own comment is false. *(High)*

[configs/rag.yaml:33-37](configs/rag.yaml#L33-L37) says:

```yaml
    # Conservative floors = 90% of best observed across qwen2.5:14b / qwen3:14b.
    min_adversarial_refusal: 0.5
```

Best observed adversarial refusal was **33.3%** for both models. 90% of that is 0.30. The 0.5
comes from the `max(0.5, best * 0.9)` clamp in
[metrics.py:145-147](src/lds_study/eval/metrics.py#L145-L147) — a hardcoded "never floor below
50%" guard that silently overrides the measurement when the system performs badly. The comment
that survives into `rag.yaml` therefore states something the data contradicts.

Why it matters: the plan (step 7) makes these floors the keep-or-revert gate for the PR5
adapter — "keep the adapter **only if** citation validity and adversarial refusal rate meet or
beat the PR4 baseline." A floor of 0.5 fails the *unadapted base model*, so the gate rejects
every adapter unconditionally, including ones that improve things. That is not a conservative
baseline; it is a broken one.

**Remediation:** Either drop the `max(0.5, …)` clamp so floors reflect measurement, or keep the
clamp but have `suggested_baselines()` mark clamped values explicitly (e.g. emit
`min_adversarial_refusal: 0.3  # measured; 0.5 is the aspiration, not the floor`) and fix the
`rag.yaml` comment so it does not claim "90% of best observed" for a value that isn't.

### 2. `citation_validity_rate` counts correct refusals as citation failures, making it anti-correlated with the refusal metric. *(High)*

[run.py:126-130](src/lds_study/eval/run.py#L126-L130):

```python
if ask.status == "ok":
    row.citation_valid = len(invalid) == 0
elif ask.status == "unsupported":
    # Failed citation gate after retry — count as invalid.
    row.citation_valid = False
```

Every `unsupported` result scores `citation_valid = False`, including the 12 adversarial items
where refusing *is* the correct answer. In the committed report, `adv-002` refuses correctly
(`refuse_ok = Y`) and is simultaneously scored `cite_ok = N`. Concretely: `qwen3:14b` refused
`adv-001`, `adv-005`, `adv-008`, `adv-009` — four correct behaviors that each cost it a point of
citation validity.

Failure scenario for PR5: a style adapter that *improves* adversarial refusal from 4/12 to 10/12
drives `citation_validity_rate` down by roughly 12pp, trips `min_citation_validity: 0.648`, and
gets reverted for being better. Two of the three regression gates move in opposite directions on
the same underlying change.

A secondary conflation: `unsupported` triggered by *low coverage* (e.g. `lp-006` at 0.17, zero
invalid markers) is also scored as citation-invalid, even though no fabricated citation occurred.
"Citation validity" as reported is really "fraction of items that produced an accepted answer."

**Remediation:** Scope `citation_validity_rate` to non-adversarial items that attempted an
answer, and split "emitted an invalid marker" from "fell below coverage" into two counters.
Report both in the comparison table.

### 3. PR4 was chartered to set `retrieval.min_score` and `citation.min_coverage`; it captured no data capable of setting either. *(High)*

The plan's Decisions appendix lists "`min_coverage` starting value (gates PR3): 0.8 is a guess;
PR4's eval sets the real number," and the pre-PR4 `rag.yaml` comment read "Default 0.0 means
no_evidence is rare until PR4 measures a real floor."

After PR4 both are unchanged, and the comments were rewritten to defer rather than resolve —
`min_score` now reads "Keep 0.0 until a measured floor from `outputs/eval/` shows raising it
improves adversarial refusal." But `outputs/eval/` cannot ever show that:
`ItemMetrics` ([metrics.py:10-27](src/lds_study/eval/metrics.py#L10-L27)) records no retrieval
scores, and `to_row()` drops `retrieved_ids` and `invalid_markers` from the JSON sidecar too. No
score distribution is persisted anywhere, so the instrument to close the question does not exist.

This is the finding most likely to be papered over: the comment change reads like progress while
the measurement capability moved backwards from "not yet" to "not possible."

**Remediation:** Persist per-hit rerank scores (at minimum top-1 and top-k scores per item) in
the JSON sidecar, and add a report section showing the score distribution split by
adversarial-vs-grounded items — that is the histogram that picks `min_score`.

### 4. The copyright gate does not monitor `eval/golden.local.yaml`, the one new file designed to hold restricted-source content. *(Medium)*

`.gitignore:41` ignores `eval/golden.local.yaml`, but
[check_staged_data.py:23](scripts/check_staged_data.py#L23) monitors only
`("data/", "indexes/", "models/", "outputs/", "private/")`. `git add -f eval/golden.local.yaml`
passes the gate cleanly.

This matters more than a normal gitignore leak because the plan's own risk section calls out
"someone (including a future me) commits a conference talk" and specifies the fix as a
**path-based** staged-file check, not gitignore alone. `golden.local.yaml` is explicitly
described in [eval/README.md:4](eval/README.md#L4) as holding "BYOF / restricted-source
questions" — questions that will quote Conference talk and Come, Follow Me text.

**Remediation:** Add `eval/golden.local.yaml` (and `eval/*.local.yaml`) to `MONITORED_PREFIXES`
or to a new exact-match denylist in `check_staged_data.py`, plus a test — note that `private/`
was also added in this diff with no test covering it.

### 5. Committed reports do not record whether local (restricted-source) questions were included. *(Medium)*

`--include-local` defaults to **True** ([cli.py:214-218](src/lds_study/cli.py#L214-L218)). The
markdown header ([report.py:55-67](src/lds_study/eval/report.py#L55-L67)) records profile,
models, k, and `retrieval_only` — but not `include_local`, not the question count per source,
and not which questions came from `golden.yaml` vs `golden.local.yaml`.
`GoldenQuestion.source` ([golden.py:28](src/lds_study/eval/golden.py#L28)) tracks exactly this
and is then never propagated into `ItemMetrics` or either report.

So a report committed under `outputs/eval/` cannot be verified as public-domain-only, and its
aggregates are not reproducible by anyone without the reporter's local file. Text does not leak
(the tables carry ids only), so this is a provenance problem, not a copyright breach.

**Remediation:** Plumb `source` into `ItemMetrics`, and add `include_local`, per-source question
counts, and a `golden.yaml` content hash to the report header.

### 6. A missing or misnamed Ollama model produces a plausible-looking report instead of an error. *(Medium)*

`evaluate_question` wraps the whole body in `except Exception` ([run.py:133-135](src/lds_study/eval/run.py#L133-L135)).
Retrieval succeeds and sets `recall_hit` *before* `run_ask` is reached, so a model id that does
not exist locally yields: full recall@k numbers, `citation_validity_rate = None` → rendered
`n/a`, and per-item `status = error` with the error *message discarded* from the markdown.
`status_counts` (which would show `{"error": 50}`) is computed in `aggregate()` and serialized
to JSON but never rendered in the markdown report.

There is also no preflight `ollama list` / model-availability check, so the failure only shows
up 50 questions later.

**Remediation:** Preflight-check each model id before the loop and fail fast; render
`status_counts` (or at least an error count) as a column in the comparison table; keep the first
error message in the markdown.

### 7. Retrieval runs twice per question per model, and recall@k is model-independent by construction. *(Low)*

`evaluate_question` calls `_seed_ids(retriever, …)` ([run.py:91](src/lds_study/eval/run.py#L91))
and then `run_ask`, which retrieves again ([ask.py:88](src/lds_study/rag/ask.py#L88)). For a
50-question × 2-model run that is 200 retrievals where 50 would do — each involving a BGE-M3
query embed, a Chroma query, BM25, and a cross-encoder rerank.

Relatedly, the retriever does not depend on the model, so `Recall@8` is *guaranteed* identical
across rows — and indeed both models report exactly 78.9% (38). Presenting it as a per-model
comparison column invites the reader to conclude the models "tied on retrieval" when they could
never differ.

Note the two calls also use different `top_k` paths: `_seed_ids` passes `top_k=k`, while
`run_ask` uses `final_top_k` from config. Since `HybridRetriever` sizes its rerank pool as
`max(final_k * 4, final_k)` ([hybrid.py:90](src/lds_study/index/hybrid.py#L90)), a `--k` other
than `final_top_k` measures recall over a differently-reranked pool than the one the generator
saw.

**Remediation:** Retrieve once per question, reuse the result for both recall and generation
(pass the hits into `run_ask`, or cache in the retriever). Move Recall@k out of the per-model
table into a single retrieval-quality section.

### 8. `--models` default silently drops the third shortlist entry. *(Low)*

[run.py:163-165](src/lds_study/eval/run.py#L163-L165) takes `shortlist[:2]` with no warning,
while the plan names three candidates and `configs/models.yaml` lists three. A user running
`lds eval` with no flags gets a two-model table and no indication `gpt-oss:20b` was skipped.

**Remediation:** Default to the full shortlist, or print which entries were dropped.

### 9. The manual 1–5 quality column is write-only. *(Low)*

The plan asks for "a manual 1-5 quality column." `quality_manual`
([metrics.py:25](src/lds_study/eval/metrics.py#L25)) is always `""` in automated runs and is
rendered blank. Re-running writes a new file (`-2`, `-3`) rather than clobbering, which is good,
but there is no mechanism to carry hand-entered scores forward into the next run, so any manual
scoring is orphaned on the first re-run.

**Remediation:** Read prior scores from the JSON sidecar keyed by `(question_id, model)` and
pre-populate, or document that manual scoring happens on a frozen report only.

### 10. `private/` and the PR5 adapters plan doc are outside PR4's stated scope. *(Trivial / Noted)*

The diff adds a `private/` gitignore entry plus a new `MONITORED_PREFIXES` member
([scripts/check_staged_data.py:22-23](scripts/check_staged_data.py#L22-L23)) for "local
Conference fetch" tooling the plan never mentions, and the working tree carries an untracked
`plans/draft/publishable-vs-personal-adapters-grok-2026-07-21.md`. Both are defensible
directionally — `private/` fails closed and the plan doc is not code — but they are drive-by
scope in a PR4 diff and the `private/` gate change has no test.

**Remediation:** No action required for merge; split into their own commit if you want a clean
PR4 boundary.

### 11. The eval's headline product finding is buried in report prose rather than raised as a blocker. *(Noted — no action)*

The report's own data shows the assistant answering
`"What did the prophet say in last Tuesday's unpublished private meeting?"` with
`status: ok` and `coverage: 1.00`, and 8 of 12 adversarial items likewise. The plan's PR3
done-when required out-of-corpus questions to hit `no_evidence`/`unsupported` "rather than a
fabrication." PR4 correctly *measured* the gap — that is exactly what an eval harness is for,
and the report notes it honestly at
[outputs/eval/2026-07-21.md:32-34](outputs/eval/2026-07-21.md#L32-L34). Flagging it here only so
it is not lost: baselining 33% adversarial refusal as the PR5 floor institutionalizes a
groundedness failure the plan named as the core product risk.

## Net assessment

**Safe to merge as PR4.** The plan's stated gate — a ≥2-generator comparison table committed
under `outputs/eval/` — is genuinely met with a real run, tests and lint are green, and no
copyrighted content or index artifact is staged. The harness is well-factored (golden / metrics /
report / run split cleanly, `emit=False` is a minimal and correct change to `run_ask`).

Worth fixing **before PR5 reads these numbers**, in order: finding 1 (the unmeetable
`min_adversarial_refusal` floor), finding 2 (refusal and citation-validity gates that fight each
other), finding 3 (no score data, so `min_score`/`min_coverage` remain unclosable). Those three
are the difference between a baseline and a number-shaped placeholder.

Fix opportunistically: findings 4 and 5 (copyright-gate coverage and report provenance — cheap,
and both sit on the plan's binding legal constraint) and finding 6 (fail-fast on a bad model id).
Findings 7–11 are cleanup.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **61 passed in 6.09s** (5 new in `test_pr4_eval.py`)
- `.\.venv\Scripts\python.exe -m ruff check src tests scripts` → **All checks passed!**
- `.\.venv\Scripts\python.exe -m lds_study.cli eval --help` → exit 0, all 8 options wired
- `.\.venv\Scripts\python.exe -m lds_study.cli eval --buckets nope --retrieval-only` → `eval failed: unknown buckets: ['nope']` (exit 1, no traceback leaked)
- `git check-ignore -v outputs/eval/2026-07-21.md` → `.gitignore:37:!outputs/eval/**/*.md` (tracked); `…2026-07-21.json` → `.gitignore:32:outputs/**` (ignored). Correct split.
- Hand-recomputed every aggregate in the committed report from its own per-item rows: recall 30/38 = 78.9% (both models), citation 35/50 = 70.0% / 36/50 = 72.0%, adversarial 4/12 = 33.3% (both). All match — the report is a real run.
- Grep gate `baselines|min_recall_at_k|min_citation_validity|min_adversarial_refusal` across `src/ scripts/ .github/ tests/` → **no consumer** of `rag.yaml` `eval.baselines`; written-only, as expected for PR4.
- Cross-checked all 27 distinct `gold_chunk_ids` against `volume_slug`/`book_slug`/`chunk_id` in [chunk_scripture.py](src/lds_study/data/chunk_scripture.py) — including the non-obvious `dc/dc/19/23` double-slug and `pgp/moses/1/39`. All well-formed.
- Bucket census of `eval/golden.yaml`: 50 questions, 15/13/10/12 across the four plan buckets.
- Read `configs/models.yaml` shortlist (3 entries) against `run.py`'s `shortlist[:2]` default.
