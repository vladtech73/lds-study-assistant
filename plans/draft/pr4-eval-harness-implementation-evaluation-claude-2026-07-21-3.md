# Eval Harness (PR4) — Implementation Evaluation (Round 3)

*Evaluator: claude · 2026-07-21 · Reviews PR4 of `claude-2026-07-20.md` against branch `pr4-eval-harness`, uncommitted working tree vs `HEAD` (`cd16b2f`). Follows [round 1](pr4-eval-harness-implementation-evaluation-claude-2026-07-21.md) and [round 2](pr4-eval-harness-implementation-evaluation-claude-2026-07-21-2.md).*

## Verdict: Ship it — the re-run happened, the numbers now reconcile, and the remaining issues are about what the gate does not measure rather than what it measures wrongly

Round 2's three blocking findings are closed properly. A real two-model run at the shipped
`min_score: 0.05` exists at [outputs/eval/2026-07-21-r2.md](outputs/eval/2026-07-21-r2.md); I
recomputed every aggregate in it from its own sidecar and all six figures match exactly. The
baselines in [configs/rag.yaml](configs/rag.yaml) are now byte-identical to harness output rather
than hand-derived, the stale report is renamed and clearly labelled `(SUPERSEDED)`, and the `--k`
guard and `--models` help text are fixed and verified live. Round 2's prediction that adversarial
refusal would jump to ≥75% under the new threshold was correct — it landed at 91.7% / 75.0%.

What remains is a different class of problem. The three shipped floors are honest measurements, but
they are anchored to `max()` across models, so `min_adversarial_refusal: 0.825` is a floor that
**qwen3:14b already fails at 0.75** — the same "floor above a real model" shape as round 1, arrived
at honestly this time. And the metric where the system is actually weak — coverage failure at
24.3% / 18.9% — has **no floor at all**, because `suggested_baselines()` only emits three. A PR5
adapter that doubles coverage failures passes every gate green.

None of that blocks PR4's stated gate, which is met. It should be fixed before PR5 relies on these
numbers.

## Round-2 finding disposition

| # | Round-2 finding | Status |
|---|---|---|
| 1 | `min_citation_validity: 0.639` hand-derived, wrong model, unreproducible | **Fixed** — re-run emitted `0.9`; `rag.yaml:34-35` now says "Pasted verbatim from harness output … do not hand-edit". Sidecar `suggested_baselines` matches the config exactly. |
| 2 | `min_score: 0.05` shipped un-evaluated | **Fixed** — full two-model run at 0.05 committed. Report now also prints "Median grounded seed-hit count: 7", surfacing the context shrinkage. |
| 3 | `min_adversarial_refusal: 0.3` stale and loose | **Fixed as measurement** (now 0.825 from a real 11/12), **new problem as a gate** — finding 1 below. |
| 4 | Committed report hand-edited | **Fixed** — renamed to `2026-07-21-pre-minscore-superseded.md` with a `(SUPERSEDED)` title and a "Do not use for PR5 floors" banner; `MODEL_CARD.md` repointed at the r2 run. One dangling reference remains — finding 4. |
| 5 | `--k` silently widened generation context | **Fixed** — retrieval now happens at `final_top_k` and recall slices it ([run.py:259-277](src/lds_study/eval/run.py#L259-L277)); `k > final_top_k` raises with an explanatory message. Verified live. |
| 6 | Stale `--models` help text | **Fixed** — now reads "default: full shortlist in models.yaml". Verified in `--help`. |
| 7 | `golden_hash` omitted the local file | **Fixed** — `golden_local_hash` computed and rendered ([run.py:244-246](src/lds_study/eval/run.py#L244-L246)); r2 header shows `golden.local.yaml sha256[:16]=n/a`. |
| 8 | Manual quality column write-only | **Not addressed** (third round). |
| 9 | Preflight skipped when any generator injected | **Fixed** — now checks only models absent from `generators` ([run.py:252-257](src/lds_study/eval/run.py#L252-L257)); suite still runs offline. |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Golden set** | Complete | Unchanged; `sha256[:16]=d704c8506d24e11d` pinned in both reports. |
| **`lds eval` command** | Complete | `--k 20 --retrieval-only` → clean `ValueError` with remediation text, exit 1. Help text accurate. |
| **Metrics** | Complete | recall@k (shared), citation validity (non-adv), invalid-marker rate, coverage-fail rate, adversarial refusal, error count. |
| **Gate: ≥2-generator comparison committed under `outputs/eval/`** | **Complete** | [2026-07-21-r2.md](outputs/eval/2026-07-21-r2.md), `qwen2.5:14b` vs `qwen3:14b`, n=50 each, 0 errors, report-only. |
| **Gate: thresholds written into `configs/rag.yaml`** | **Complete (accurate)** | Config matches sidecar `{'min_recall_at_k': 0.711, 'min_citation_validity': 0.9, 'min_adversarial_refusal': 0.825}` exactly. Coverage of the gate is incomplete — finding 2. |
| **Decisions appendix: `min_coverage` real number** | Addressed | Kept 0.8 on evidence (`ok` answers median coverage 1.0). |
| **Plan: "whichever wins becomes the documented default in `configs/models.yaml`"** | **Partial** | The decision (keep qwen2.5) is now better supported than before, but the comment justifying it is stale and its file reference is broken — finding 4. |
| **Tests / lint** | Complete, one gap | `pytest -q` → **63 passed in 5.31s**; `ruff check` → clean. No test for the new `--k` guard — finding 5. |

## Findings (ranked)

### 1. `min_adversarial_refusal: 0.825` is a floor that qwen3:14b already fails, and it rests on a 3-item coin flip. *(High)*

[configs/rag.yaml:38](configs/rag.yaml#L38) ships `0.825`, correctly emitted as `0.9 × 0.9167`
(qwen2.5's 11/12). But the same run measured qwen3:14b at **9/12 = 0.75**. `suggested_baselines()`
takes `max()` across models ([metrics.py:197](src/lds_study/eval/metrics.py#L197)), so the floor is
pinned to the better model and the alternative candidate fails it before any adapter is trained.
This is round-1 finding 1 in a new costume: honestly measured this time, but structurally the same
— a gate no real configuration in the repo can clear except one.

Worse, look at where the model-dependent signal actually is. From the sidecar:

```
qwen2.5:14b  adv statuses: {'no_evidence': 9, 'unsupported': 2, 'ok': 1}   -> 11/12
qwen3:14b    adv statuses: {'no_evidence': 9, 'ok': 3}                     -> 9/12
```

Nine of twelve adversarial refusals are `no_evidence` — decided by retrieval, identical for both
models, fully deterministic. **Only three items are model-dependent**, and the entire 11-vs-9 gap is
those three. A floor of 0.825 requires ≥10/12, i.e. at least one of those three going the right way.
And `ask.temperature: 0.2` ([configs/rag.yaml:31](configs/rag.yaml#L31)) means the first generation
pass is stochastic — a second run of the identical config can produce a different number on exactly
the items the floor hinges on.

So the tightest gate in PR5 is 90% of a single stochastic observation with an effective sample size
of three.

**Remediation:** Anchor floors to the **default generator** (`generator.id`, currently qwen2.5)
rather than `max()` across the shortlist, so promoting a different model is not blocked by the one
it is being compared against. If the floors are meant to survive re-runs, either run the adversarial
bucket at `temperature: 0` or take the min across two runs. At n=12 the honest move is to record the
count (`11/12`) alongside the rate and treat single-item moves as noise.

### 2. The metric that reveals the system's actual weakness has no baseline. *(High)*

Round 1 correctly separated "fabricated a citation" from "failed the coverage gate." The
consequence, visible now that a clean run exists, is that `citation_validity_rate` measures only
fabrication — and fabrication is essentially solved:

```
qwen2.5:14b  cite validity 97.3% (36/37)   invalid markers 2.7%   coverage fail 24.3% (9/37)
qwen3:14b    cite validity 100.0% (37/37)  invalid markers 0.0%   coverage fail 18.9% (7/37)
```

`vl-004` illustrates it: `status: unsupported`, `coverage 0.50`, and `cite_ok: Y`. The answer was
refused for insufficient grounding, and it counts as a citation success.

So `min_citation_validity: 0.9` guards a metric already at 97–100%, while roughly **one in five
grounded questions produces no usable answer** and nothing guards that at all —
`suggested_baselines()` emits three keys and `coverage_fail_rate` is not among them
([metrics.py:191-198](src/lds_study/eval/metrics.py#L191-L198)). A PR5 style adapter that pushes
coverage failure from 18.9% to 40% would pass `min_recall_at_k`, `min_citation_validity`, and
`min_adversarial_refusal` simultaneously.

The plan's step 7 requires keeping an adapter "only if citation validity and adversarial refusal rate
meet or beat the PR4 baseline." Under the round-1 metric that phrase covered coverage failures;
under the round-2 metric it no longer does, and no floor was added to replace the coverage the split
removed.

**Remediation:** Add `max_coverage_fail_rate` (≈ `1.1 × worst observed`, so ~0.27) to
`suggested_baselines()` and `rag.yaml`. It is the one number in this run that describes user-visible
quality.

### 3. `suggest_min_score` is now circular and will ratchet upward on every re-run. *(Medium)*

[2026-07-21-r2.md:19-22](outputs/eval/2026-07-21-r2.md#L19-L22) reports:

```
- Grounded:    n=37 min=0.056  p25=0.3313 …
- Adversarial: n=3  min=0.0502 p25=0.0574 p75=0.0883 max=0.112
- Suggested `retrieval.min_score` (midpoint adv p75 / grounded p25): **0.2098**
```

Both distributions are measured **after** the retriever filtered at `min_score: 0.05`
([hybrid.py:107](src/lds_study/index/hybrid.py#L107)), so `min=0.0502` and `min=0.056` are artifacts
of the threshold, not observations. Adversarial `n` collapsed from 12 to 3 for the same reason. The
suggestion is computed on the survivors of the previous suggestion; following it would push
`min_score` to 0.21, then higher again next run, with no signal that anything is wrong.

The pre-change [2026-07-21-scores.md](outputs/eval/2026-07-21-scores.md) run was methodologically
sound precisely because it was taken at `min_score: 0.0`. Every subsequent run is not, and the report
presents the number with no caveat.

**Remediation:** Compute the score distribution from an unfiltered retrieval (force `min_score=0`
for the calibration pass), or suppress the suggestion and print "calibration requires
`min_score: 0.0`" whenever the configured threshold is non-zero.

### 4. `configs/models.yaml` cites a file that no longer exists and numbers the re-run superseded. *(Medium)*

[configs/models.yaml:5-7](configs/models.yaml#L5-L7):

```yaml
  # PR4 eval (outputs/eval/2026-07-21.md): qwen3:14b edged citation validity
  # (72% vs 70%); recall@8 and adversarial refusal tied. Keep Qwen2.5 as interim
  # default until adversarial refusal improves (both at 33% with min_score 0.0).
```

`outputs/eval/2026-07-21.md` was renamed to `2026-07-21-pre-minscore-superseded.md` — the path in
the comment resolves to nothing. Every figure quoted is from the superseded run: refusal is no longer
"tied at 33%" (91.7% vs 75.0%), and "72% vs 70% citation validity" is now "100% vs 97.3%" under a
different definition.

The plan's PR4 done-when is "Whichever wins becomes the documented default in `configs/models.yaml`."
The *decision* to keep qwen2.5 is now better supported than it was — it wins adversarial refusal
decisively (11/12 vs 9/12) — but the documented reasoning points a future reader at a deleted file
and at numbers the repo has explicitly disowned. The stated condition ("until adversarial refusal
improves") has in fact been met, which makes the comment read as blocking a promotion that the data
no longer blocks.

**Remediation:** Rewrite the comment against `2026-07-21-r2.md`: qwen2.5 retained on adversarial
refusal (11/12 vs 9/12); qwen3 better on citation validity (100% vs 97.3%) and coverage fail (18.9%
vs 24.3%); note the n=12 caveat from finding 1.

### 5. The new `--k` guard has no test. *(Low)*

[run.py:206-212](src/lds_study/eval/run.py#L206-L212) adds the `k > final_top_k` `ValueError` that
closes round-2 finding 5, and it works — verified live. But the suite is still **63 tests**, the same
count as round 2: no test was added for the guard, the `final_top_k` retrieval path, or the
`golden_local_hash`. Three behavior changes landed in `run_eval` this round with zero new coverage.

**Remediation:** One `pytest.raises(ValueError)` case, plus an assertion that retrieval requested
`final_top_k` while recall sliced to `k` (the `_FakeRetriever` already records `top_k`).

### 6. `coverage_stats` pools models; `score_distribution` de-duplicates them. *(Low)*

[2026-07-21-r2.md:26](outputs/eval/2026-07-21-r2.md#L26) reports "All answered: n=74" — that is 37
items × 2 models pooled into one distribution ([metrics.py:266-292](src/lds_study/eval/metrics.py#L266-L292)),
whereas `score_distribution()` deliberately de-duplicates by `question_id`
([metrics.py:209-217](src/lds_study/eval/metrics.py#L209-L217)). Two adjacent sections of the same
report use different denominators for the same 50 questions. Also note `status=ok only: min=0.8` is
tautological — the gate is 0.8, so no `ok` answer can be below it; that line cannot inform whether
0.8 is the right threshold.

**Remediation:** Report coverage per model (it is model-dependent, unlike retrieval scores), and drop
or relabel the tautological `ok_min`.

### 7. `lp-004` now refuses a question whose gold verses are indexed. *(Low / Noted)*

`lp-004` ("Create a family home evening outline on prayer using James 1:5 and Enos 1:4") is the one
grounded item whose entire seed set fell below 0.05, so it returns `no_evidence` for both models.
Both gold chunks — `nt/james/1/5`, `bofm/enos/1/4` — are in the index and are gold ids for other
questions that retrieve fine.

This is not a regression in honesty (retrieval was already missing it: `recall N` at `min_score:
0.0`), and refusing beats answering ungrounded. But `no_evidence` is documented in
[README.md:75](README.md#L75) as "nothing retrieved above `retrieval.min_score`", which a user will
read as "not in the corpus" — and here it is. Worth one line in the report's notes rather than a code
change.

### 8. Manual 1–5 quality column still write-only. *(Low — carried from rounds 1 and 2)*

Third round unchanged: always blank, no merge path across re-runs. Three of the plan's four PR4
metrics are automated; this one has no workflow. Either wire it (read prior scores from the sidecar
by `(question_id, model)`) or drop the column and say manual scoring happens against a frozen report.

## Net assessment

**PR4 is done and safe to merge.** The plan's gate — a ≥2-generator comparison table committed under
`outputs/eval/`, with the thresholds it establishes written into `configs/rag.yaml` — is met with a
verified, self-consistent, harness-emitted artifact. Round 2's core complaint (numbers describing a
configuration the repo no longer had) is fully resolved, and the discipline added along the way
(`do not hand-edit` in the config, `(SUPERSEDED)` banner, provenance hashes, `--k` guard) is the
right kind of scar tissue.

The two findings worth fixing before PR5 consumes these floors are structural, not clerical:
`max()`-anchored baselines that exclude the alternative model (finding 1), and a missing
`coverage_fail_rate` floor that leaves the system's weakest metric ungated (finding 2). Both are
small changes to `suggested_baselines()` plus one config line. Finding 4 (dead file reference in
`models.yaml`) is a two-minute fix that should not be left in a merged commit.

Findings 3, 5, 6, 7, 8 are cleanup.

One observation across three rounds: the failure mode has moved from "wrong numbers" to "right
numbers, incomplete gate." That is real progress, and the remaining gap is the ordinary one — the
metric that got split in round 1 lost its floor and nobody re-added it.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **63 passed in 5.31s**; `ruff check src tests scripts` → **All checks passed!**
- Recomputed every aggregate in `2026-07-21-r2.md` from `2026-07-21-r2.json`. All match exactly:
  - `qwen2.5:14b` — citation 36/37 = 0.973 ✓, coverage fail 9/37 = 24.3% ✓, adversarial 11/12 = 91.7% ✓, non-adv statuses `{ok: 27, unsupported: 10, no_evidence: 1}`
  - `qwen3:14b` — citation 37/37 = 1.000 ✓, coverage fail 7/37 = 18.9% ✓, adversarial 9/12 = 75.0% ✓, non-adv statuses `{ok: 30, unsupported: 7, no_evidence: 1}`
  - `recall_shared = 0.78947…` ✓; sidecar `suggested_baselines` = `{'min_recall_at_k': 0.711, 'min_citation_validity': 0.9, 'min_adversarial_refusal': 0.825}` — **identical to `configs/rag.yaml`**, confirming no hand-editing this round
- Confirmed round-2's prediction: adversarial refusal rose from 33.3% to 91.7%/75.0% under `min_score: 0.05`, driven by 9/12 items reaching `no_evidence` deterministically
- Established the effective sample size behind `min_adversarial_refusal`: 9 of 12 refusals are retrieval-determined and identical across models; the entire 11-vs-9 gap is 3 model-dependent items generated at `temperature: 0.2` (finding 1)
- `.\.venv\Scripts\python.exe -m lds_study.cli eval --k 20 --retrieval-only` → `eval failed: --k (20) cannot exceed retrieval.final_top_k (8)…`, exit 1 (round-2 finding 5 fixed)
- `eval --help` → `--models` now documents "full shortlist in models.yaml"; `--k` documents the `final_top_k` constraint (round-2 finding 6 fixed)
- Grepped `2026-07-21` across `*.md`/`*.yaml`/`*.py`: [configs/models.yaml:5](configs/models.yaml#L5) is the only dangling reference to the renamed report (finding 4); `MODEL_CARD.md` correctly points at `-r2.md` and `-scores.md`
- Compared score distributions across runs: adversarial `n` 12 → 3 and `min` 0.0004 → 0.0502 between the `min_score: 0.0` calibration run and the `0.05` run, demonstrating the circularity in finding 3
- Read `2026-07-21-pre-minscore-superseded.md` header — `(SUPERSEDED)` in the title, "Do not use for PR5 floors" banner, historical errata retained and labelled. Correct handling of round-2 finding 4.
- Verified preflight offline-safety: [run.py:252-257](src/lds_study/eval/run.py#L252-L257) checks only models absent from injected `generators`; suite makes no network calls
