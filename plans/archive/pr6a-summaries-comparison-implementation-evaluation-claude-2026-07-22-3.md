# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 3 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows [round 1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md) and [round 2](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-2.md).*

## Verdict: Safe to merge. One narrow residual path leak is worth a two-line fix first.

Both Round 2 blockers are fixed, and fixed at the right layer. Explicit `--compare` now resolves before any retrieval happens, so a bad reference costs nothing and writes nothing (verified: `calls["n"] == 0`, no output directory created). Report paths are rendered repo-relative through a shared `display_path()` helper, and the test that covers it asserts the *absence* of `Users` / `AppData` / `C:` rather than the presence of the new form — the right polarity for a leak test. The metric-key coupling I raised as a test gap was closed harder than requested: it is now an import-time `RuntimeError`, not an assertion.

92 tests and `ruff` pass. Every finding across three rounds is now resolved except two Trivials I flagged as optional, plus one new Low: the `compare failed:` branch still writes an absolute path — with the OS username — into the committed markdown report. It is the one branch of the path-normalization fix that the new tests do not exercise, which is why it survived.

## Round 2 finding disposition

| # (R2) | Severity | Status | Evidence |
|---|---|---|---|
| 1 | Critical | **Fixed** | Explicit `--compare` resolved at [run.py:252-264](../../src/lds_study/eval/run.py#L252-L264), before `load_golden_set`; result reused later ([run.py:435-436](../../src/lds_study/eval/run.py#L435-L436)) so no double resolution. Repro now: `RAISED: compare path not found: …` / `files on disk: NO DIR` — the eval directory is never even created |
| 2 | High | **Fixed (one branch residual)** | `display_path()` ([compare.py:277-282](../../src/lds_study/eval/compare.py#L277-L282)) + `normalize_compare_display()` ([compare.py:285-299](../../src/lds_study/eval/compare.py#L285-L299)); repro now prints `- compare=outputs/eval/a.summary.json`, `- Previous: \`outputs/eval/a.summary.json\``, `- Current: \`outputs/eval/b.summary.json\``. See Finding 1 for the branch that was missed |
| 3 | Medium | **Fixed, stronger than asked** | `_COMPARE_REQUIRED_AGGREGATE_KEYS` checked at import time with a `RuntimeError` ([compare.py:38-47](../../src/lds_study/eval/compare.py#L38-L47)) — a broken projection fails the whole CLI, not one test. Plus `test_run_eval_generation_compare_round_trips_citation_delta` ([test_pr6_iterate.py:551-613](../../tests/test_pr6_iterate.py#L551-L613)) runs two real generation evals and asserts a non-`n/a` per-model citation delta |
| 4 | Low | **Fixed** | `created: list[Path]` accumulated and unwound on any exception ([run.py:399](../../src/lds_study/eval/run.py#L399), [run.py:520-524](../../src/lds_study/eval/run.py#L520-L524)); a sidecar failure now removes the markdown too |
| 5 | Low | **Fixed** | Compare fixtures build through `summary_safe_aggregate()` ([test_pr6_iterate.py:277-357](../../tests/test_pr6_iterate.py#L277-L357)), so tests consume exactly what `write_summary_json` emits |
| 6 | Trivial | **Fixed** | `except (OSError, ValueError)` at [compare.py:446](../../src/lds_study/eval/compare.py#L446) and [compare.py:456](../../src/lds_study/eval/compare.py#L456) |
| 7 | Trivial | **Not fixed** | `_format_generated_at()` still re-reads and re-parses the file `_summary_recency_key()` just parsed. Flagged as optional in round 2; still fine to leave |
| 8–10 | Noted | Unchanged, correctly | No code needed; 10 still true (`git ls-files "outputs/eval/*.summary.json"` → 0 rows) |

Rounds 1 and 2 findings 1–10 (R1) and 1–6 (R2) are all resolved; I re-ran the round 1 leak repro and the round 2 path repro against current code to confirm neither regressed.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema v1, aggregates-only** | Complete | [report.py:97-158](../../src/lds_study/eval/report.py#L97-L158) |
| **Step 1 — copyright boundary** | Complete | Fail-closed projection; leak repro → `SECRET IN SUMMARY: False`; generation-path test at [test_pr6_iterate.py:190-248](../../tests/test_pr6_iterate.py#L190-L248) |
| **Step 1 — persisted gate result** | Complete | Summary + markdown, with a "Gate not run" branch distinguishing not-run from clean |
| **Step 1 — gitignore + allowlist** | Complete | `check_staged_data.py --paths …summary.json` → 0; `….json` → 1 |
| **Step 4 — `--compare <path\|auto\|none>`** | Complete | Fail-fast on explicit, soft on `auto` |
| **Step 4 — git-aware, chronological `auto`** | Complete | `generated_at` sort, mtime fallback; adversarial 2099-timestamped untracked fixture loses to a tracked 2026 one |
| **Step 4 — `diff_summaries()` per-model** | Complete | Model-keyed, order-normalized, `models` in the guard list |
| **Step 4 — tolerance; tol=0 for recall/retrieval-only** | Complete | [compare.py:168-178](../../src/lds_study/eval/compare.py#L168-L178) |
| **Step 4 — comparability guard** | Complete | 8 fields, one test case each |
| **Step 4 — markdown + console rendering** | **Complete (one residual)** | Finding 1 |
| **Step 4 — `--check-baselines` unchanged** | Complete | [cli.py:287-297](../../src/lds_study/cli.py#L287-L297) untouched across all three rounds |
| **Step 10 — tests (PR6a subset)** | Complete | 92 pass; every "Done when" clause in Steps 1 and 4 has a corresponding test |
| Steps 2, 3, 5–9 | Deferred-as-planned | Correctly absent |

Plan "Done when" checks, Step 1: committable summary ✓, full sidecar still refused ✓, test asserts no question text ✓ (now on the generation path). Step 4: two consecutive runs produce a delta table ✓, differing `golden_hash` refuses to diff ✓, untracked summary never auto-selected ✓ (real git repo), sub-tolerance drop reported but not flagged ✓.

## Findings (ranked)

### 1. The `compare failed:` branch still writes an absolute path — with the OS username — into the committed report. *(Low)*

Round 2 Finding 2 was fixed for the three lines it named, but the reason string on the soft-failure branch was not routed through `display_path()`. `load_summary()` raises `ValueError(f"summary is not an object: {path}")` with the resolved absolute path ([compare.py:67](../../src/lds_study/eval/compare.py#L67)); `run_eval` catches it and formats `compare failed: {exc}` ([run.py:459-462](../../src/lds_study/eval/run.py#L459-L462)), which `render_no_comparison_section()` writes verbatim into the markdown.

Reproduced with a reference summary containing valid JSON of the wrong type:

```
'- compare=outputs/eval/bad.summary.json'
'- No comparison: compare failed: summary is not an object: C:\Users\vladtech\AppData\Local\Temp\tmpbpht0rbr\outputs\eval\bad.summary.json'
```

Note the two lines disagree: the header is correctly relative, the reason immediately below it is not. Narrow trigger — it needs a malformed reference summary — but `outputs/eval/*.md` is committed, so it is the same class as the High that was just fixed, and it is exactly the branch the new assertions miss (`test_run_eval_compare_embeds_section` and the generation round-trip both take the success path).

**Remediation:** Have `load_summary()` raise with `path.name`, or format the reason as `compare failed: {display_path(ref_path, repo_root)}: {exc}` and keep exception text out of the report. Then add a case to the existing tests that corrupts the reference and re-asserts `"Users" not in body`.

### 2. `_format_generated_at()` re-parses a file already parsed by the sort key. *(Trivial — carried)*

Unchanged from Round 2 Finding 7. [compare.py:438-458](../../src/lds_study/eval/compare.py#L438-L458). Irrelevant at current scale; fold the timestamp into `_summary_recency_key`'s return if it is ever convenient.

### 3. Artifacts are added to the cleanup list after their write returns. *(Trivial)*

[run.py:399](../../src/lds_study/eval/run.py#L399), [run.py:490](../../src/lds_study/eval/run.py#L490), [run.py:519](../../src/lds_study/eval/run.py#L519) each `created.append(...)` *after* the corresponding write. A write that fails partway therefore leaves a partial file outside the cleanup set. In practice each writer is a single `path.write_text()` ([report.py:188](../../src/lds_study/eval/report.py#L188), [report.py:436](../../src/lds_study/eval/report.py#L436), [report.py:480](../../src/lds_study/eval/report.py#L480)), so this only bites on disk-full or interrupt. Appending before the write would close it.

### 4. Confusing operator precedence in a new assertion. *(Trivial)*

[test_pr6_iterate.py:527](../../tests/test_pr6_iterate.py#L527):

```python
assert not list(out.glob("should-not-exist*")) if out.exists() else True
```

This parses as `assert (X if out.exists() else True)`, which is what was meant, but it reads as `(assert X) if …`. The line above it (`assert calls["n"] == 0`) is the assertion doing the real work here. Rewrite as an `if out.exists():` guard.

### 5. The metric-coupling check raises at import time. *(Noted — no action)*

[compare.py:42-47](../../src/lds_study/eval/compare.py#L42-L47) raises `RuntimeError` at module scope if `SUMMARY_AGGREGATE_KEYS` ever stops covering what `diff_summaries` reads. This is more aggressive than the static assertion I suggested — a violation takes down the entire `lds` CLI, not one test — and it adds a `compare.py` → `report.py` import edge (no cycle; `report.py` imports nothing from `compare.py`). Given the plan's "fail closed over make it work" posture and that the invariant is a copyright-boundary consequence, loud is correct. Flagging so it is a deliberate choice on record rather than a surprise for whoever next edits the key sets.

### 6. Carried: no committed summary yet, and a trend regression does not affect the exit code. *(Noted — no action)*

`git ls-files "outputs/eval/*.summary.json"` still returns 0 rows, so `--compare auto` resolves to `no reference (no tracked *.summary.json)` on merge and on any fresh clone — now with an explicit `- No comparison: …` line in the report rather than silence. Trend regressions still print `[REGRESSED]` and exit 0; floors remain the only gate, which is right for PR6a and becomes `lds iterate`'s exit 1 in PR6c. Both deserve a line in the PR description, not code.

## Net assessment

Merge it. Finding 1 is worth the two-line fix first — it is cheap, it is the same defect class that was just treated as High, and every additional line in a committed report is a line PR6d's `check_eval_reports.py` has to reason about. Findings 2–4 are housekeeping that can ride along or be skipped. 5–6 are prose.

Three things stand out about how this converged. The remediations kept moving the fix *up* a layer rather than patching the symptom: Round 1's `first_error` deletion became a fail-closed key projection, Round 2's late `raise` became pre-flight validation, and Round 2's test-gap became an import-time invariant. The path fix was done through one shared helper rather than three call-site edits, which is why only the one branch that does not use it was missed. And the tests added in each round were adversarial rather than confirmatory — the 2099-timestamped untracked fixture, the retriever call counter, the generator that raises with restricted text in its message. That is the pattern that closed Round 1's central problem, which was a guard test passing on a path where the hazard could not occur.

Scope held across all three rounds: no new commands, no config writes, no changes to `--check-baselines`, Steps 2/3/5–9 still absent. PR6a is the thin, independently-mergeable slice the plan asked for.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **92 passed in 7.60s** (86 → 89 → 92 across rounds)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- **R2 Finding 1 regression check**: `run_eval(..., compare="2026-07-21-r2")` → `RAISED: compare path not found: 2026-07-21-r2`; `files on disk: NO DIR` (fails before the output dir is created); `test_run_eval_bad_compare_fails_before_retrieval` asserts `calls["n"] == 0`
- **R2 Finding 2 regression check**: two chained runs, grep of the second report → `- compare=outputs/eval/a.summary.json`, `- Previous: \`outputs/eval/a.summary.json\``, `- Current: \`outputs/eval/b.summary.json\`` — all relative
- **Finding 1 repro** (scratchpad): reference summary containing `["not","an","object"]` → report line `- No comparison: compare failed: summary is not an object: C:\Users\vladtech\...`
- **R1 Finding 1 regression check**: generation-path leak repro (`include_local=True`, generator raising with restricted text) → `SECRET IN SUMMARY: False`; `KeyError: 'first_error'` when probing the removed field
- `python scripts/check_staged_data.py --paths outputs/eval/2026-07-21-r2.summary.json` → exit 0; `…-r2.json` → exit 1
- `git ls-files "outputs/eval/*.summary.json"` → 0 rows
- Grep gates: `_COMPARE_REQUIRED_AGGREGATE_KEYS` enforced at import (not test-only); `eval_cfg` confirmed defined at [run.py:228](../../src/lds_study/eval/run.py#L228), before the new fail-fast block at 252; all three report writers confirmed single-`write_text`
- Spot-checks: no import cycle between `compare.py` and `report.py`; explicit-mode resolution passes `exclude=None` but cannot self-compare because the stem dedup bumps a colliding output; `display_path` falls back to `path.name` for references outside the repo root
- Reviewed the full diff of all six modified files plus `compare.py` and `tests/test_pr6_iterate.py`

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index.*
