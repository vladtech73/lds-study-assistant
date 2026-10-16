# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 4 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows rounds [1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md), [2](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-2.md), [3](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-3.md).*

## Verdict: Not safe to merge — I was wrong to sign off in round 3.

This round I stopped re-reading the diff and did what the previous three rounds skipped: drove the actual typer CLI, and rendered a full report end to end. Both were productive, and both found defects that three rounds of reading missed.

The CLI crashes. `lds eval --compare` with any delta emits `→` (U+2192) through `console.print`, and whenever stdout is a pipe or a redirect this box resolves stdout to cp1252 and raises `UnicodeEncodeError`. A **KEEP** run redirected to a file exits **1** — the code that means REVERT — because the crash happens before the keep-or-revert block runs. That directly breaks the plan's Step 8 nightly script and poisons the exit-code contract PR6c is built on. Separately, rich parses `[model]` as markup and silently swallows the model name from every per-model comparison line, so the multi-model comparison this PR exists to enable prints unlabeled rows.

And rendering a full report surfaced the one I should be most uncomfortable about: the restricted question text that round 1 scrubbed out of `*.summary.json` is still written into `*.md` — which has been committed under the same allowlist since PR1. The summary is provably clean and the file next to it is not. That is pre-existing, not introduced here, but three rounds of my own reports concluded "the copyright boundary is closed" on the strength of a fix that only covered one of the two committed artifacts.

Round 3's finding was fixed and is covered by a new test; 93 tests and `ruff` pass.

## Round 3 finding disposition

| # (R3) | Severity | Status | Evidence |
|---|---|---|---|
| 1 | Low | **Fixed** | `load_summary` raises with `path.name` and a comment naming the reason ([compare.py:77-83](../../src/lds_study/eval/compare.py#L77-L83)); repro now yields `compare failed: summary is not an object: bad.summary.json`; new `test_run_eval_corrupt_reference_keeps_paths_relative` ([test_pr6_iterate.py:531](../../tests/test_pr6_iterate.py#L531)) |
| 2 | Trivial | Not fixed | `_format_generated_at()` still re-parses; flagged optional twice, fine to leave |
| 3 | Trivial | Not fixed | `created.append(...)` still follows each write; single-`write_text` writers make it near-unreachable |
| 4 | Trivial | Not fixed | Precedence oddity at [test_pr6_iterate.py:527](../../tests/test_pr6_iterate.py#L527) |
| 5–6 | Noted | Unchanged, correctly | — |

*Correction to my own method:* I opened this round assuming the tree was unchanged because `git diff main --stat` was byte-identical to round 3. It was not — the round 3 fix landed in `compare.py`, which is untracked and so contributes no diffstat, and the test count moved 92 → 93. Diffstat identity is not tree identity; I should have hashed or run the repro first, which is what actually caught it.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema v1, aggregates-only** | Complete | [report.py:97-158](../../src/lds_study/eval/report.py#L97-L158) |
| **Step 1 — copyright boundary (summary)** | Complete | Fail-closed projection; repro → `SECRET in *.summary.json: False` |
| **Step 1 — copyright boundary (as a boundary)** | **Breached in the sibling artifact** | Finding 3 |
| **Step 1 — persisted gate result** | Complete | Verified in a rendered report: `## Keep-or-revert` with floors and a REVERT reason |
| **Step 1 — gitignore + allowlist** | Complete | Filename-scoped only, which is what Finding 3 exploits |
| **Step 4 — `--compare` resolution** | Complete | Fail-fast on explicit, soft on `auto`, chronological, git-tracked only |
| **Step 4 — `diff_summaries()`** | Complete | Verified against a real rendered report: per-model rows, `—` for the shared recall row |
| **Step 4 — markdown rendering** | Complete | Full report read end to end; all paths repo-relative |
| **Step 4 — console rendering** | **Broken** | Findings 1 and 2 |
| **Step 4 — CLI wiring** | Partial | `--compare` parses and passes through correctly (`--help` renders it; stub confirms `compare='outputs/eval/a.summary.json'` reaches `run_eval`), but the render path crashes |
| **Step 10 — tests** | **Partial** | 93 pass, but nothing executes the CLI; Findings 1 and 2 are both invisible to the suite |
| Steps 2, 3, 5–9 | Deferred-as-planned | Correctly absent |

## Findings (ranked)

### 1. `lds eval --compare` crashes when stdout is redirected, and a KEEP run exits 1. *(High)*

[compare.py:394](../../src/lds_study/eval/compare.py#L394) builds each delta line with `→` (U+2192), and [cli.py:277-278](../../src/lds_study/cli.py#L277-L278) pushes it through the module-level `Console()`. When stdout is a pipe or a file redirect, Python falls back to `locale.getpreferredencoding()` — cp1252 on this machine — and the write raises.

```
$ python -c "...render_comparison_console...; c.print(line)" > out.txt 2>&1 ; echo exit=$?
exit=1
stdout encoding = cp1252
Comparison vs previous:
  citation_validity: 0.9500Traceback (most recent call last):
UnicodeEncodeError: 'charmap' codec can't encode character '→'
```

The consequence is worse than a cosmetic crash. Driving the real typer app with a stubbed `run_eval` returning a clean **KEEP** (`baseline_verdicts={"m": (True, [])}`, a sub-tolerance −0.01 delta, `regressed=False`) and redirecting stdout:

```
$ python exitcode.py > ec.txt 2>&1 ; echo EXIT=$?
EXIT=1
UnicodeEncodeError: 'charmap' codec can't encode character '→'
```

Exit 1 is the REVERT signal. The crash happens at [cli.py:277](../../src/lds_study/cli.py#L277), above the keep-or-revert block at [cli.py:287-297](../../src/lds_study/cli.py#L287-L297), so the verdict never prints and every redirected run reports failure regardless of the metrics. `run_eval` has already returned, so the report, sidecar and summary are all safely on disk — the damage is entirely in the exit code and the lost verdict.

This lands on the plan's Step 8 directly: `scripts/nightly_eval.ps1` is specified to run `lds iterate` and "exit non-zero on REVERT", and it redirects. It would flag REVERT on every successful nightly. PR6c's exit-code contract (0 KEEP / 1 REVERT / 2 stale / 3 not comparable) inherits the same hazard.

**Scope note, stated plainly:** the arrow-in-`console.print` pattern is pre-existing — [cli.py:90](../../src/lds_study/cli.py#L90), [cli.py:98](../../src/lds_study/cli.py#L98), [cli.py:131](../../src/lds_study/cli.py#L131), [cli.py:325](../../src/lds_study/cli.py#L325) all predate this branch, so `lds prepare` and `lds index` already crash on redirect. PR6a is not the origin. But PR6a puts a new instance on the one command whose exit code is a contract, and the author already used ASCII `->` for the adjacent new line at [cli.py:273](../../src/lds_study/cli.py#L273) (`Summary -> …`), so the inconsistency is within the new code itself.

**Remediation:** Use `->` in `render_comparison_console` to match [cli.py:273](../../src/lds_study/cli.py#L273). Repo-wide, construct the console as `Console(legacy_windows=False)` with a UTF-8-safe writer, or reconfigure stdout once at CLI entry. Add a test that renders through a `Console(file=…)` backed by a cp1252 stream.

### 2. Rich markup swallows the model name from every per-model comparison line. *(High)*

`render_comparison_console` formats the label as `f"{d.name}[{d.model}]"` ([compare.py:384](../../src/lds_study/eval/compare.py#L384)) and the CLI prints it with `console.print`, which parses `[...]` as markup. The model name is consumed and never reaches the terminal:

```
model='m'                     raw:  citation_validity[m]: 0.9500 -> 0.7000 (-0.2500) [REGRESSED]
                         rendered:  citation_validity: 0.9500 -> 0.7000 (-0.2500) [REGRESSED]
model='qwen2.5:7b-instruct'   raw:  citation_validity[qwen2.5:7b-instruct]: …
                         rendered:  citation_validity: …
```

For a single-model run this is cosmetic. For the multi-model comparison this PR exists to enable, a two-model run prints eight rows in which `citation_validity`, `invalid_marker_rate`, `coverage_fail_rate` and `adversarial_refusal` each appear twice with different numbers and no way to tell which model produced which. That is the exact output a human reads to answer "did this run regress?", and it is ambiguous by construction.

It also behaves inconsistently, which makes it harder to notice: `[REGRESSED]` survives while `[m]` does not, and a model named after a real rich style changes the formatting instead of vanishing — with `model="bold"` the remainder of the line renders bold. Confirmed with `force_terminal=True`; no exception in any case tested, including `hf.co/u/mdl`.

The markdown report is unaffected — it carries `model` as its own table column and is written with `write_text`, no rich involved. Verified in a rendered report.

**Remediation:** `console.print(line, markup=False)` at [cli.py:278](../../src/lds_study/cli.py#L278), or emit `f"{d.name} ({d.model})"`. Add a rendering test that asserts the model name survives to the console for a two-model comparison.

### 3. Restricted question text still reaches the committed markdown report. *(High — pre-existing, but it makes rounds 1–3's boundary conclusion wrong)*

Round 1 found `first_error` leaking restricted golden-local question text into `*.summary.json`; it was fixed via the `SUMMARY_AGGREGATE_KEYS` projection, whose own comment reads *"Intentionally omits `first_error` (unbounded free text that can echo restricted question content)"*. The identical string is still rendered into the markdown report at `main:report.py:155`, and `outputs/eval/**/*.md` has been on the commit allowlist since `a4537f8` (PR1).

Same repro as round 1, now checking both artifacts:

```
SECRET in *.summary.json : False
SECRET in *.md (COMMITTED): True
   >> \* First error message(s): `mock-a`: upstream 400: prompt was RESTRICTED_LOCAL_QUESTION_TEXT_NEVER_COMMIT
```

`check_staged_data.py` cannot catch it — it matches filenames, not content, so an `.md` is waved through by construction.

This is **not** in PR6a's diff; the rendering predates the branch. I am reporting it because the plan calls the summary schema *"a copyright boundary"* and names leakage *"highest-severity risk"*, and because the round 2 test comments the exposure in as acceptable — [test_pr6_iterate.py:238](../../tests/test_pr6_iterate.py#L238): *"Markdown may still show first_error for local debugging; summary must not."* The markdown is not local; it is the more visible of the two committed artifacts. Closing the boundary on the JSON while documenting it as open on the sibling `.md` is the false-confidence pattern this review is supposed to catch, and my own round 3 verdict repeated it.

**Remediation:** Out of PR6a scope to fix here, but it should not merge as a documented non-issue. Either render only `type(exc).__name__` plus a count in the markdown, or drop the "First error message(s)" line and keep full text in the gitignored `*.json` sidecar where it already lives. If it is deferred, file it against PR6d — that PR already owns `check_eval_reports.py` and the copyright guards — and correct the round 2 test comment so it does not read as a considered clearance.

### 4. Nothing in the test suite executes the CLI. *(Medium)*

All 93 tests call `run_eval()` and the `compare`/`report` helpers directly. Findings 1 and 2 both live strictly between `run_eval`'s return and the process exit — argument marshalling, rich rendering, exit-code selection — and neither is reachable by any current test. That is why four rounds of eval passed over them.

`typer.testing.CliRunner` with a stubbed `run_eval` is enough to cover it offline; that is precisely how I found both, in about fifteen lines. It needs no GPU, no Ollama, no index, so it satisfies the plan's CI constraint.

**Remediation:** Add a small `CliRunner` test class: `--compare` reaches `run_eval`; a KEEP result exits 0 and a REVERT exits 1; the comparison block renders with the model name intact; and the whole thing survives a non-UTF-8 output stream.

### 5. Two sections now begin with `## Comparison`. *(Low)*

A rendered report contains both `## Comparison (generation)` (pre-existing, the per-model metrics table) and `## Comparison vs previous` (new, added here). PR6d's `check_eval_reports.py` has to parse this document section-by-section and *fail closed* on ambiguity, and a `startswith("## Comparison")` matcher — the obvious implementation — now hits the wrong one first. Cheap to avoid by renaming the new section (`## Trend vs previous`) while nothing depends on it yet; expensive once reports carrying the current heading are committed and the guard must accept both.

### 6. Stem de-duplication is TOCTOU. *(Trivial)*

[run.py:397-405](../../src/lds_study/eval/run.py#L397-L405) probes for existing artifacts and then writes. Two concurrent evals with the same stem both observe "free" and the second overwrites the first. Inherent to the pre-existing design, not worsened here, and unlikely on a single-GPU box where evals serialize anyway.

### 7. Carried: no committed summary yet; trend regression does not affect the exit code. *(Noted — no action)*

`git ls-files "outputs/eval/*.summary.json"` still returns 0 rows. And I confirmed the exit-code behavior empirically this round rather than by reading: a stubbed run with `regressed=True` and a KEEP verdict exits 0 (unredirected). Correct for PR6a — floors are the gate, the trend is reporting — and it becomes `lds iterate`'s exit 1 in PR6c.

## Net assessment

Findings 1 and 2 must be fixed before merge. Both are one-line changes in the code this PR adds, both break the feature on its primary surface, and both are invisible to a suite that never starts the CLI — so Finding 4 should land with them or they will regress unnoticed.

Finding 3 is not PR6a's to fix, but it should not merge with the current test comment blessing it. The minimum is an honest re-label and a tracked follow-up; the plan's own risk register calls this the highest-severity failure mode in the whole programme.

Finding 5 is worth thirty seconds now and is annoying later. Findings 6 and 7 need nothing.

The implementation work across four rounds has been genuinely good — every remediation moved the fix up a layer rather than patching the symptom, and the round 3 fix landed with a test that pins the exact behavior. What went wrong is my review method, not the code: three rounds of reading the same diff converged on agreement rather than coverage, and the first round that changed technique — run the thing, render the artifact — found three High findings in a tree I had called safe to merge. The lesson generalizes past this PR: reading a diff verifies what the author was thinking about, and executing the program is what finds what nobody was.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **93 passed in 7.67s** (86 → 89 → 92 → 93 across rounds)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- `python -m lds_study.cli eval --help` → `--compare` present, defaulted `auto`, help text renders
- **CLI wiring** (`CliRunner` + stubbed `run_eval`): `compare` kwarg arrives as `'outputs/eval/a.summary.json'`; full console block renders; regressed-trend + KEEP verdict → exit 0
- **Finding 1 repro**: `Console().print` of a delta line with stdout redirected → `stdout encoding = cp1252`, `UnicodeEncodeError: '→'`, exit 1; stubbed KEEP run through the real typer app with redirect → `EXIT=1` with the verdict never printed
- **Finding 2 repro**: `render_comparison_console` raw vs rendered for models `m`, `qwen2.5:7b-instruct`, `llama3.1:8b`, `bold`, `hf.co/u/mdl` — label stripped in every case; `bold` additionally restyles the line; no exception under `force_terminal=True`
- **Finding 3 repro**: generation-path failure with restricted text under `include_local=True` → `SECRET in *.summary.json: False`, `SECRET in *.md (COMMITTED): True`; confirmed pre-existing via `git show main:src/lds_study/eval/report.py` (line 155) and `git log -S` on `.gitignore` (allowlisted in `a4537f8`)
- **Full report render**: two chained generation runs, complete markdown read end to end — header `compare=outputs/eval/full-a.summary.json`, `## Keep-or-revert` with floors and a REVERT reason, `## Comparison vs previous` with per-model rows and `—` for shared recall, per-item table intact and free of question text
- **R3 Finding 1 regression check**: corrupt reference → `compare failed: summary is not an object: bad.summary.json` (filename only)
- Scanned `compare.py` and `cli.py` for non-cp1252-encodable characters in console-bound strings: `→` at [compare.py:394](../../src/lds_study/eval/compare.py#L394) (new) and cli.py 90/98/131/325 (pre-existing)
- Re-diffed `report.py` against `main` in full; confirmed the `First error message(s)` line is not among the additions

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index. Note that Finding 1 would surface there immediately — it needs only a redirect.*
