# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 6 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows rounds [1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md), [2](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-2.md), [3](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-3.md), [4](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-4.md), [5](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-5.md).*

## Verdict: Green and mergeable. Two Medium input-validation gaps share one two-line fix.

All three round 5 findings are fixed. The suite is green (**95 passed**), `ruff` is clean, and the plan's offline verification block runs as written. The CLI test now exercises the shipped console instead of a patched one, and a second test covering the REVERT exit path was added alongside it.

This round I probed input validation on the comparison path, which no previous round had touched. `load_summary()` accepts any JSON object: it checks neither `schema_version` nor whether the file is a summary at all. Two consequences, both silent. A `schema_version: 99` payload diffs against v1 as `comparable: True` and emits five deltas. And `--compare outputs/eval/X.json` — the **restricted, gitignored** full sidecar — resolves, diffs clean, and the committed markdown report then cites that machine-local file by name, bypassing exactly the reproducibility contract the git-tracked `auto` path was built to enforce.

Neither is a blocker: both need a deliberate action (a typed path, or a schema bump that does not exist yet). Both are closed by the same guard in `load_summary`.

## Round 5 finding disposition

| # (R5) | Severity | Status | Evidence |
|---|---|---|---|
| 1 — failing CLI test, red CI | Critical | **Fixed** | `force_terminal=False` at [test_pr6_iterate.py:812](../../tests/test_pr6_iterate.py#L812); `95 passed in 7.60s`. A second test, `test_cli_eval_revert_exits_1` ([test_pr6_iterate.py:824](../../tests/test_pr6_iterate.py#L824)), now covers the REVERT exit path too |
| 2 — "ASCII-safe" claim false | Low | **Fixed** | Not-comparable line is now `Comparison: not comparable -- run shape differs: …`; `pure ASCII? True`; encodes clean under cp1252, cp850 **and** ascii. The doubled "not comparable … not comparable" phrasing is gone |
| 3 — CLI test patched its own console | Low | **Fixed** | Monkeypatch removed, replaced by the comment *"Exercise the shipped module console (do not replace it)"* at [test_pr6_iterate.py:767](../../tests/test_pr6_iterate.py#L767) |
| 4–5 | Noted | Unchanged, correctly | Pre-existing arrows in `prepare`/`index`/`finetune-dataset` still out of scope |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema v1, aggregates-only** | Complete | Fail-closed projection; import-time invariant on the compare keys |
| **Step 1 — copyright boundary (both artifacts)** | Complete | Verified in round 5 on summary *and* markdown |
| **Step 1 — persisted gate result** | Complete | Rendered and read |
| **Step 1 — gitignore + allowlist** | Complete | Deny-before-allow ordering confirmed correct at [check_staged_data.py:125-128](../../scripts/check_staged_data.py#L125-L128) — a denied path cannot be rescued by an allowlist match |
| **Step 4 — `--compare` resolution** | **Partial** | Correct for `auto`; accepts non-summary files on the explicit path — Finding 1 |
| **Step 4 — comparability guard** | **Partial** | 8 run-shape fields correct; `schema_version` unguarded — Finding 2 |
| **Step 4 — trend tolerance from config** | Complete | Verified flowing: `trend_tolerance: 0.90` in `configs/rag.yaml` → `ComparisonResult.tolerance=0.9`. Untested in the suite — Finding 3 |
| **Step 4 — rendering (markdown + console)** | Complete | Verified rounds 4–5 |
| **Step 4 — CLI wiring and exit codes** | Complete | KEEP → 0, REVERT → 1, both now under test |
| **Step 10 — tests** | Complete | 95 pass; gaps noted in Finding 3 |
| Steps 2, 3, 5–9 | Deferred-as-planned | `scripts/check_eval_reports.py` correctly absent (PR6d) |

Plan offline verification block, run verbatim: `pytest -q` → 95 passed; `ruff check src scripts tests` → clean; `check_staged_data.py --paths outputs/eval/2026-07-21-r2.md` → `OK — 1 path(s) checked`; `check_eval_reports.py` → not present, as expected for PR6a.

## Findings (ranked)

### 1. `--compare` accepts the restricted JSON sidecar and diffs it as a summary. *(Medium)*

`_resolve_summary_candidate()` never checks that the resolved file is a summary — for an absolute path it takes the path as given ([compare.py:471-472](../../src/lds_study/eval/compare.py#L471-L472)), and `load_summary()` accepts any JSON object ([compare.py:77-83](../../src/lds_study/eval/compare.py#L77-L83)). The full `*.json` sidecar happens to carry every comparability field and every metric key `diff_summaries` reads, so it diffs cleanly:

```
sidecar has items: True
compare_reason : explicit --compare …\outputs\eval\sc-a.json
comparable     : True
reason         : ok
report cites the sidecar: True
```

Two problems, the second larger than the first:

- **The committed report names a gitignored, restricted artifact.** No content leaks — `diff_summaries` reads only named aggregate keys, so the sidecar's `items` and `first_error` never surface — but the `## Trend vs previous` section in a committed `.md` now points a reader at `outputs/eval/sc-a.json`, a file that must never be shared and that no one else will have.
- **It bypasses the reproducibility contract.** The entire rationale for git-aware `auto` resolution — plan Step 4, *"the directory also holds untracked local runs, and picking one silently makes the diff unreproducible for anyone else"* — is defeated by an explicit path to a gitignored file, with no warning. The design carefully prevents this accidentally and permits it deliberately, without ever saying so.

The same hole accepts any roughly-shaped JSON, which is how Finding 2 becomes reachable in practice.

**Remediation:** In `load_summary()`, reject payloads containing an `items` key — that is the exact copyright-boundary marker, and a real summary can never have one. Optionally also require the resolved filename to end in `.summary.json` in `_resolve_summary_candidate()`. Two lines, fail-closed, and it closes Finding 2 in the same place.

### 2. `schema_version` is written but never validated. *(Medium)*

`SUMMARY_SCHEMA_VERSION = 1` is stamped into every summary ([report.py:121](../../src/lds_study/eval/report.py#L121)) and is in `SUMMARY_TOP_LEVEL_KEYS`, but nothing ever reads it back. It is absent from `COMPARABILITY_FIELDS`, and `load_summary()` does not check it:

```
schema_version guarded? False
v1 vs v99 comparable: True | reason: ok
deltas emitted: 5
```

A `grep` for `schema_version` across `src/`, `tests/` and `scripts/` returns only the writer and one assertion that the written value is `1`. Nothing consumes it.

This is latent — only one schema version exists — but the field's only purpose is to signal that semantics changed, and the moment it changes is exactly when nobody will remember to add the check. PR6b already has a placeholder waiting (`config_fingerprint`, commented *"Filled by PR6b fingerprints; present so schema is stable"*), and PR6d's promotion path will read summaries to write config floors. A v1/v2 mix diffs clean today because every guarded field (`golden_hash`, `k`, `profile`, `models`, …) can legitimately match across a schema change — so the guard that exists cannot catch the case the version field was added for.

**Remediation:** Reject unknown major versions in `load_summary()` (`if data.get("schema_version") != SUMMARY_SCHEMA_VERSION: raise ValueError(...)`). `run_eval` already degrades softly on `ValueError` from this call, so an old or future summary becomes `compare failed: …` in the report rather than a silently wrong trend table. Add `schema_version` to the round-trip test's assertions on the *read* side, not just the write side.

### 3. The `trend_tolerance` config read is untested. *(Low)*

`configs/rag.yaml` gains `trend_tolerance: 0.02`, and `run_eval` reads it as `float(eval_cfg.get("trend_tolerance", 0.02))` ([run.py:407](../../src/lds_study/eval/run.py#L407)) — a silent fallback to the identical value. The test fixture also sets `0.02`, so no test can distinguish "config was read" from "config key was misspelled and the default applied." A typo like `trend_tolerence` in the shipped config would be undetectable by the suite and by inspection of behavior.

I confirmed the plumbing works by hand:

```
trend_tolerance=0.02  -> ComparisonResult.tolerance=0.02
trend_tolerance=0.90  -> ComparisonResult.tolerance=0.9
```

**Remediation:** Set a distinctive value (e.g. `0.25`) in the test fixture's `rag.yaml` and assert `result.comparison.tolerance == 0.25`. One line, and it pins the config contract for PR6b–6d, which will add more keys under `eval:`.

### 4. Carried notes. *(Noted — no action)*

TOCTOU stem dedup, no committed summary yet, trend regression not gating the exit code, and the four pre-existing U+2192 arrows in `prepare` / `index` / `finetune-dataset`. All unchanged and all correct for PR6a.

## Net assessment

Merge it. Nothing here blocks: the suite is green, the plan's verification block passes, and both Mediums require a deliberate user action against a schema version that does not yet exist. I would still take them before merge, because they collapse into a single guard in `load_summary()` — reject `items`, reject unknown `schema_version` — which is cheaper now than after PR6d starts reading summaries to write config floors. Finding 3 is a one-line fixture change worth making while the tests are open.

Six rounds is past the point of useful return. The last two rounds found three defects between them and all three are input-validation edges on paths a user has to opt into by typing; nothing in rounds 4–6 touched the core measurement, comparison, or copyright logic, which has been stable since round 3. The remaining risk in PR6a is not in code I can read — it is in the one thing I have never been able to run, the plan's local block against a real index with Ollama. That is where I would spend the next hour instead of a seventh review.

Method note across the series, offered for PR6b–6e rather than as criticism of this PR: rounds 1–3 read the diff and converged on agreement; round 4 ran the CLI and found three High findings in a tree I had called safe; round 5 ran the artifact lifecycle; round 6 attacked inputs. Each change of technique paid, each repetition of one did not. If PR6b gets a single review, it should be an executing one.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **95 passed in 7.60s** (86 → 89 → 92 → 93 → 94+1F → 95)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- `python scripts/check_staged_data.py --paths outputs/eval/2026-07-21-r2.md` → `OK — 1 path(s) checked`, exit 0
- `Test-Path scripts/check_eval_reports.py` → `False` (PR6d, correctly absent)
- `configs/rag.yaml` parses; `eval` keys = `['baselines', 'recall_k', 'trend_tolerance']`
- **R5 Finding 1 regression check**: `force_terminal=False` in the encoding block; suite green; `test_cli_eval_revert_exits_1` added
- **R5 Finding 2 regression check**: not-comparable console line → `pure ASCII? True`; encodes OK under cp1252, cp850, ascii
- **R5 Finding 3 regression check**: no `cli_mod.console` monkeypatch remains; comment documents the intent
- **Finding 1 repro**: two real runs, second with `compare=<first run's *.json sidecar>` → `comparable: True`, `reason: ok`, committed report contains `sc-a.json`; sidecar confirmed to contain `items`
- **Finding 2 repro**: `diff_summaries(v1, v99)` → `comparable: True`, 5 deltas; `'schema_version' in COMPARABILITY_FIELDS` → `False`; `grep -rn schema_version src/ tests/ scripts/` → writer + one write-side assertion only
- **Finding 3 repro**: two full `run_eval` pairs with `trend_tolerance` `0.02` vs `0.90` in the fixture config → `ComparisonResult.tolerance` `0.02` vs `0.9` (config read confirmed working, just unpinned)
- Read `check_staged_data.check_paths` and confirmed `is_denied` precedes the allowlist branch, so no allowlist pattern can rescue a denied path
- Read `load_summary` in full: no `schema_version` check, no `items` check, no filename check

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index — the largest remaining unknown, as noted above.*
