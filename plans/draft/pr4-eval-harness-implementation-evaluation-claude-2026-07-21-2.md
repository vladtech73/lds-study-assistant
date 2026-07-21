# Eval Harness (PR4) — Implementation Evaluation (Round 2)

*Evaluator: claude · 2026-07-21 · Reviews PR4 of `claude-2026-07-20.md` against branch `pr4-eval-harness`, uncommitted working tree vs `HEAD` (`cd16b2f`). Follows [round 1](pr4-eval-harness-implementation-evaluation-claude-2026-07-21.md).*

## Verdict: Harness code is now good; the numbers it feeds PR5 got worse, not better — do not merge the config until one clean re-run exists

Round 1's ten findings were taken seriously and the *code* fixes are genuinely well done: retrieval
happens once and is shared, scores are persisted and a real score-distribution report was
generated, the citation metric is scoped and split into three counters, `golden.local.yaml` is on a
verified denylist, reports carry provenance, and a preflight catches missing models. Findings 4, 5,
6, 7, 8 are closed outright.

But the two hardest findings were closed on paper rather than in fact. `min_citation_validity:
0.639` in [configs/rag.yaml](configs/rag.yaml) was hand-derived from the **losing** model under the
**superseded** metric definition — the shipped code computes `0.663` from the same stored run, and
the new metric's true value is not computable from any surviving artifact. And `retrieval.min_score`
was raised `0.0 → 0.05`, a live change to `lds ask` that **drops 33.2% of all grounded seed chunks**
(98/295, measured from the committed sidecar) and shrinks median context 8 → 6.5 — after which
neither baseline was re-measured. All three PR5 floors now describe a configuration that no longer
ships.

The harness is mergeable. `configs/rag.yaml`'s `eval.baselines` block is not.

## Round-1 finding disposition

| # | Round-1 finding | Status |
|---|---|---|
| 1 | `min_adversarial_refusal: 0.5` unmeetable clamp | **Fixed in code** — `max(0.5, …)` removed ([metrics.py:192-197](src/lds_study/eval/metrics.py#L192-L197)), `0.3` shipped, regression test added. Value is now stale for a different reason — see finding 3 below. |
| 2 | Citation validity counted correct refusals as failures | **Fixed in code, wrong in config** — scoped to non-adversarial ([metrics.py:136-140](src/lds_study/eval/metrics.py#L136-L140)), split into `invalid_marker_rate` / `coverage_fail_rate`, `test_citation_validity_excludes_adversarial_refusals` added. The number written to `rag.yaml` is wrong — finding 1 below. |
| 3 | No score data → `min_score`/`min_coverage` unclosable | **Fixed** — `seed_scores`/`top1_score`/`topk_min_score` persisted, `score_distribution()` + `suggest_min_score()` + `coverage_stats()` added, real retrieval-only run committed at [outputs/eval/2026-07-21-scores.md](outputs/eval/2026-07-21-scores.md). Consequences unevaluated — finding 2. |
| 4 | Copyright gate missed `eval/golden.local.yaml` | **Fixed** — `DENYLIST_PATTERNS` ([check_staged_data.py:26-30](scripts/check_staged_data.py#L26-L30)) applied before the monitored-prefix check, with a test. Verified live below. |
| 5 | Reports didn't record `include_local` | **Fixed** — header carries `include_local`, `source_counts`, `golden.yaml` sha256[:16]; `source` column per item ([report.py:84-85](src/lds_study/eval/report.py#L84-L85)). Partial gap — finding 7. |
| 6 | Missing model → plausible-looking report | **Fixed** — `preflight_ollama_models()` ([run.py:83-107](src/lds_study/eval/run.py#L83-L107)); `error_n`/`first_error` rendered in the comparison table. |
| 7 | Double retrieval; recall shown per-model | **Fixed** — one `retrieve()` per question reused across models ([run.py:242-256](src/lds_study/eval/run.py#L242-L256)); recall moved to a shared "Retrieval quality" section. Introduced a new coupling — finding 5. |
| 8 | `--models` default dropped shortlist entry 3 | **Fixed in code** ([run.py:209-210](src/lds_study/eval/run.py#L209-L210)), help text now wrong — finding 6. |
| 9 | Manual quality column write-only | **Not addressed** — still blank-only, still orphaned on re-run. |
| 10 | `private/` scope creep, untested | **Partially** — now covered by `test_denylist_rejects_golden_local_and_private`. Still out of PR4 scope. |
| 11 | Weak adversarial refusal (noted) | **Acted on** via `min_score: 0.05` — unverified, see finding 2. |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Golden set (50 q, 4 buckets, public-domain)** | Complete | Unchanged from round 1; `sha256[:16]=d704c8506d24e11d` now pinned into reports. |
| **`lds eval` command** | Complete | Runs; `--buckets nope` fails cleanly. Help text stale (finding 6). |
| **Metrics** | Complete | recall@k shared, citation validity (non-adv), invalid-marker rate, coverage-fail rate, adversarial refusal, error count. |
| **Score-based `min_score` calibration** | Complete (measurement) / Missing (verification) | [2026-07-21-scores.md](outputs/eval/2026-07-21-scores.md) is a genuine `retrieval_only=True` artifact. Every claim in the `rag.yaml` comment checks out against it (verified below). No post-change run — finding 2. |
| **Gate: ≥2-generator comparison committed** | Complete, but the artifact is now hand-edited | [outputs/eval/2026-07-21.md](outputs/eval/2026-07-21.md) — finding 4. |
| **Gate: thresholds written to `configs/rag.yaml`** | **Incorrect** | Findings 1–3. |
| **Decisions appendix: `min_coverage` real number** | Addressed | Kept at 0.8 with measured justification (`ok` answers cluster near 1.0; failures 0.17–0.75). Deciding to keep a value on evidence is a legitimate close. |
| **Copyright gate** | Complete | Live run below. |
| **Tests / lint** | Complete | `pytest -q` → **63 passed in 6.17s**; `ruff check` → clean. No network reached (preflight is skipped whenever `generators` is injected). |

## Findings (ranked)

### 1. `min_citation_validity: 0.639` is arithmetically wrong, taken from the losing model, and not reproducible by the shipped code. *(Critical)*

[configs/rag.yaml:38](configs/rag.yaml#L38) ships:

```yaml
    min_citation_validity: 0.639    # 0.9 * ~0.711 scoped non-adv (excl. adversarial)
```

and the errata table in [outputs/eval/2026-07-21.md:13](outputs/eval/2026-07-21.md#L13) repeats
`~27/38 ≈ 0.711 × 0.9`. Recomputed directly from the stored sidecar `outputs/eval/2026-07-21.json`:

```
qwen2.5:14b non-adv n=38  cite_ok=27/38  0.7105
qwen3:14b   non-adv n=38  cite_ok=28/38  0.7368
```

Three defects compound:

1. **Wrong model.** `suggested_baselines()` takes `max(cites)`
   ([metrics.py:195](src/lds_study/eval/metrics.py#L195)). Best is qwen3's 0.7368, so the shipped
   code would emit **0.663**, not 0.639. The errata used qwen2.5, the model that scored lower.
2. **Wrong metric.** Those counts come from the *old* rule (`unsupported` → always invalid). The
   new rule ([run.py:172-176](src/lds_study/eval/run.py#L172-L176)) sets `citation_valid =
   len(invalid) == 0`, which promotes every coverage-only `unsupported` item to *valid*. That is
   exactly the round-1 fix — and it means the true new-metric rate is strictly **≥ 0.7368**.
3. **Not reproducible.** The stored sidecar's item schema is
   `['bucket','citation_coverage','citation_valid','error','expect_refuse','id','model','quality_manual','recall_hit','recall_rank','refusal_correct','refused','status']` — no
   `invalid_markers`. The new metric cannot be recomputed from any surviving artifact at any value.

So a number presented as a computation ("0.9 × ~0.711") is a hand-fit to a superseded definition,
and it is the tighter of the two candidate values — it will reject PR5 adapters more readily than
the measured floor would. Round 1's finding 2 was closed in the code and re-opened in the config.

**Remediation:** Re-run `lds eval` with both models under the shipped config and paste the
harness-emitted `eval.baselines` block verbatim. Do not hand-derive floors from a prior run.

### 2. `retrieval.min_score` was raised `0.0 → 0.05` — a live change to `lds ask` that removes a third of grounded context — and nothing was re-evaluated afterwards. *(Critical)*

The calibration itself is sound. Every claim in the
[configs/rag.yaml:14-18](configs/rag.yaml#L14-L18) comment reconciles against the committed scores
data — I checked each: 9/12 adversarial top-1 scores fall below 0.05 ✓; exactly one grounded item
(`lp-004`, top1 0.028, recall N) is lost ✓; at 0.12 exactly two *recall-hit* grounded items
(`ds-010` 0.063, `ds-013` 0.102) would drop ✓. That is real work and it closes round-1 finding 3.

The problem is what happens next. `min_score` is applied **inside** `HybridRetriever`, before top-k
truncation ([hybrid.py:107](src/lds_study/index/hybrid.py#L107)), not only in `ask.py`. So it
filters *every individual chunk*, not just the top-1 the calibration examined. Computed from
`outputs/eval/2026-07-21-scores.json`:

```
grounded items: 38
total seed hits: 295   below 0.05: 98  (33.2%)
items whose entire seed set falls below 0.05: 1   (lp-004)
items where the gold-hit chunk itself scores <0.05: 0
median context size: 8.0 -> 6.5
worst shrinkage: lp-004 8->0, vl-003 8->1, ds-003 8->1, ds-010 8->1, ds-013 8->1, lp-002 8->1
```

Recall survives — no gold chunk is dropped, which is the good news the calibration predicted. But
**a third of the generation context disappears**, and five grounded questions drop to a single
chunk. `citation.min_coverage: 0.8` requires 80% of claim-bearing paragraphs to carry a valid
marker; `ds-003`, `ds-010`, `ds-013` all returned `status: ok` with `coverage 1.00` at eight chunks
and will now be synthesizing from one. The `doctrinal_synthesis` bucket was 13/13 `ok`; that is very
unlikely to hold.

`topk_min_score` is captured on every item ([metrics.py:20](src/lds_study/eval/metrics.py#L20)) and
never rendered in either report — the data to see this was collected and then not looked at.

**Remediation:** Re-run the full two-model eval at `min_score: 0.05` before merging the config
change, and compare the `coverage_fail_rate` column against the 0.0 run. If coverage failures spike,
the right fix is a per-item floor (require *at least N* qualifying seeds) rather than a flat
per-chunk threshold.

### 3. `min_adversarial_refusal: 0.3` is now a floor roughly 2.5× below actual shipping behavior. *(High)*

`0.3 = 0.9 × 0.333` is correct arithmetic for the 4/12 refusal rate measured at `min_score: 0.0`.
But nine of the twelve adversarial items have a **top-1** score below 0.05
([2026-07-21-scores.md:80-91](outputs/eval/2026-07-21-scores.md#L80-L91)) — and top-1 is the maximum,
so for those nine the entire seed set is filtered out, `qualifying_seeds` is empty
([ask.py:95](src/lds_study/rag/ask.py#L95)), and `lds ask` returns `no_evidence` before generating.
Adversarial refusal under the shipping config should be **≥ 9/12 = 75%**, not 33%.

A regression floor of 0.3 against real behavior of ~0.75 cannot detect a PR5 adapter that halves
adversarial refusal. The plan calls this metric out as the guard on "the core product risk"
(misquotation / false attribution); a gate this loose is worse than none, because it will report
green.

**Remediation:** Same re-run as findings 1–2. Expect the floor to land near 0.675.

### 4. The committed comparison report is now a hand-edited document, not a harness artifact. *(Medium)*

[outputs/eval/2026-07-21.md](outputs/eval/2026-07-21.md) opens with a manually inserted
`Round-1 remediation errata` blockquote and errata table (lines 3-20), and its
`Suggested regression baselines` block (lines 39-45) has been **edited in place** to show `0.639` /
`0.3` — while the stored sidecar for that same run still reads
`{'min_recall_at_k': 0.711, 'min_citation_validity': 0.648, 'min_adversarial_refusal': 0.5}`. The
markdown and its own JSON now disagree, and neither matches what
`write_markdown_report()` would produce today (the current writer emits a six-column generation
table with `Invalid markers` / `Coverage fail` / `errors`; the committed file still has the old
four-column one).

The file states "A full re-run with the fixed counters was not required to correct the PR5 floors."
As finding 1 shows, it was — the hand correction is wrong. This is the shape of false confidence the
review is meant to catch: an errata that *looks* like reconciliation and instead launders a guess
into `configs/rag.yaml`.

[MODEL_CARD.md:33](MODEL_CARD.md#L33) points a reader at this file as "Latest comparison."

**Remediation:** Regenerate under the shipped config, commit the new file, and either delete the
hand-annotated one or keep it explicitly labelled as a superseded pre-`min_score` run. Never edit a
generated report's numbers in place.

### 5. `--k` now silently changes what the generator sees, not just the recall cutoff. *(Medium)*

Fixing round-1 finding 7 coupled the two paths. `run_eval` retrieves once with `top_k=k`
([run.py:255](src/lds_study/eval/run.py#L255)) and passes the result straight into `run_ask` via the
new `retrieval=` parameter ([run.py:156](src/lds_study/eval/run.py#L156),
[ask.py:64](src/lds_study/rag/ask.py#L64)). Previously `run_ask` retrieved independently at
`final_top_k`.

So `lds eval --k 20` no longer measures "recall@20 with the production 8-chunk pipeline" — it
measures a 20-chunk generation pipeline that `lds ask` never runs. And since `HybridRetriever` sizes
its rerank pool as `max(final_k * 4, final_k)` ([hybrid.py:90](src/lds_study/index/hybrid.py#L90)),
the candidate set is reranked differently too. It happens to be harmless today only because
`eval.recall_k: 8 == retrieval.final_top_k: 8`.

**Remediation:** Retrieve at `final_top_k` for generation and slice to `k` for the recall
computation, or refuse `--k > final_top_k` with an explicit error.

### 6. Stale `--models` help text contradicts the fixed behavior. *(Low)*

[cli.py:192](src/lds_study/cli.py#L192) still reads `"(default: first two shortlist entries)"`.
`run_eval` now uses the entire shortlist ([run.py:209-210](src/lds_study/eval/run.py#L209-L210)), so
a bare `lds eval` will run three models including `gpt-oss:20b` — roughly a 50% longer run than the
help promises. Related trivia: `render_comparison_table(aggs, *, k)`
([report.py:28](src/lds_study/eval/report.py#L28)) no longer uses `k` at all now that recall moved
out, but callers and the test still pass it.

**Remediation:** Update the help string; drop the dead `k` parameter.

### 7. `golden_hash` covers only `golden.yaml`, not the local file it is meant to disambiguate. *(Low)*

[run.py:232-233](src/lds_study/eval/run.py#L232-L233) hashes `default_golden_path()` only. When
`include_local=True` (the default), the report records `include_local=True` and
`source_counts={'golden': 50, 'local': N}` — good — but the hash still describes only the committed
half, so two runs with different local question sets are indistinguishable by hash. Round-1 finding
5 is 90% closed; this is the remainder.

**Remediation:** Hash the concatenation of both files when local is included, or emit a second
`golden_local_hash`.

### 8. Manual 1–5 quality column remains write-only. *(Low — carried from round 1)*

Unchanged: `quality_manual` is always `""`, rendered blank, and any hand-entered score is orphaned
the next time a report is generated. The plan asks for "a manual 1-5 quality column" as one of four
metrics; three of four are automated and this one has no workflow.

### 9. `preflight_ollama_models` is skipped whenever any generator is injected. *(Trivial)*

[run.py:239](src/lds_study/eval/run.py#L239) gates on `generators is None`. Injecting a mock for one
model out of three skips the availability check for the other two, which then fail 50 questions
later — the exact failure mode round-1 finding 6 addressed. It cannot bite from the CLI (which never
injects), and the gate is what keeps the test suite off the network, so this is a correct trade with
a rough edge.

**Remediation:** Preflight only the models *not* present in `generators`.

## Net assessment

**Merge the harness; hold the config.** [src/lds_study/eval/](src/lds_study/eval/),
[tests/test_pr4_eval.py](tests/test_pr4_eval.py), the `check_staged_data.py` denylist, and the
`retrieval=` plumbing in `ask.py` are all in good shape and close five round-1 findings outright.
The score-distribution work is the strongest part of this round — it turned an unclosable question
into a defensible decision with data behind it.

What must not ship as-is is the `eval.baselines` block in [configs/rag.yaml](configs/rag.yaml) and
the `min_score: 0.05` change that invalidated it. One command fixes all three of findings 1–3:

```powershell
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default --models qwen2.5:14b,qwen3:14b
```

run under the shipped config, with the emitted baselines block pasted in verbatim. Until that
exists, PR5's keep-or-revert gate compares an adapter against numbers measured on a configuration
the repo no longer has — one floor too tight (finding 1), one far too loose (finding 3), and a
context change of unknown sign sitting underneath both (finding 2).

Findings 5–9 are cleanup and need not block.

One process note worth stating plainly: rounds 1's two hardest findings were both closed with a
correct code change plus a hand-written number. The code changes were good. The hand-written numbers
were not, and the errata block made them look verified. Re-running the harness is cheaper than
reasoning about what it would have said.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **63 passed in 6.17s** (6 PR4 tests + 1 new denylist test in `test_pr1_scaffold.py`); no network, `preflight` bypassed via injected `generators`
- `.\.venv\Scripts\python.exe -m ruff check src tests scripts` → **All checks passed!**
- `.\.venv\Scripts\python.exe scripts\check_staged_data.py --paths eval/golden.local.yaml eval/byof.local.yaml private/x.py data/.gitkeep outputs/eval/2026-07-21.md` → exit 1, rejecting exactly the three restricted paths and passing both legitimate ones. Round-1 finding 4 confirmed fixed, including the `eval/*.local.yaml` glob.
- Recomputed non-adversarial citation validity from `outputs/eval/2026-07-21.json`: qwen2.5 `27/38 = 0.7105`, qwen3 `28/38 = 0.7368` → `suggested_baselines` would emit **0.663**, not the shipped 0.639 (finding 1). Confirmed the stored item schema has no `invalid_markers`, so the new metric is uncomputable from it.
- Quantified `min_score: 0.05` from `outputs/eval/2026-07-21-scores.json`: **98/295 grounded seed hits (33.2%) fall below the threshold**; median context 8.0 → 6.5; `lp-004` → 0 chunks; `vl-003`/`ds-003`/`ds-010`/`ds-013`/`lp-002` → 1 chunk; **0** gold-hit chunks lost (finding 2).
- Hand-verified every quantitative claim in the `configs/rag.yaml` `min_score` comment against `2026-07-21-scores.md`: 9/12 adversarial blocked at 0.05 ✓; 1 grounded lost, no recall hit ✓; 2 recall-hit grounded lost at 0.12 ✓. Calibration reasoning is accurate.
- Traced `min_score` application points: [hybrid.py:107](src/lds_study/index/hybrid.py#L107) (pre-truncation, per-chunk) and [ask.py:95](src/lds_study/rag/ask.py#L95) (seed gate) — confirming the change is not top-1-only as the calibration assumed.
- Confirmed adversarial top-1 scores: 9 of 12 below 0.05, implying refusal ≥ 75% under the shipped config vs the 33.3% the `0.3` floor was derived from (finding 3).
- Diffed `outputs/eval/2026-07-21.md` against its own `.json` sidecar and against the current `write_markdown_report()` column set — all three disagree (finding 4).
- `git check-ignore -v` on both report files: `.md` tracked, `.json` ignored. Unchanged and correct.
