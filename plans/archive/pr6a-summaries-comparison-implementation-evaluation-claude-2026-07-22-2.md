# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 2 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows [round 1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md).*

## Verdict: Round 1's findings are genuinely fixed — but one remediation was applied at the wrong point and now destroys eval runs.

All ten Round 1 findings were addressed, several better than I asked for: the copyright boundary is now a fail-closed key projection rather than a field deletion, the reference sort uses `generated_at` with an mtime fallback, comparison is keyed by model name with `models` added to the guard list, and the untracked-skip test now builds a real git repo. 89 tests and `ruff` pass.

But the fix for Round 1 Finding 4 — hard-fail on an unresolvable explicit `--compare` — was placed *after* the eval completes and inside the summary-cleanup `try`. A mistyped `--compare` now runs the full eval and then writes **nothing**: no markdown report, no JSON sidecar, no summary, exit 1. On a real GPU run that is an hour of irreproducible measurement discarded by an argument typo. That is strictly worse than the silent no-op it replaced, and it is a merge blocker. One further defect: absolute machine-local paths, including the OS username, are now written into the committed markdown report — the exact portability wart the plan names and forbids repeating.

## Round 1 finding disposition

| # (R1) | Severity | Status | Evidence |
|---|---|---|---|
| 1 | Critical | **Fixed** | `summary_safe_aggregate()` projects through `SUMMARY_AGGREGATE_KEYS`, which omits `first_error` ([report.py:44-95](../../src/lds_study/eval/report.py#L44-L95)); leak repro now prints `SECRET IN SUMMARY: False`; test rewritten to drive the generation path ([test_pr6_iterate.py:190-248](../../tests/test_pr6_iterate.py#L190-L248)) |
| 2 | High | **Fixed** | `_summary_recency_key()` sorts on parsed `generated_at`, mtime fallback ([compare.py:371-396](../../src/lds_study/eval/compare.py#L371-L396)); `compare_reason` now carries the timestamp |
| 3 | High | **Fixed** | `models` added to `COMPARABILITY_FIELDS` and order-normalized; `_aggregates_by_model()` keys by name; per-model delta rows ([compare.py:91-100](../../src/lds_study/eval/compare.py#L91-L100), [compare.py:235-252](../../src/lds_study/eval/compare.py#L235-L252)) |
| 4 | Low | **Fixed, but wrongly placed** | Raises `ValueError` ([compare.py:467](../../src/lds_study/eval/compare.py#L467)) — see Finding 1 below |
| 5 | Low | **Fixed** | Test now `git init`s, commits two summaries, leaves one untracked with a 2099 timestamp, and asserts the untracked one loses ([test_pr6_iterate.py:353-406](../../tests/test_pr6_iterate.py#L353-L406)) |
| 6 | Low | **Fixed** | Dedup probes `md or json or summary` ([run.py:383-390](../../src/lds_study/eval/run.py#L383-L390)) |
| 7 | Low | **Fixed** | `render_no_comparison_section()`, always-emitted `## Keep-or-revert` with a "Gate not run" branch, `compare=` in the header ([report.py:355-381](../../src/lds_study/eval/report.py#L355-L381)) |
| 8 | Trivial | **Fixed** | `except Exception:` unlinks the orphan summary ([run.py:487-490](../../src/lds_study/eval/run.py#L487-L490)) — partially, see Finding 4 |
| 9 | Trivial | **Fixed** | Printed message now lists `outputs/eval/*.summary.json (and nested)`; verified in output |
| 10 | Trivial | **Fixed in `run.py`, reintroduced in `compare.py`** | See Finding 6 |
| 11–13 | Noted | Unchanged, correctly | Still no code change needed; 13 still true (`git ls-files` → 0 rows) |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema v1, aggregates-only** | Complete | [report.py:97-158](../../src/lds_study/eval/report.py#L97-L158); all plan fields present |
| **Step 1 — copyright boundary** | Complete | Fail-closed projection; `status_counts` values confirmed bounded (`ok` / `unsupported` / `no_evidence` / `error` / `unknown`, [ask.py:111-191](../../src/lds_study/rag/ask.py#L111-L191)) |
| **Step 1 — persisted gate result** | Complete | Summary + markdown; "Gate not run" branch distinguishes not-run from clean |
| **Step 1 — gitignore + allowlist** | Complete | `git status -uall` shows summary as `??`, full sidecar ignored; check script exits 0/1 correctly |
| **Step 4 — `--compare <path\|auto\|none>`** | **Partial — unsafe failure mode** | Finding 1 |
| **Step 4 — git-aware `auto`, chronological** | Complete | Finding 2 (R1) fixed and tested |
| **Step 4 — `diff_summaries()` per-model** | Complete | Finding 3 (R1) fixed and tested |
| **Step 4 — tolerance, tol=0 for recall/retrieval-only** | Complete | [compare.py:149-158](../../src/lds_study/eval/compare.py#L149-L158) |
| **Step 4 — comparability guard** | Complete | 8 fields, one test case each |
| **Step 4 — markdown + console rendering** | **Partial** | Renders, but embeds absolute paths — Finding 2 |
| **Step 4 — `--check-baselines` unchanged** | Complete | [cli.py:287-297](../../src/lds_study/cli.py#L287-L297) untouched |
| **Step 10 — tests** | **Partial** | 89 pass; generation-path comparison never exercised end to end — Finding 3 |
| Steps 2, 3, 5–9 | Deferred-as-planned | Correctly absent |

## Findings (ranked)

### 1. An unresolvable `--compare` reference discards the entire eval run. *(Critical — regression)*

`resolve_compare_reference()` now raises on an explicit reference that does not resolve ([compare.py:466-467](../../src/lds_study/eval/compare.py#L466-L467)). That was the right call. The problem is where it fires: it is invoked at [run.py:407-413](../../src/lds_study/eval/run.py#L407-L413), *after* the whole eval has run, and inside the `try` whose handler unlinks the summary and re-raises ([run.py:487-490](../../src/lds_study/eval/run.py#L487-L490)). `write_markdown_report` and `write_json_sidecar` sit below the raise, so they never execute.

Reproduced — a full retrieval-only run with `compare="2026-07-21-r2"` (a stem with no summary yet, which is the *expected* state of this repo today):

```
RAISED: compare path not found: 2026-07-21-r2
files on disk: []
```

Nothing survives. On the plan's own local verification path (`lds eval --profile default --no-local` against a real index and Ollama), that is a long GPU job whose measurements are irrecoverable, thrown away by a string typo. The Round 1 behavior — a silent no-op — was wrong, but it at least preserved the report. This is a strict downgrade in blast radius.

Two things compound it. First, `--compare` is user input available *before* any work starts, so late validation is gratuitous. Second, the failure is asymmetric in a way nobody would predict: a reference that is *missing* nukes the run, while a reference that exists but is *corrupt JSON* degrades softly to `compare failed: …` ([run.py:425-429](../../src/lds_study/eval/run.py#L425-L429)) and writes a complete report.

**Remediation:** Resolve and validate the explicit `--compare` path at the top of `run_eval()`, before retrieval begins — fail fast, having spent nothing. Keep `auto` resolution where it is (it depends on `summary_path`). If late validation must stay, at minimum move the raise below the report writers so the measurement is never lost. Add a test asserting that a bad `--compare` either fails before any retrieval, or leaves `md_path` and `json_path` on disk.

### 2. Absolute machine-local paths — including the OS username — are written into the committed report. *(High)*

Three lines in every generated report carry fully-resolved local paths:

```
'- compare=C:\\Users\\vladtech\\AppData\\Local\\Temp\\tmpx0b6m222\\outputs\\eval\\a.summary.json'
'- Previous: `C:/Users/vladtech/AppData/Local/Temp/tmpx0b6m222/outputs/eval/a.summary.json`'
'- Current: `C:/Users/vladtech/AppData/Local/Temp/tmpx0b6m222/outputs/eval/b.summary.json`'
```

Sources: `compare_mode` is echoed verbatim ([report.py:276](../../src/lds_study/eval/report.py#L276)), and `previous_path` / `current_path` are `.as_posix()` of resolved absolutes ([compare.py:279-282](../../src/lds_study/eval/compare.py#L279-L282)). Both are absolute on the `auto` path too — `resolve_compare_reference` returns `chosen.resolve()` and `summary_path` comes from `settings.resolve()`.

`outputs/eval/*.md` is committed. The plan is explicit about this pattern in Step 2: *"Paths must be stored repo-relative; the existing absolute `chunks_path` in `index_manifest.json` is already a portability wart, do not repeat it."* This repeats it, in a more visible artifact, and adds a username to a public file.

It also collides with PR6d: `check_eval_reports.py` must diff committed reports field-by-field, and these three lines differ per machine and per temp directory — every cross-machine regeneration produces a spurious diff on lines the guard is supposed to treat as immutable.

**Remediation:** Render all three relative to `settings.effective_root` (`Path.relative_to` with an absolute fallback for out-of-tree references), and normalize `compare_mode` to `auto` / `none` / the relative stem rather than echoing raw user input.

### 3. Nothing guards the coupling between the new key projection and the metrics `diff_summaries` reads. *(Medium)*

`summary_safe_aggregate()` is now a fail-closed allowlist projection — the right design, and it is what closed Round 1 Finding 1. But it created a new silent-degradation path: `diff_summaries` reads five aggregate keys, and if any one were dropped from `SUMMARY_AGGREGATE_KEYS`, `_metric_from_agg` returns `None`, the delta becomes `n/a`, and every comparison quietly stops reporting that metric. No exception, no warning, `comparable=True`.

The intersection is correct today:

```
needed by diff_summaries: ['adversarial_refusal_rate', 'citation_validity_rate',
                           'coverage_fail_rate', 'invalid_marker_rate', 'recall_at_k']
missing from projection : []
```

Nothing asserts it. And no test would catch the drift, because no test compares two summaries produced by the generation path: `test_run_eval_compare_embeds_section` ([test_pr6_iterate.py:447-474](../../tests/test_pr6_iterate.py#L447-L474)) is `retrieval_only=True`, which skips per-model metrics entirely ([compare.py:235](../../src/lds_study/eval/compare.py#L235)); `test_run_eval_scripted_keep_verdicts_in_summary` runs generation but passes `compare="none"`. The only tests that exercise generation deltas use hand-built fixtures, not real summaries.

This is the same class of gap as Round 1 Finding 1 — a guard test that passes on a path where the guarded thing cannot happen.

**Remediation:** Add a static assertion that the keys in `_PER_MODEL_METRIC_SPECS` plus `recall_at_k` are a subset of `SUMMARY_AGGREGATE_KEYS`, and extend `test_run_eval_compare_embeds_section` (or add a sibling) that runs two `ScriptedGenerator` evals and asserts a non-`n/a` `citation_validity` delta round-trips through two real `*.summary.json` files.

### 4. Cleanup on failure is asymmetric. *(Low)*

The `except Exception:` handler unlinks only the summary ([run.py:487-490](../../src/lds_study/eval/run.py#L487-L490)), but `write_json_sidecar` runs *after* `write_markdown_report` inside the same block. If the sidecar write fails — disk full, permissions — the summary is removed and the markdown report is left behind, orphaned in the opposite direction. Since both are now paired artifacts that PR6d's integrity checker will expect to co-exist, "report without summary" is the worse of the two orphan states.

**Remediation:** Have the handler remove any of the three files this invocation created, or write all three only after all payloads are computed.

### 5. Comparison test fixtures no longer match the real committed schema. *(Low)*

`_base_summary()` and the diff tests build aggregates with `_agg(...).to_dict()` ([test_pr6_iterate.py:276](../../tests/test_pr6_iterate.py#L276), and throughout), which includes `first_error` — a key that `summary_safe_aggregate()` now strips. So every `diff_summaries` test operates on payloads that would fail the `SUMMARY_AGGREGATE_KEYS` assertion the other tests apply. Harmless today because `diff_summaries` reads only named keys, but it means the compare suite is validated against a shape the system no longer produces, which is how Finding 3's gap stays invisible.

**Remediation:** Build fixtures with `summary_safe_aggregate()` so the compare tests consume exactly what `write_summary_json` emits.

### 6. `json.JSONDecodeError` in `except` tuples — fixed in `run.py`, reintroduced in `compare.py`. *(Trivial)*

Round 1 Finding 10 was resolved at [run.py:427](../../src/lds_study/eval/run.py#L427) (`except (OSError, ValueError)`), but the same redundancy appears twice in the new code at [compare.py:394](../../src/lds_study/eval/compare.py#L394) and [compare.py:404](../../src/lds_study/eval/compare.py#L404). `JSONDecodeError` subclasses `ValueError`.

### 7. The chosen reference is read and JSON-parsed twice. *(Trivial)*

`_summary_recency_key()` parses every tracked summary to sort ([compare.py:386-396](../../src/lds_study/eval/compare.py#L386-L396)), then `_format_generated_at()` re-reads and re-parses the winner ([compare.py:399-406](../../src/lds_study/eval/compare.py#L399-L406)). Irrelevant at current scale; fold the timestamp into the sort key if it is ever cheap to do so.

### 8. Output de-duplication is now stricter than before for pre-existing runs. *(Noted — no action)*

Round 1 Finding 6's fix means a leftover `.json` or `.summary.json` with no matching `.md` now bumps the stem to `-2`, where previously the `.md` alone decided. This is the correct behavior and what I asked for, but it is a small behavior change to existing `lds eval` beyond the plan's "behaves exactly as before" invariant. Worth one line in the PR description.

### 9. `SUMMARY_TOP_LEVEL_KEYS` is documentation, not enforcement. *(Noted — no action)*

Unlike `SUMMARY_AGGREGATE_KEYS`, which is applied as a projection, the top-level frozenset is only asserted in tests; `build_summary_payload` returns a dict literal. The asymmetry is defensible — `AggregateMetrics` is the class that grows fields (it already grew `first_error`), so fail-closed belongs there, and the top-level dict is explicit enough to review by eye. Flagging so the difference is deliberate rather than accidental.

### 10. Carried from Round 1: trend regression does not affect exit code; `auto` has no reference yet. *(Noted — no action)*

Both unchanged and both still correct for PR6a. `git ls-files "outputs/eval/*.summary.json"` still returns 0 rows, so `--compare auto` resolves to "no reference" on merge and on any fresh clone until a first summary is committed — now with an explicit `- No comparison: …` line in the report, which is an improvement over Round 1's silence.

## Net assessment

Finding 1 blocks merge. It is a small fix — hoist the explicit-path resolution above the retrieval loop — but shipping it as-is means the first person who mistypes `--compare` on a real run loses the run, and the plan's own verification block (`--compare auto` before any summary is committed, `--stem verify-b`) walks straight toward that edge. Finding 2 should go in the same pass: it is cheap, it puts a username into a committed file, and leaving it for PR6d means `check_eval_reports.py` inherits three lines it cannot treat as stable.

Finding 3 is the one I would not defer even though it is only Medium. Round 1's core lesson was that a guard test passing on a path where the hazard cannot occur is worse than no test, and the remediation for Round 1 Finding 1 introduced a fresh instance of exactly that shape. A static subset assertion is two lines.

Findings 4–7 are cleanup and can ride along or wait. 8–10 need prose, not code.

The direction of travel is good. The fixes were not minimal patches — the projection allowlist, the `generated_at` sort with the deliberately-adversarial 2099-timestamped untracked fixture, and the model-order-normalization test all go beyond what Round 1 asked for and close the underlying class of bug rather than the instance. Scope stayed disciplined: still no new commands, still no config writes, Steps 2/3/5–9 still absent.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **89 passed in 7.60s** (was 86 in round 1)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- **Finding 1 repro** (scratchpad): `run_eval(..., compare="2026-07-21-r2")` after a completed retrieval-only eval → `RAISED: compare path not found: 2026-07-21-r2`; `files on disk: []` — no `.md`, no `.json`, no `.summary.json`
- **Finding 2 repro** (scratchpad): two chained runs, grep of the second report → `- compare=C:\Users\vladtech\...`, `- Previous: \`C:/Users/vladtech/...\``, `- Current: \`C:/Users/vladtech/...\``
- **Finding 3 check**: `_PER_MODEL_METRIC_SPECS` keys + `recall_at_k` vs `SUMMARY_AGGREGATE_KEYS` → `missing from projection: []` (correct, unasserted)
- **R1 Finding 1 regression check**: round-1 leak repro (generation path, `include_local=True`, generator raising with restricted text) → `SECRET IN SUMMARY: False`; `KeyError: 'first_error'` when probing the old field
- `python scripts/check_staged_data.py --paths outputs/eval/x.json` → error text now contains `outputs/eval/*.summary.json (and nested)`
- Grep gates: `SUMMARY_TOP_LEVEL_KEYS` / `SUMMARY_AGGREGATE_KEYS` / `summary_safe_aggregate` usage outside tests → projection enforced at [report.py:135](../../src/lds_study/eval/report.py#L135), top-level set unreferenced in prod
- Spot-checks: `ask.py` status values bounded (no free text in `status_counts`); `report_paths` 3-tuple call sites both updated; new markdown sections still precede `## Per-item results`
- Reviewed the full diff of all six modified files plus `compare.py` and `tests/test_pr6_iterate.py` in their entirety

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index.*
