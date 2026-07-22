# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 9 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows rounds [1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md)–[8](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-8.md).*

## Verdict: Mergeable. Two Lows about the committed artifact as a *file*, not as data.

Round 8's finding is fixed thoroughly — a metric going value → `None` is now `regressed=True`, `error_n` joined the compared metrics at tolerance 0, and the verdict line reads *"regression(s) beyond tolerance (4 metric(s) became unmeasurable)"* with a dedicated test. **99 passed**, `ruff` clean.

Having exhausted the data-level angles, this round I looked at the summary as a file on disk that gets committed: bytes, determinism, and where it lands. Determinism is good — two identical runs produce summaries differing on exactly one line, `generated_at`. The two issues are that the new committed artifact is written with platform-dependent line endings in a repo with no `.gitattributes`, and that `--stem` accepts `../` and can place both artifacts entirely outside the directory every guard in this repo reasons about.

Neither blocks. Both are cheap, and both matter more to PR6d than to PR6a.

## Round 8 finding disposition

| # (R8) | Severity | Status | Evidence |
|---|---|---|---|
| 1 — vanished metric read as "no regression" | Medium | **Fixed** | value → `None` now yields `reg=True`; `error_n` added to `_PER_MODEL_METRIC_SPECS` at tolerance 0 ([compare.py:39](../../src/lds_study/eval/compare.py#L39), [:206](../../src/lds_study/eval/compare.py#L206)); verdict line now `**Trend:** regression(s) beyond tolerance (4 metric(s) became unmeasurable).` ([compare.py:424](../../src/lds_study/eval/compare.py#L424), [:430](../../src/lds_study/eval/compare.py#L430)); `test_diff_summaries_lost_metric_is_regressed` ([test_pr6_iterate.py:358](../../tests/test_pr6_iterate.py#L358)) |
| 2 | Noted | Unchanged, correctly | — |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema, boundary, allowlist** | Complete | Verified rounds 1–6 |
| **Step 1 — summary determinism** | Complete | Two identical runs differ on one line (`generated_at`) — clean git history, no float or key-order churn |
| **Step 1 — summary as a committed file** | **Partial** | Platform-dependent line endings — Finding 1 |
| **Step 4 — resolution, guards, deltas, rendering, CLI** | Complete | Verified rounds 3–8 |
| **Artifact placement** | **Partial** | `--stem` can write outside `outputs/eval/` — Finding 2 |
| **Step 10 — tests** | Complete | 99 pass |
| Steps 2, 3, 5–9 | Deferred-as-planned | — |

## Findings (ranked)

### 1. The new committed artifact is written with CRLF, and the repo has no `.gitattributes`. *(Low)*

`write_summary_json` and `write_markdown_report` both use `Path.write_text()`, which opens in text mode and applies `os.linesep` translation. On Windows:

```
summary.json  CRLF=49    bare-LF=0
report.md     CRLF=54    bare-LF=0
```

There is no `.gitattributes` in the repo, so normalization depends entirely on each contributor's local `core.autocrlf`. Demonstrated in a scratch repo committing the same CRLF file under each setting:

```
autocrlf=false -> committed blob contains CR: YES
autocrlf=input -> committed blob contains CR: no
autocrlf=true  -> committed blob contains CR: no
```

This machine is set to `true`, so the blobs committed here will be LF. But `false` is the default on Linux and macOS and in GitHub Actions `ubuntu-latest`, so the committed bytes for `outputs/eval/*.summary.json` are a function of who ran the eval, not of the content.

The `.md` writer predates this branch, so CRLF in reports is pre-existing. What is new is that PR6a adds a *second* committed artifact class with the same property and puts it on the allowlist.

Why it matters downstream rather than here: plan Step 7 has `check_eval_reports.py` diff old vs new report content and **fail closed** on any difference outside the `quality` column, and the plan's Verification section requires `configs/rag.yaml` to be *"byte-identical outside `eval.baselines`… verify with `git diff`, not by eye."* Both are byte-level expectations. If line endings flip between machines, every line of a report differs, the guard fails closed on a legitimate `quality` edit, and the likely workaround — normalizing before comparison — quietly weakens the check the plan wants to be strict.

**Remediation:** Add a `.gitattributes` with `outputs/eval/** text eol=lf` (or `* text=auto` plus that line), which fixes both artifact types and any future one. Alternatively pass `newline="\n"` to the writers. The `.gitattributes` route is preferable because it also normalizes what is already committed and does not depend on every writer remembering.

### 2. `--stem` is not validated and can place artifacts outside `outputs/eval/`. *(Low)*

`report_paths()` interpolates the stem directly into a path ([report.py:53-64](../../src/lds_study/eval/report.py#L53-L64)) with no check for separators or `..`:

```
md   -> …\outputs\eval\..\..\escaped.md
summ -> …\outputs\eval\..\..\escaped.summary.json
resolved: …\escaped.summary.json          # repo root
inside outputs/eval? False
```

The artifacts land at the repo root, which puts them outside every perimeter this repo has:

- `.gitignore` ignores `outputs/**`; a file at the root is not ignored at all, so it shows up as an ordinary untracked file that `git add -A` will stage.
- `check_staged_data.py` monitors only `data/ indexes/ models/ outputs/ private/ adapters/`, so the root is unmonitored. Confirmed: `python scripts/check_staged_data.py --paths escaped.summary.json` → `OK — 1 path(s) checked`, exit 0.

**Deliberately not overstating this.** `--stem` is a flag the repo owner types on their own machine; there is no untrusted input and no injection vector. The content is aggregates-only by construction — the `SUMMARY_AGGREGATE_KEYS` projection holds regardless of where the file is written — so no restricted data escapes. The realistic failure is a typo containing a slash silently writing somewhere unexpected, and the `-2` dedup not protecting across directories.

It is worth a line anyway because PR6d's guards are being built on the assumption that report/summary pairs live under `outputs/eval/`, and because the fix is trivial.

**Remediation:** Reject a stem containing a path separator or `..` in `report_paths()` (or normalize with `Path(stem).name`), and add one test.

### 3. Carried notes. *(Noted — no action)*

TOCTOU stem dedup; no committed summary yet; trend regression not gating the exit code; four pre-existing U+2192 arrows in `prepare` / `index` / `finetune-dataset`. Unchanged, all correct for PR6a.

## Net assessment

Ship it. Neither finding affects correctness of measurement, comparison, or the copyright boundary — the three things that took rounds 1–8 to get right and that have been stable since. Both are file-hygiene items that cost minutes now and cause confusing failures later, and both land in territory PR6d will depend on, so the argument for doing them in this PR is sequencing rather than risk.

Returns are now clearly marginal, and I want to be straight about that rather than manufacture urgency. Rounds 7 and 8 each found something real by shifting to the default path; round 9 found two Lows by shifting from "the summary as data" to "the summary as a file." That third axis is now also spent. The axes I can still reach — more input fuzzing, more path edge cases — are the ones that produced round 6's opt-in edges, the least valuable findings of the series. The axis I cannot reach remains the same one named in every report since round 3: the plan's local verification block against a real index with Ollama, where a broken generator, a stale index, and a genuine multi-model quality regression would actually originate.

If there is a round 10, the honest recommendation is that it not be a review. It should be that local run.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **99 passed in 7.72s** (86 → 89 → 92 → 93 → 94+1F → 95 → 97 → 98 → 99)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- **R8 regression check**: value → `None` on four metrics plus `error_n` 0 → 50 now yields `any_regressed: True`, per-metric `reg=True`, and `**Trend:** regression(s) beyond tolerance (4 metric(s) became unmeasurable).`; `error_n` present in `_PER_MODEL_METRIC_SPECS` and pinned at tolerance 0
- **Determinism** (new): two identical `run_eval` invocations → summaries differ on exactly one line, `generated_at`; no float-repr or key-order churn
- **Finding 1 repro**: `summary.json CRLF=49 bare-LF=0`, `report.md CRLF=54 bare-LF=0`; scratch repo committing an identical CRLF file under `core.autocrlf` `false` / `input` / `true` → CR preserved only under `false`; `ls .gitattributes` → absent; `git config core.autocrlf` → `true` on this machine
- **Finding 2 repro**: `run_eval(stem="../../escaped")` → artifacts resolve to the repo root, `inside outputs/eval? False`; `check_staged_data.py --paths escaped.summary.json` → exit 0 (unmonitored); `MONITORED_PREFIXES` confirmed to exclude the root
- Read `report_paths`, `MONITORED_PREFIXES`, `DENYLIST_PATTERNS`, `ALLOWLIST_PATTERNS` to confirm the perimeter gap

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index — see the recommendation above.*
