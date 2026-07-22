# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 8 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows rounds [1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md)–[7](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-7.md).*

## Verdict: One Medium — a metric that vanishes is reported as "no regression."

Round 7's finding is fixed, and more thoroughly than I asked: `COMPARABILITY_FIELDS` gained both `golden_local_hash` **and** `source_counts`. Suite at **98 passed**, `ruff` clean.

Continuing round 7's lesson — probe the default path — I exercised the default multi-model configuration (the real `configs/models.yaml` shortlist has three models, so an unflagged `lds eval` evaluates all three). Multi-model comparison is correct: per-model deltas key by name, and a single degraded model is isolated (`coverage_fail_rate b: 0.0 -> 1.0 reg=True` while `a` and `c` stayed flat).

The defect is in how the comparison handles metrics that stop existing. A run where generation broke completely — every generation metric unmeasurable, `error_n` 0 → 50 — renders as `comparable: True`, `any_regressed: False`, and the report line **"Trend: no regression beyond tolerance."** over a table of `n/a`. `--check-baselines` catches it, but that flag is not the default, and the trend section is what a user reads to answer the question this PR exists to answer.

## Round 7 finding disposition

| # (R7) | Severity | Status | Evidence |
|---|---|---|---|
| 1 — changed local golden set → false regression | High | **Fixed, beyond scope asked** | `COMPARABILITY_FIELDS` is now `('golden_hash', 'golden_local_hash', 'k', 'profile', 'include_local', 'retrieval_only', 'buckets', 'limit', 'models', 'source_counts')` — both the hash and the independent count check |
| 2 | Noted | Unchanged, correctly | — |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema v1, aggregates-only** | Complete | Projection fail-closed; version + `items` enforced on read |
| **Step 1 — copyright boundary (both artifacts)** | Complete | Verified round 5 |
| **Step 1 — gitignore + allowlist** | Complete | Verified round 6 |
| **Step 4 — `--compare` resolution** | Complete | Verified rounds 5–7, incl. paths containing spaces |
| **Step 4 — comparability guard** | Complete | 10 fields; local-set change now refused |
| **Step 4 — multi-model comparison** | Complete | Newly verified: 3-model shortlist, per-model deltas, degraded model isolated |
| **Step 4 — deltas on missing metrics** | **Incorrect** | Finding 1 |
| **Step 4 — rendering, CLI, exit codes** | Complete | Verified rounds 4–6 |
| **Step 10 — tests** | Complete for what is compared | 98 pass; no case covers a metric going value → `None` |
| Steps 2, 3, 5–9 | Deferred-as-planned | — |

## Findings (ranked)

### 1. A metric that becomes unmeasurable is reported as "no regression." *(Medium)*

`_make_delta` sets `delta=None` whenever either side is `None` ([compare.py:175-178](../../src/lds_study/eval/compare.py#L175-L178)), and `_is_regressed` returns `False` for a `None` delta ([compare.py:129-130](../../src/lds_study/eval/compare.py#L129-L130)). So the transition *"0.95 → cannot be measured"* is indistinguishable from *"no data on either side."*

Simulating a run where the generator died — every generation metric `None`, `error_n` 0 → 50, retrieval untouched:

```
comparable : True
any_regressed: False
  recall@k               0.9  -> 0.9   delta=0.0  reg=False
  citation_validity      0.95 -> None  delta=None reg=False
  invalid_marker_rate    0.0  -> None  delta=None reg=False
  coverage_fail_rate     0.0  -> None  delta=None reg=False
  adversarial_refusal    0.9  -> None  delta=None reg=False

['**Trend:** no regression beyond tolerance.']
error_n compared? False
```

Three compounding pieces:

- **The verdict line is affirmatively wrong.** Not "insufficient data" — *"no regression beyond tolerance"*, printed under four `n/a` rows. Every other failure mode in this feature degrades to "not comparable" with the offending field named; this one degrades to reassurance.
- **`error_n` is recorded but never compared.** It is in `SUMMARY_AGGREGATE_KEYS` and lands in every summary, but is absent from `_PER_MODEL_METRIC_SPECS`, so 0 → 50 errors is invisible to the trend. Same shape as the `generated_at` (round 2) and `golden_local_hash` (round 7) findings: the datum that would catch it is already in the file, unread. Third instance of that pattern.
- **The denominators are also unread.** `citation_n`, `adversarial_n`, `recall_n`, `n_items` all ship in the summary. A run measuring 10 items and one measuring 1 compare as equals.

**What limits severity:** `--check-baselines` catches it — `meets_regression_baselines` treats `None` as failure (`got is None or got < floor`), so the gate correctly REVERTs. The markdown's pre-existing per-model table also shows the error count. And the plan does frame floors as the gate and `--compare` as the trend. But `--check-baselines` is opt-in, so plain `lds eval` on a broken run prints "no regression beyond tolerance" and exits 0 — and the plan equally requires the comparison to avoid *"printing misleading deltas."* A reassuring verdict over unmeasurable metrics is the most misleading delta available.

**Remediation:** In `_make_delta`, distinguish "absent on both sides" (`n/a`, no verdict) from "present then absent" — treat the latter as `regressed=True` with a `lost` verdict, or at minimum render `was 0.9500, now unmeasurable`. Suppress the "no regression" summary line whenever any delta is `None`, replacing it with a count of unmeasurable metrics. Adding `error_n` to the compared metrics (lower-is-better, tolerance 0) would catch the same class from the other direction, and gives PR6c's `lds iterate` a signal it will want.

### 2. Carried notes. *(Noted — no action)*

TOCTOU stem dedup; no committed summary yet; trend regression not gating the exit code; four pre-existing U+2192 arrows in `prepare` / `index` / `finetune-dataset`. Unchanged, all correct for PR6a.

## Net assessment

This is a judgment call rather than a blocker. The floors gate does catch the scenario, so nothing ships silently broken in the `--check-baselines` workflow the plan treats as authoritative — and PR6c's `lds iterate` runs the gate unconditionally, so the loop is safe by construction. What is wrong is the standalone `lds eval --compare` verdict, which a human reads directly. I would fix the summary line at minimum (cheap, no semantic change) and take the `regressed` reclassification if PR6c is going to consume `any_regressed` programmatically, which the plan implies it will.

Eight rounds in, the shape of what remains is clear: the core paths are correct and have been stable since round 3, and every finding since round 5 has been about *how the tool describes edge states* rather than whether it measures correctly. That is a reasonable place for a PR to be. The genuinely untested surface is unchanged and unchangeable from here — the plan's local block against a real index with Ollama, which is where a broken-generator run would actually originate.

On method: rounds 7 and 8 both came from the same shift — stop probing what a user might type, start running what a user gets by default. That heuristic is now spent too. The default single-model, multi-model, retrieval-only, and full-generation paths have all been executed; the remaining defaults are the ones requiring hardware I do not have.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **98 passed in 7.76s** (86 → 89 → 92 → 93 → 94+1F → 95 → 97 → 98)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- **R7 regression check**: `COMPARABILITY_FIELDS` now includes `golden_local_hash` and `source_counts` (10 fields)
- **Default multi-model path** (new this round): `configs/models.yaml` shortlist of 3, `models=None` → all three evaluated; summary aggregates `['a','b','c']`; per-model verdicts for all three; comparison `comparable: True` with deltas keyed per model; a single degraded model isolated correctly (`coverage_fail_rate b: 0.0 -> 1.0 reg=True`, `a`/`c` flat)
- **Finding 1 repro**: prev with full metrics vs curr with all generation metrics `None` and `error_n=50` → `comparable: True`, `any_regressed: False`, section renders `**Trend:** no regression beyond tolerance.`; `error_n` absent from all deltas
- Confirmed `meets_regression_baselines` treats `None` as failure, so `--check-baselines` still REVERTs on the same input (the mitigation that caps this at Medium)
- Read `_make_delta`, `_is_regressed`, `_is_improved`, `_PER_MODEL_METRIC_SPECS` and `SUMMARY_AGGREGATE_KEYS` to confirm the recorded-but-uncompared fields (`error_n`, `citation_n`, `adversarial_n`, `recall_n`, `n_items`)

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index.*
