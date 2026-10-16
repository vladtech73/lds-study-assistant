# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 5 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows rounds [1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md), [2](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-2.md), [3](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-3.md), [4](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-4.md).*

## Verdict: One blocker left — the test suite is red, and CI gates on it.

Every round 4 finding is fixed, and I verified each by running rather than reading. A redirected KEEP run now exits **0** with the model label intact (`citation_validity (m): 0.9500 -> 0.9400`); restricted question text no longer reaches the committed `*.md` (`SECRET in *.md: False`); the section heading is renamed to `## Trend vs previous`, ending the `## Comparison` collision. I also ran the `--compare auto` lifecycle end to end through `run_eval` in a real git repo for the first time — commit a summary, re-run, narrow the run, collide the stem — and all four behaviors are correct.

But the remediation for round 4's Finding 4 shipped a **failing test**. `test_cli_eval_compare_keep_exit_and_console_encoding` asserts a bare substring against rich output rendered with `force_terminal=True`, and rich's `ReprHighlighter` splits `qwen2.5:7b-instruct` into `qwen2.\x1b[1m5:7b\x1b[0m-instruct`. `.github/workflows/ci.yml:71` runs `pytest -q`, so this branch fails CI as it stands. The irony is sharp: the test added to close a coverage gap is the only thing blocking merge, and it models the wrong scenario — a redirect is by definition not a terminal, which is exactly what the assertion trips over.

`1 failed, 94 passed`; `ruff` clean.

## Round 4 finding disposition

| # (R4) | Severity | Status | Evidence |
|---|---|---|---|
| 1 — redirect crash, KEEP exits 1 | High | **Fixed** | `render_comparison_console` is ASCII on the delta path (`->`, `--`); repro re-run → `REDIRECTED KEEP EXIT=0` with the full verdict block printed. `compare.py` now has zero cp1252-unencodable characters |
| 2 — rich markup swallows model name | High | **Fixed** | Label is `citation_validity (qwen2.5:7b-instruct)` (parens, not brackets) plus `console.print(line, markup=False)` at [cli.py:278](../../src/lds_study/cli.py#L278) with a comment explaining why |
| 3 — restricted text in committed `*.md` | High | **Fixed** | `first_error` replaced by counts: `\* Errors: \`mock-a\`: 1 (details in JSON sidecar)` ([report.py diff](../../src/lds_study/eval/report.py)), with a comment naming the copyright reason. Repro → `SECRET in *.md (COMMITTED): False` |
| 4 — no test executes the CLI | Medium | **Addressed, but the test fails** | `test_cli_eval_compare_keep_exit_and_console_encoding` added — see Finding 1 |
| 5 — two `## Comparison` headings | Low | **Fixed** | Renamed to `## Trend vs previous` at [compare.py:308](../../src/lds_study/eval/compare.py#L308) and [compare.py:322](../../src/lds_study/eval/compare.py#L322); rendered report confirms one `## Comparison (generation)` and one `## Trend vs previous` |
| 6 — TOCTOU stem dedup | Trivial | Not fixed | Inherent to pre-existing design; unchanged |
| 7 | Noted | Unchanged | — |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema v1, aggregates-only** | Complete | Projection is fail-closed; import-time invariant guards the compare keys |
| **Step 1 — copyright boundary (both artifacts)** | Complete | Summary *and* markdown both verified clean under a generation-path failure carrying restricted text |
| **Step 1 — persisted gate result** | Complete | `## Keep-or-revert` with floors and per-model verdict, read in a rendered report |
| **Step 1 — gitignore + allowlist** | Complete | Verified across rounds |
| **Step 4 — `--compare auto` lifecycle** | Complete | Newly verified end to end in a real git repo (below) |
| **Step 4 — comparability guard** | Complete | Narrowed `--buckets` run against a full reference → `comparable: False`, names `buckets` |
| **Step 4 — markdown rendering** | Complete | Full report read; repo-relative paths, no heading collision |
| **Step 4 — console rendering** | Complete | Redirected KEEP → exit 0, model label intact |
| **Step 4 — CLI wiring** | Complete | `--compare` reaches `run_eval` verbatim; `--help` renders |
| **Step 10 — tests** | **Failing** | Finding 1 |
| Steps 2, 3, 5–9 | Deferred-as-planned | Correctly absent |

**`--compare auto` lifecycle, run through `run_eval` in a real git repo** (never exercised before this round):

```
1) first run, nothing tracked   -> no reference (no tracked *.summary.json)
   tracked now: outputs/eval/run-a.summary.json
2) second run, auto            -> newest git-tracked summary (run-a.summary.json, generated_at=2026-07-22T20:42:44…)
   comparison: (True, 'ok')
3) narrowed --buckets run      -> comparable: False
   reason: not comparable — run shape differs: buckets: previous=None current=('adversarial',)
4) re-run stem 'run-a'         -> wrote run-a-2.summary.json | compared against tracked run-a
```

All four correct, including `exclude` (the run never compares against its own output) and the dedup interaction.

## Findings (ranked)

### 1. The test suite is red; CI gates on it. *(Critical)*

```
FAILED tests/test_pr6_iterate.py::test_cli_eval_compare_keep_exit_and_console_encoding
1 failed, 94 passed in 7.64s
```

[.github/workflows/ci.yml:71](../../.github/workflows/ci.yml#L71) runs `pytest -q`, so the branch cannot merge green.

The failing assertion is [test_pr6_iterate.py:808](../../tests/test_pr6_iterate.py#L808):

```
AssertionError: assert 'qwen2.5:7b-instruct' in
  'Comparison vs previous:\r\n  citation_validity \x1b[1m(\x1b[0mqwen2.\x1b[1m5:7b\x1b[0m-instruct\x1b[1m)\x1b[0m: …'
```

The product is fine. The cause is the test's own `Console(file=buf, force_terminal=True, …)`: with a terminal asserted, rich applies `ReprHighlighter`, which matches the `5:7b` fragment and wraps it in ANSI codes, splitting the model name mid-token so a plain `in` check fails. Isolated:

```
force_terminal=True   model-name-intact=False
force_terminal=False  model-name-intact=True
```

Two things are wrong, and the second matters more than the first:

- **It fails.** One keyword (`force_terminal=False`) or an ANSI-stripping comparison fixes it.
- **It tests the wrong thing.** The block's own comment reads *"Console lines must survive a cp1252 stream (Windows redirect)"* — but a redirect is precisely the case where rich is **not** a terminal. Asserting `force_terminal=True` models an interactive console while claiming to model a redirect. The encoding property it wants did pass (the cp1252 encode succeeded, which is the real round 4 regression guard); only the label assertion tripped, on styling that never occurs in the scenario under test.

This is deterministic and platform-independent — `ReprHighlighter` behavior does not vary by OS — so it fails on `ubuntu-latest` too, not just here.

**Remediation:** Set `force_terminal=False` in the encoding block so it matches the redirect it describes. If terminal rendering is also worth asserting, make it a separate case that strips ANSI (`rich.text.Text.from_ansi(...).plain`) before checking the label, and pick a fixture model id without a `N:N` fragment so the intent is not hostage to highlighter heuristics.

### 2. "ASCII-safe" is claimed but not true on the not-comparable path. *(Low)*

`render_comparison_console`'s docstring now reads *"Plain lines for CLI console output (ASCII-safe for redirected Windows stdout)"* ([compare.py:377](../../src/lds_study/eval/compare.py#L377)). The delta path is ASCII, but the not-comparable path is not: `diff_summaries` builds `reason="not comparable — run shape differs: …"` with U+2014, and `render_comparison_console` interpolates it.

```
pure ASCII? False
  cp1252: OK
  cp850:  UnicodeEncodeError: 'charmap' codec can't encode character '—'
  ascii:  UnicodeEncodeError: 'ascii' codec can't encode character '—'
```

cp1252 is the realistic Windows default and handles it, so this is not the round 4 crash returning. But `chcp 850` consoles and `PYTHONIOENCODING=ascii` do exist, and the failure mode would be identical: a crash after the eval completes, converting a KEEP into a non-zero exit. The round 4 fix was applied to the two strings that were reported rather than audited across the module — the same "one branch missed" pattern as round 3.

The rendered line also reads badly, because both layers prefix the same words:

```
Comparison: not comparable -- not comparable — run shape differs: buckets: previous=None current=('adversarial',)
```

**Remediation:** Use `--` in the `diff_summaries` reason, or drop the redundant prefix in `render_comparison_console` and let the reason speak. Then make the docstring's claim testable: assert `all(ord(c) < 128 …)` over the output of both branches rather than asserting a single codec succeeds.

### 3. The CLI test patches the console it is meant to exercise. *(Low)*

[test_pr6_iterate.py](../../tests/test_pr6_iterate.py) does `monkeypatch.setattr(cli_mod, "console", cli_mod.Console(legacy_windows=False))` before invoking the app, so the test never touches the product's real `console = Console()` at [cli.py:18](../../src/lds_study/cli.py#L18). Today that is harmless — the eval path is ASCII, so the real console is safe — but it means the one test covering the CLI would keep passing if someone reintroduced a non-ASCII character *and* the product console stayed unconfigured. Given that this exact regression is what round 4 found, the guard should exercise the shipped object.

**Remediation:** Drop the console monkeypatch and let `CliRunner` capture the real one, or add the encoding assertion against `cli_mod.console` directly.

### 4. Pre-existing arrows remain in `prepare` / `index` / `finetune-dataset`. *(Noted — no action)*

[cli.py:90](../../src/lds_study/cli.py#L90), [cli.py:98](../../src/lds_study/cli.py#L98), [cli.py:131](../../src/lds_study/cli.py#L131), [cli.py:326](../../src/lds_study/cli.py#L326) still emit U+2192 through `console.print`, so those commands still crash on a redirect. Correctly left alone — out of PR6a scope, and I flagged them as pre-existing in round 4. Worth a tracked follow-up rather than scope creep here, since the root cause (an unconfigured `Console()`) is one line and would fix all four.

### 5. Carried: TOCTOU stem dedup; no committed summary yet; trend regression does not gate the exit code. *(Noted — no action)*

Unchanged and still correct for PR6a. The lifecycle test above confirms the intended sequence works as soon as a first summary is committed.

## Net assessment

Fix Finding 1 and merge. It is a one-keyword change in a test, the product behavior underneath it is verified correct, and everything else on the branch is now green across five rounds. Finding 2 is worth folding into the same commit — it is two string edits and it closes the last gap in the ASCII-safety property the code now advertises. Finding 3 is a five-line simplification that makes the new CLI test actually guard the shipped console; I would take it now while the test is being touched anyway.

Findings 4 and 5 need no code in this PR.

Substantively, PR6a is done. Every plan "Done when" clause in Steps 1 and 4 is satisfied and I have now verified the headline claim — "did this run regress?" — end to end in a real git repo rather than in fixtures: a committed summary is found, a narrowed run is refused with the offending field named, a run never compares against itself, and the verdict survives a redirect with the right exit code. The copyright boundary is closed on both committed artifacts, which took until round 4 to establish because rounds 1–3 checked only the one the plan named.

The pattern across five rounds is worth recording for PR6b–6e: every round that changed *technique* found something, and every round that repeated the previous technique mostly confirmed prior findings. Reading the diff found the schema and comparison-logic defects; running the CLI found the crash and the markup bug; rendering the artifact found the markdown leak and the heading collision; running the lifecycle in a real repo found nothing — which is itself the useful result, and the reason I would stop here.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **1 failed, 94 passed in 7.64s** (86 → 89 → 92 → 93 → 95 collected)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- `grep -nE "pytest|ruff" .github/workflows/ci.yml` → `pytest -q` at line 71, `ruff check src scripts tests` at line 68 (confirms the failure gates CI)
- **R4 Finding 1 regression check**: stubbed KEEP run through the real typer app, stdout redirected → `REDIRECTED KEEP EXIT=0`, full output including `Keep-or-revert vs eval.baselines: m: KEEP`
- **R4 Finding 2 regression check**: same run → `citation_validity (m): 0.9500 -> 0.9400 (-0.0100)`, label present
- **R4 Finding 3 regression check**: generation-path failure carrying restricted text, `include_local=True` → `SECRET in *.summary.json: False`, `SECRET in *.md (COMMITTED): False`; markdown now emits `\* Errors: \`mock-a\`: 1 (details in JSON sidecar)`
- **R4 Finding 5 regression check**: freshly rendered report → `## Comparison (generation)` (line 30) and `## Trend vs previous` (line 55), no collision
- **`--compare auto` lifecycle** in a temp git repo through `run_eval`: no-reference → commit → auto-selects → narrowed run refused naming `buckets` → same-stem re-run dedups to `run-a-2` and still compares against tracked `run-a`
- **Finding 1 isolation**: `force_terminal=True` → model name split by `ReprHighlighter`; `force_terminal=False` → intact
- **Finding 2 isolation**: not-comparable line encoded against cp1252 (OK), cp850 (`UnicodeEncodeError`), ascii (`UnicodeEncodeError`); `pure ASCII? False`
- Re-scanned `compare.py` and `cli.py` for cp1252-unencodable characters: none in `compare.py`; four pre-existing in `cli.py` outside this diff
- *Method note:* a stale scratch file briefly showed the old heading after a suppressed-output re-run; I deleted it and regenerated before reporting. Same class of mistake as round 4's diffstat assumption — verify the artifact is fresh, not just present.

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index.*
