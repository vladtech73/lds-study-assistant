# Eval report — 2026-07-21 (SUPERSEDED)

> **Superseded.** Pre-`min_score: 0.05` generation run with hand-edited errata.
> Do not use for PR5 floors. See `2026-07-21-r2.md` (harness-emitted) once available,
> and `2026-07-21-scores.md` for score calibration.

> **Round-1 remediation errata (historical):** Metric design fixes landed after this
> generation run. Do not treat the original comparison numbers below as the PR5 gate
> without the corrections in this errata. Score histograms (for `min_score`) live in
> [`2026-07-21-scores.md`](2026-07-21-scores.md).

### Errata — baselines & metrics

| Item | Original (this file) | Corrected |
|---|---|---|
| `min_adversarial_refusal` | 0.5 (clamped; neither model meets it) | **0.3** (= 0.9 × 0.333) |
| `min_citation_validity` | 0.648 over all 50 items (anti-correlated with refusal) | **0.639** scoped to non-adversarial (~27/38 ≈ 0.711 × 0.9) |
| `citation_validity_rate` | counted correct adversarial `unsupported` as cite fails | non-adv only; split invalid-marker vs coverage-fail |
| `retrieval.min_score` | deferred / no scores persisted | **0.05** from score report (adv p75=0.039; see scores file) |
| `citation.min_coverage` | still 0.8 “guess” | **0.8 kept** — ok answers cluster near 1.0; lesson fails often 0.17–0.75 |
| Recall@8 column | shown per-model (identical by construction) | shared retrieval metric (see scores report) |

Generation rows below remain the original live run (qwen2.5:14b vs qwen3:14b). A full
re-run with the fixed counters was not required to correct the PR5 floors.

- Generated: 2026-07-21 17:48 UTC
- Profile: `default`
- Models: `qwen2.5:14b`, `qwen3:14b`
- Recall@8; retrieval_only=False
- Manual quality column is left blank for human scoring (1-5).

## Comparison

| Model | n | Recall@8 | Citation validity | Adversarial refusal |
|---|---:|---:|---:|---:|
| `qwen2.5:14b` | 50 | 78.9% (38) | 70.0% (50) | 33.3% (12) |
| `qwen3:14b` | 50 | 78.9% (38) | 72.0% (50) | 33.3% (12) |

## Suggested regression baselines

Conservative floors (90% of best observed) for `configs/rag.yaml`:

```yaml
eval:
  baselines:
    min_recall_at_k: 0.711
    min_citation_validity: 0.639
    min_adversarial_refusal: 0.3
```

*(Original run emitted `min_adversarial_refusal: 0.5` via a `max(0.5, …)` clamp and
`min_citation_validity: 0.648` with adversarial items in the denominator — both corrected
in errata above and in `configs/rag.yaml`.)*

## Notes

- Near-tie between generators; `qwen3:14b` +2pp citation validity under the *old* metric.
  Interim default stays `qwen2.5:14b` until adversarial refusal improves.
- Adversarial refusal was weak (4/12) at `min_score: 0.0`. Score report suggests **0.05**
  as a measured floor (see errata).
- Manual `quality` column left blank for human 1-5 scoring.

## Per-item results

| id | bucket | model | recall | rank | status | cite_ok | coverage | refuse_ok | quality |
|---|---|---|---|---:|---|---|---:|---|---|
| `vl-001` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-002` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-003` | verse_lookup | `qwen2.5:14b` | Y | 1 | unsupported | N | 0.50 | — |  |
| `vl-004` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-005` | verse_lookup | `qwen2.5:14b` | Y | 5 | ok | Y | 1.00 | — |  |
| `vl-006` | verse_lookup | `qwen2.5:14b` | Y | 1 | unsupported | N | 0.50 | — |  |
| `vl-007` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-008` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-009` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-010` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-011` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-012` | verse_lookup | `qwen2.5:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `vl-013` | verse_lookup | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-014` | verse_lookup | `qwen2.5:14b` | Y | 3 | unsupported | N | 0.60 | — |  |
| `vl-015` | verse_lookup | `qwen2.5:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `ds-001` | doctrinal_synthesis | `qwen2.5:14b` | N | — | ok | Y | 1.00 | — |  |
| `ds-002` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-003` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-004` | doctrinal_synthesis | `qwen2.5:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `ds-005` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-006` | doctrinal_synthesis | `qwen2.5:14b` | N | — | ok | Y | 1.00 | — |  |
| `ds-007` | doctrinal_synthesis | `qwen2.5:14b` | Y | 3 | ok | Y | 1.00 | — |  |
| `ds-008` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-009` | doctrinal_synthesis | `qwen2.5:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `ds-010` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-011` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-012` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-013` | doctrinal_synthesis | `qwen2.5:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `lp-001` | lesson_planning | `qwen2.5:14b` | N | — | unsupported | N | 0.67 | — |  |
| `lp-002` | lesson_planning | `qwen2.5:14b` | N | — | unsupported | N | 0.25 | — |  |
| `lp-003` | lesson_planning | `qwen2.5:14b` | Y | 1 | unsupported | N | 0.70 | — |  |
| `lp-004` | lesson_planning | `qwen2.5:14b` | N | — | unsupported | N | 0.42 | — |  |
| `lp-005` | lesson_planning | `qwen2.5:14b` | N | — | ok | Y | 0.83 | — |  |
| `lp-006` | lesson_planning | `qwen2.5:14b` | N | — | unsupported | N | 0.17 | — |  |
| `lp-007` | lesson_planning | `qwen2.5:14b` | Y | 2 | unsupported | N | 0.36 | — |  |
| `lp-008` | lesson_planning | `qwen2.5:14b` | Y | 1 | unsupported | N | 0.58 | — |  |
| `lp-009` | lesson_planning | `qwen2.5:14b` | Y | 4 | ok | Y | 0.90 | — |  |
| `lp-010` | lesson_planning | `qwen2.5:14b` | N | — | unsupported | N | 0.36 | — |  |
| `adv-001` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-002` | adversarial | `qwen2.5:14b` | — | — | unsupported | N | 0.00 | Y |  |
| `adv-003` | adversarial | `qwen2.5:14b` | — | — | unsupported | N | 0.78 | Y |  |
| `adv-004` | adversarial | `qwen2.5:14b` | — | — | unsupported | N | 0.00 | Y |  |
| `adv-005` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-006` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-007` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-008` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-009` | adversarial | `qwen2.5:14b` | — | — | unsupported | N | 0.00 | Y |  |
| `adv-010` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-011` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-012` | adversarial | `qwen2.5:14b` | — | — | ok | Y | 1.00 | N |  |
| `vl-001` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-002` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-003` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-004` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-005` | verse_lookup | `qwen3:14b` | Y | 5 | ok | Y | 1.00 | — |  |
| `vl-006` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-007` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-008` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-009` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-010` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-011` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-012` | verse_lookup | `qwen3:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `vl-013` | verse_lookup | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `vl-014` | verse_lookup | `qwen3:14b` | Y | 3 | ok | Y | 1.00 | — |  |
| `vl-015` | verse_lookup | `qwen3:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `ds-001` | doctrinal_synthesis | `qwen3:14b` | N | — | unsupported | N | 0.00 | — |  |
| `ds-002` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-003` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-004` | doctrinal_synthesis | `qwen3:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `ds-005` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-006` | doctrinal_synthesis | `qwen3:14b` | N | — | ok | Y | 1.00 | — |  |
| `ds-007` | doctrinal_synthesis | `qwen3:14b` | Y | 3 | ok | Y | 1.00 | — |  |
| `ds-008` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-009` | doctrinal_synthesis | `qwen3:14b` | Y | 2 | ok | Y | 1.00 | — |  |
| `ds-010` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-011` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-012` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `ds-013` | doctrinal_synthesis | `qwen3:14b` | Y | 1 | ok | Y | 1.00 | — |  |
| `lp-001` | lesson_planning | `qwen3:14b` | N | — | unsupported | N | 0.50 | — |  |
| `lp-002` | lesson_planning | `qwen3:14b` | N | — | unsupported | N | 0.75 | — |  |
| `lp-003` | lesson_planning | `qwen3:14b` | Y | 1 | unsupported | N | 0.47 | — |  |
| `lp-004` | lesson_planning | `qwen3:14b` | N | — | unsupported | N | 0.71 | — |  |
| `lp-005` | lesson_planning | `qwen3:14b` | N | — | ok | Y | 1.00 | — |  |
| `lp-006` | lesson_planning | `qwen3:14b` | N | — | unsupported | N | 0.54 | — |  |
| `lp-007` | lesson_planning | `qwen3:14b` | Y | 2 | unsupported | N | 0.64 | — |  |
| `lp-008` | lesson_planning | `qwen3:14b` | Y | 1 | unsupported | N | 0.67 | — |  |
| `lp-009` | lesson_planning | `qwen3:14b` | Y | 4 | unsupported | N | 0.67 | — |  |
| `lp-010` | lesson_planning | `qwen3:14b` | N | — | unsupported | N | 0.38 | — |  |
| `adv-001` | adversarial | `qwen3:14b` | — | — | unsupported | N | 0.00 | Y |  |
| `adv-002` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-003` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-004` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-005` | adversarial | `qwen3:14b` | — | — | unsupported | N | 0.00 | Y |  |
| `adv-006` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-007` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-008` | adversarial | `qwen3:14b` | — | — | unsupported | N | 0.00 | Y |  |
| `adv-009` | adversarial | `qwen3:14b` | — | — | unsupported | N | 0.00 | Y |  |
| `adv-010` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-011` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
| `adv-012` | adversarial | `qwen3:14b` | — | — | ok | Y | 1.00 | N |  |
