# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 1 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`).*

## Verdict: Structurally complete, but not safe to merge — the copyright boundary leaks.

Both in-scope workstreams (Step 1 summaries + persisted verdicts, Step 4 `--compare`) landed with the shape the plan asked for, the gitignore/allowlist plumbing works, and all 86 tests plus `ruff` pass. But the plan's own highest-severity risk is live: `AggregateMetrics.first_error` is an unbounded free-text field that flows verbatim into the committable `*.summary.json`, and I reproduced restricted golden-local question text landing in it. The copyright test that is supposed to guard this passes only because it runs `retrieval_only=True`, a path where the field is never populated from generation — textbook false confidence. Two further defects make `--compare auto` pick the wrong reference (lexicographic sort, not chronological) and silently diff two *different models* against each other.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — `write_summary_json()`, schema v1** | Complete | [report.py:40-134](../../src/lds_study/eval/report.py#L40-L134); all plan-named fields present incl. `buckets`, `limit`, `config_fingerprint` placeholder |
| **Step 1 — persist gate result** | Complete | `baselines_checked` / `baseline_verdicts` in summary ([report.py:110-112](../../src/lds_study/eval/report.py#L110-L112)) and a `## Keep-or-revert` markdown section ([report.py:298-315](../../src/lds_study/eval/report.py#L298-L315)) |
| **Step 1 — no `items` / no free text** | **Partial — fails on free text** | `items` correctly absent; `first_error` is free text and leaks (Finding 1) |
| **Step 1 — gitignore allowlist** | Complete | `.gitignore:38`; verified: `outputs/eval/X.summary.json` shows as `??`, `outputs/eval/X.json` stays ignored |
| **Step 1 — `check_staged_data.py`** | Complete | [check_staged_data.py:58-60](../../scripts/check_staged_data.py#L58-L60); summary exits 0, full sidecar exits 1 (verified) |
| **Step 1 — wire into `run_eval`, `summary_path` on `EvalResult`** | Complete | [run.py:75](../../src/lds_study/eval/run.py#L75), [run.py:394-414](../../src/lds_study/eval/run.py#L394-L414) |
| **Step 4 — `--compare <path\|auto\|none>`** | Complete | [cli.py:234-242](../../src/lds_study/cli.py#L234-L242), default `auto` |
| **Step 4 — git-aware `auto` resolution** | **Partial** | Order (explicit → `reference_report` → tracked) is right ([compare.py:332-379](../../src/lds_study/eval/compare.py#L332-L379)); "newest" is wrong (Finding 2) |
| **Step 4 — `diff_summaries()` + deltas** | **Partial** | [compare.py:144-206](../../src/lds_study/eval/compare.py#L144-L206); model-blind (Finding 3) |
| **Step 4 — noise tolerance, tol=0 for recall/retrieval-only** | Complete | [compare.py:132-141](../../src/lds_study/eval/compare.py#L132-L141); `eval.trend_tolerance: 0.02` in `configs/rag.yaml` |
| **Step 4 — comparability guard on 7 fields** | Complete | [compare.py:13-21](../../src/lds_study/eval/compare.py#L13-L21); one test case per field |
| **Step 4 — markdown section + console table** | Complete | [compare.py:209-272](../../src/lds_study/eval/compare.py#L209-L272), [cli.py:274-278](../../src/lds_study/cli.py#L274-L278) |
| **Step 4 — `--check-baselines` semantics unchanged** | Complete | [cli.py:287-297](../../src/lds_study/cli.py#L287-L297) untouched |
| **Step 10 — tests (PR6a subset)** | **Partial** | 11 tests, all passing; the copyright test and the untracked-skip test are both vacuous on the path they claim to cover (Findings 1, 5) |
| Steps 2, 3, 5–9 | Deferred-as-planned | Correctly absent from this diff |

## Findings (ranked)

### 1. `first_error` carries arbitrary free text — including restricted question text — into the committed summary. *(Critical)*

`AggregateMetrics.to_dict()` emits `first_error` ([metrics.py:99](../../src/lds_study/eval/metrics.py#L99)), which is `str(exc)` from any per-item failure ([run.py:200-201](../../src/lds_study/eval/run.py#L200-L201)). `build_summary_payload` serializes every aggregate wholesale (`"aggregates": [a.to_dict() for a in aggs]`, [report.py:106](../../src/lds_study/eval/report.py#L106)), so that string goes straight into the file the plan just added to the git allowlist.

Plan Step 1 is explicit: *"Add an explicit unit test asserting no per-item payload **and no free text fields**."* The `items` half landed; the free-text half did not. Provider errors routinely echo the request — an Ollama 400, a validation error, a template failure — and `run_ask()` receives the question text.

Reproduced (scratchpad script, generator raising `RuntimeError(f"upstream 400: prompt was {SECRET}")` with `include_local=True`):

```
SECRET IN SUMMARY: True
first_error: upstream 400: prompt was RESTRICTED_LOCAL_QUESTION_TEXT_NEVER_COMMIT
```

The guard test [test_pr6_iterate.py:177-217](../../tests/test_pr6_iterate.py#L177-L217) misses this because it passes `retrieval_only=True` — generation never runs, `error` is never set, and the assertion `secret not in raw` is trivially satisfied. My first two repro attempts hit the same wall for a different reason (missing prompts dir, wrong generator method), each time producing a green `SECRET IN SUMMARY: False` from a code path that never reached the generator. That is precisely the shape of false confidence this test was meant to prevent.

Compounding it: `check_staged_data.py` allowlists by filename only. Nothing inspects summary *content* at stage time, so once the file is allowlisted the schema is the sole boundary.

**Remediation:** Drop `first_error` from the summary payload (keep `error_n` and `status_counts`, which are counts), or replace it with a scrubbed classifier (exception type name only). Then rewrite the copyright test to run the generation path — a generator that raises with the secret in its message — and assert the secret is absent. Consider an allowlist-of-keys assertion over the serialized payload so any future field addition fails the test rather than silently widening the boundary.

### 2. `--compare auto` picks the lexicographically-largest filename, not the newest run. *(High)*

[compare.py:377](../../src/lds_study/eval/compare.py#L377):

```python
tracked.sort(key=lambda p: (p.name, p.stat().st_mtime), reverse=True)
```

The primary sort key is the filename, so `st_mtime` is a dead tiebreaker and "newest" is really "last alphabetically". Verified:

```
sorted(['2026-07-22.summary.json','nightly-2026-01-01.summary.json',
        '2026-07-21-r2.summary.json','verify-b.summary.json'], reverse=True)[0]
→ 'verify-b.summary.json'
```

This holds only while every committed stem is an ISO date. The plan itself breaks that assumption in two places: Step 8's nightly script uses `--stem nightly-{date}`, and the plan's own verification block commits `verify-a` / `verify-b` / `verify-promote` stems. The moment one non-date stem is committed it becomes the permanent auto-reference. `generated_at` is already in the payload and unused — the correct key was available.

Silent wrong-reference selection is exactly the failure mode the git-awareness requirement existed to prevent; it just moved from "untracked file" to "wrong tracked file."

**Remediation:** Sort by the summary's `generated_at` (parsed, with mtime as fallback for unparseable/legacy files), and print the chosen reference's timestamp in `compare_reason` so a wrong pick is visible in the console line.

### 3. Comparison is model-blind: `models` is not a comparability field, and deltas read `aggregates[0]`. *(High)*

`COMPARABILITY_FIELDS` ([compare.py:13-21](../../src/lds_study/eval/compare.py#L13-L21)) guards `golden_hash`, `k`, `profile`, `include_local`, `retrieval_only`, `buckets`, `limit` — not `models`. All generation metrics are then pulled from `_primary_aggregate()`, which is unconditionally `aggregates[0]` ([compare.py:86-91](../../src/lds_study/eval/compare.py#L86-L91)), and `aggregates` is built in `model_list` order — i.e. the order of the `--models` CSV ([run.py:353](../../src/lds_study/eval/run.py#L353)).

Two consequences, both silent:

- `lds eval --models qwen` compared against a summary from `--models llama` reports a "trend" that is actually a model swap. `comparable=True`, no warning.
- `--models a,b` vs `--models b,a` — same models, same run shape — compares `a`'s citation validity against `b`'s and calls it a delta.

Recall is unaffected (`recall_shared` is overlaid onto every aggregate, [run.py:355-358](../../src/lds_study/eval/run.py#L355-L358)), which makes it worse: recall looks stable while the generation row silently changes meaning.

The plan's guard list omitted `models`, so part of this is inherited. The `aggregates[0]` positional read is an implementation choice, and it is the part that misfires even when the model *set* is identical.

**Remediation:** Add `models` (order-normalized, like `buckets`) to `COMPARABILITY_FIELDS`, and index aggregates by `model` name rather than position. Ideally emit one delta row per model rather than collapsing to the first.

### 4. A mistyped explicit `--compare <path>` degrades to no comparison, exit 0. *(Low)*

[compare.py:351-357](../../src/lds_study/eval/compare.py#L351-L357) returns `(None, "compare path not found: {mode}")`, and [run.py:424](../../src/lds_study/eval/run.py#L424) then skips comparison entirely. The user gets one console line among ~10 and a report with no `## Comparison vs previous` section. The plan's "report *no reference* and continue" was written for the `auto` path, where no reference is a legitimate state; an explicitly-named reference that does not resolve is a user error, and in a scripted `lds eval --compare $REF` it fails open.

**Remediation:** Raise `ValueError` for an unresolvable *explicit* `--compare` path (`run_eval` already surfaces `ValueError` as `eval failed:` + exit 1 at [cli.py:265-267](../../src/lds_study/cli.py#L265-L267)). Keep the soft path for `auto`.

### 5. The untracked-skip test is vacuous. *(Low)*

[test_pr6_iterate.py:307-326](../../tests/test_pr6_iterate.py#L307-L326) writes an untracked summary under `tmp_path` and asserts `resolve_compare_reference` returns `None`. But `tmp_path` is not inside a git repo, so `git ls-files` exits 128 and `_git_tracked_summaries` returns `[]` at [compare.py:289-290](../../src/lds_study/eval/compare.py#L289-L290):

```
$ cd C:/Users/vladtech/AppData/Local/Temp && git ls-files "outputs/eval/*.summary.json"
fatal: not a git repository (or any of the parent directories): .git
exit=128
```

The assertion would still pass if the tracked-file filtering were deleted outright. The plan's verification asked for the discriminating form: *"create an untracked `outputs/eval/zz-local.summary.json` and confirm it is skipped"* — i.e. skipped **while a tracked one is chosen**.

**Remediation:** `git init` a temp repo in the fixture, commit one summary, drop a second untracked alongside it, and assert the tracked one is returned. That test would also have caught Finding 2.

### 6. Output de-duplication keys only on the markdown path. *(Low)*

[run.py:382-390](../../src/lds_study/eval/run.py#L382-L390) probes `md_c.exists()` only. A `*.summary.json` whose `.md` was deleted or never existed is overwritten without warning — and PR6d's plan (Step 7 bootstrap) creates exactly that artifact class, a backfilled summary produced by a script rather than a run. Since summaries are now *committed*, silent overwrite of one is a git-visible surprise rather than a local one.

**Remediation:** Extend the collision probe to `md_c.exists() or sum_c.exists() or json_c.exists()`.

### 7. The committed report records nothing when no reference resolved. *(Low)*

`comparison_section` stays `None` whenever `ref_path is None` ([run.py:420-424](../../src/lds_study/eval/run.py#L420-L424)), so the markdown is silent. `compare_reason` — the "print which one was chosen and why" the plan asked for — exists only on the console and on `EvalResult`, both ephemeral. A committed report therefore cannot answer "was this compared, and against what?", which is the same durability argument the plan used to justify persisting `baseline_verdicts` in the first place.

Same gap on the `## Keep-or-revert` section: it is emitted only when `baselines_checked` is truthy, so "gate not run" and "gate ran clean" are indistinguishable in the artifact.

**Remediation:** Always emit a `## Comparison vs previous` stub carrying `compare_reason` (e.g. "no reference (no tracked `*.summary.json`)"), and add the `compare` mode to the report header block. Note this affects the table layout PR6d's `check_eval_reports.py` will parse — better to settle it now.

### 8. The summary is written before the markdown, with no cleanup on failure. *(Trivial)*

[run.py:395](../../src/lds_study/eval/run.py#L395) writes the summary, then compare, then `write_markdown_report`. If any later step raises, an orphan `*.summary.json` — a git-visible file — is left behind with no corresponding report. The ordering is deliberate and justified by the comment, so this is about cleanup, not sequencing.

**Remediation:** Wrap the post-summary block so a failure unlinks the summary, or write it last from a payload computed earlier.

### 9. `check_staged_data.py`'s user-facing error message was not updated. *(Trivial)*

The module docstring gained the `*.summary.json` line ([check_staged_data.py:9](../../scripts/check_staged_data.py#L9)), but the message a developer actually sees on rejection still says `outputs/eval/*.md (and nested)` ([check_staged_data.py:160-164](../../scripts/check_staged_data.py#L160-L164)). Observed in the run above.

**Remediation:** Add `outputs/eval/*.summary.json` to the printed list, or derive the message from `ALLOWLIST_PATTERNS`.

### 10. Redundant exception clause. *(Trivial)*

[run.py:437](../../src/lds_study/eval/run.py#L437): `except (OSError, ValueError, json.JSONDecodeError)` — `JSONDecodeError` subclasses `ValueError`.

### 11. `lds eval` with no new flags does not behave exactly as before. *(Noted — no action)*

The plan's Verification section lists as an invariant: *"`lds eval` without new flags behaves exactly as before (report path, exit codes, console output unchanged)."* With `--compare` defaulting to `auto` (which Step 4 mandates), an unflagged run now writes a third file, shells out to `git ls-files`, prints two extra console lines, and may add a markdown section. Exit codes and the report path are genuinely unchanged. This is the plan contradicting itself, resolved correctly in favor of Step 4; flagging so the invariant gets restated rather than silently treated as satisfied.

### 12. A trend regression does not affect the exit code. *(Noted — no action)*

Step 4 says *"`--compare` is the trend; floors are the gate. Both must pass for KEEP."* Today a `[REGRESSED]` metric prints and exits 0 ([cli.py:276-297](../../src/lds_study/cli.py#L276-L297)). Reading the plan as a whole, "both must pass" belongs to `lds iterate` (PR6c, exit 0/1/2/3), and leaving `lds eval`'s exit semantics alone is the right PR6a call. Worth confirming explicitly before PR6c so the contract is not decided by accident.

### 13. `--compare auto` has nothing to compare against until a summary is committed. *(Noted — no action)*

`git ls-files "outputs/eval/*.summary.json"` returns 0 rows in this repo today; the backfilled `2026-07-21-r2.summary.json` is PR6d work. So on merge, and on any fresh clone, `auto` resolves to "no reference" until someone runs an eval and commits its summary. The plan claims PR6a *"ships value immediately: 'did this run regress?' becomes answerable"* — accurate one commit later, not at merge. Low friction, but worth stating in the PR description so the first user is not confused by a comparison-free report.

## Net assessment

Finding 1 must be fixed before merge. Everything else in this PR is a plumbing change that is reversible; a leaked restricted question string in a committed, allowlisted JSON file is not. The fix is small — drop one field, then rewrite the guard test to actually traverse the generation path — but the *test* fix matters more than the field fix, because the current test's green result is what would let the next boundary widening through.

Findings 2 and 3 are worth fixing in the same PR. Both are silent-wrong-answer bugs in the feature this PR exists to deliver, both are a few lines, and both undermine the "did this run regress?" claim in ways a user cannot detect from the output. Finding 5 belongs with them — the strengthened test catches Finding 2 for free.

Findings 4, 6, 7 are cheap and I would take them now; 7 in particular touches the markdown layout that PR6d's `check_eval_reports.py` will have to parse, and churning that layout across two PRs is avoidable. 8–10 are cleanup. 11–13 need no code, only a sentence each in the PR description or the plan's Verification section.

Scope discipline is good: no drive-by refactors, Steps 2/3/5–9 correctly absent, the one signature change (`report_paths` → 3-tuple) has both call sites updated, and `config_fingerprint` is stubbed rather than half-implemented. PR6a is genuinely thin, as the plan demanded.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **86 passed in 7.22s**
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- `python scripts/check_staged_data.py --paths outputs/eval/2026-07-21-r2.md` → exit 0
- `python scripts/check_staged_data.py --paths outputs/eval/2026-07-21-r2.summary.json` → exit 0
- `python scripts/check_staged_data.py --paths outputs/eval/2026-07-21-r2.json` → exit 1 (correctly rejected)
- Gitignore gate: `touch outputs/eval/ZZTEST.summary.json outputs/eval/ZZTEST.json; git status --porcelain -uall outputs/eval/` → only `?? outputs/eval/ZZTEST.summary.json` (summary trackable, full sidecar still ignored)
- **Leak repro** (scratchpad, `include_local=True`, generation path, generator raising with restricted text in the message) → `SECRET IN SUMMARY: True`; `first_error: upstream 400: prompt was RESTRICTED_LOCAL_QUESTION_TEXT_NEVER_COMMIT`
- **Sort repro**: `sorted([...], reverse=True)[0]` → `verify-b.summary.json` over `2026-07-22.summary.json`
- `cd <non-repo>; git ls-files "outputs/eval/*.summary.json"` → `fatal: not a git repository`, exit 128 (proves Finding 5)
- `git ls-files "outputs/eval/*.summary.json"` in repo → 0 rows (Finding 13)
- Grep gates: `report_paths` — 2 call sites, both updated to the 3-tuple; `eval_cfg` / `settings.effective_root` confirmed to exist on the paths the new code uses
- Spot-checks: `AggregateMetrics.to_dict` field list; `COMPARABILITY_FIELDS` vs the plan's guarded-field list; `_primary_aggregate` positional read; new markdown sections ordered before `## Per-item results` (PR6d parser unaffected)

*Not run (require GPU/Ollama/built index, out of reach here): the plan's local verification block — `lds eval --compare auto` against a real index, and the two-run `verify-a` / `verify-b` sequence.*
