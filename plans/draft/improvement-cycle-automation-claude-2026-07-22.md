# Automating the RAG improvement cycle

*Author: claude · 2026-07-22*
*Revised 2026-07-22 after Phase B evaluation
([report](improvement-cycle-automation-plan-evaluation-2026-07-22.md), 3/3 execute
this plan). Folds the steal list, the five blocking items, and the pre-execute
checklist. Changes are marked **[eval]** where they alter a prior decision.*

## Goal

Turn [docs/IMPROVEMENT_CYCLE.md](../../docs/IMPROVEMENT_CYCLE.md) from a
human-followed checklist into executable commands, so that one iteration of
*diagnose → change one knob → re-index if needed → measure → compare → keep or
revert* costs a single command and cannot be done wrong by accident.

Success looks like:

- `lds status` answers "do I need to re-prepare/re-index?" instead of the
  human reading a decision table.
- `lds iterate` runs staleness check → eval → compare-to-last-committed →
  keep/revert verdict, and exits non-zero on regression.
- Promoting new baselines into `configs/rag.yaml` and refreshing the
  `MODEL_CARD.md` link is a flag, not a copy-paste ritual.
- The "What not to do" list in the doc is enforced by hooks, not by memory.
- The doc shrinks to *why* + the symptom→knob table; the *how* lives in code.

## Constraints

- **GPU/Ollama-bound.** `lds eval` needs a built index, a local embedder, and
  Ollama models. CI (`.github/workflows/ci.yml`) is `ubuntu-latest` CPU-only and
  installs no models. Full eval **cannot** run in GitHub Actions — all eval
  automation must be local-first, with CI limited to offline unit tests.
- **JSON sidecars are gitignored.** `.gitignore` allowlists only
  `outputs/eval/**/*.md`. There is therefore **no committed machine-readable
  history** to diff against today. This is the blocking constraint for
  automated comparison and must be solved first (Step 1).
- **`configs/rag.yaml` is comment-load-bearing.** The `min_score: 0.05` and
  `min_coverage: 0.8` blocks carry the calibration rationale. Any programmatic
  write-back must round-trip comments (`ruamel.yaml`), not `yaml.safe_dump`.
  `Settings.load_yaml` (`src/lds_study/config.py:62`) is read-only today.
- **Baselines must stay harness-emitted.** Automation may only write the exact
  `suggested_baselines()` output (`src/lds_study/eval/metrics.py:177`, 90% of
  best observed). No smoothing, no clamping, no hand-tuned floors.
- **[eval] `prepare_stats.json` carries no provenance today.** Verified on disk:
  it holds `sources[]` (id, chunk_count, empty_dropped, token stats),
  `total_chunks`, `empty_dropped_total`, `exportable_chunks` — no hashes, no
  mtimes, no timestamp, no `sources.yaml` fingerprint. Any `prepare` staleness
  check is aspirational until Step 2 adds them.
- **[eval] Stage ordering is a hard dependency, not a preference.** A `chunking:`
  change invalidates `chunks.jsonl`, so `prepare` must precede `index`. An
  embedder change invalidates existing vectors, and `run_index()` resumes by
  default — it must be `lds index --rebuild`, or stale embeddings survive
  silently. Automation that re-indexes without honoring this produces a
  corrupt-but-green index.
- **[eval] The manual quality column is a legitimate post-hoc edit.** Reports are
  written with the 1–5 column blank for human scoring
  (`src/lds_study/eval/report.py:101`), so "never modify a committed report"
  cannot be enforced as a whole-file rule.
- **Copyright gates stay hard.** No automation may stage `data/`, `indexes/`,
  `models/`, or `eval/golden.local.yaml`. `scripts/check_staged_data.py` remains
  authoritative.
- Non-destructive by default: `--promote-baselines` and any config write must be
  opt-in and refuse to run on a dirty working tree.
- Windows/PowerShell is the primary dev surface; keep entry points cross-platform
  Python where possible.

## Approach

**Chosen: extend the existing `lds` CLI with three new commands plus flags, and
back them with a committed machine-readable eval summary.**

The harness already computes everything needed for a verdict — aggregates,
`suggested_baselines()`, `meets_regression_baselines()`, `suggest_min_score()`,
`coverage_stats()`, and a non-zero exit on REVERT (`src/lds_study/cli.py:270-280`).
What is missing is not measurement but *plumbing*: persistence of a comparable
history, staleness detection, and config write-back. So the work is mostly
connective, and each piece is independently useful.

Rejected alternatives:

- **Parse the committed markdown reports to get history.** Avoids a gitignore
  change, but couples automation to `write_markdown_report()` table formatting
  and breaks silently on any layout edit. Rejected in favor of an explicit,
  versioned summary artifact.
- **Commit the full JSON sidecar.** Simplest, but sidecars embed per-item rows
  including question text from `golden.local.yaml` when `--include-local` is on —
  a copyright leak. Rejected. The summary artifact must be aggregates-only and
  scrubbed of local-source content.
- **Do it all in CI.** Impossible for the eval leg (no GPU/Ollama). CI keeps its
  current role: ruff, pytest, copyright allowlist, plus new baseline-integrity
  checks that are pure-CPU.
- **A shell/PowerShell wrapper script instead of CLI commands.** Faster to write,
  but untestable by pytest and duplicates argument parsing. Rejected except as a
  thin optional scheduled-task shim (Step 8).
- **[eval] An auto-experiment mode that patches `configs/rag.yaml` and
  `prompts/*.md` from a snapshot and restores on regression** (the competing
  plan's `cycle experiment`). Unanimously rejected by the evaluation: a crash or
  concurrent run leaves a half-applied config or a dirty tree, and it moves the
  system from *measure and gate* into *change things on its own* — the one
  boundary this repo's design depends on. Explicitly deferred, see Out of scope.

**[eval] Open question — command naming.** One evaluator preferred a single
`lds cycle {status,run,promote}` namespace over top-level `lds status` /
`lds iterate`. Not blocking and not a consensus view; decide before PR6b lands
the first new command. If renamed, do it before any of these commands are
documented in `docs/IMPROVEMENT_CYCLE.md` (Step 9) so no alias needs
maintaining.

## Automation inventory

The core deliverable. Each row of the current doc, classified.

| Doc section / step | Today | Verdict | Where handled |
|---|---|---|---|
| "Steady state vs refresh" table | Human reads table | **Automatable** | Step 3 `lds status` |
| 1. Diagnose (symptom) | Human judgment | **Partial** — surface candidate knobs from metrics; the call stays human | Step 6 hints |
| 2. Change one knob | Human edits config/prompt | **Not automatable** (design decision) | — |
| 3. Re-index if needed | Human decides | **Automatable** — incl. correct stage order | Steps 2–3 (`remediation_plan()`) |
| 4. Measure (`lds eval`) | Already a command | **Done** | existing |
| 5. Compare vs last report | Human eyeballs two markdown files | **Automatable** | Steps 1, 4 |
| 6. Keep or revert | `--check-baselines` exit code, console-only | **Mostly done**; persist the verdict (Step 1); revert action stays manual git | Steps 1, 6 |
| Baselines: copy YAML block verbatim | Manual copy-paste | **Automatable** | Step 5 |
| Baselines: commit report | Manual | **Automatable** (assisted) | Step 5 |
| Baselines: update MODEL_CARD link | Manual | **Automatable** | Step 5 |
| "What not to do" (4 bullets) | Human discipline | **Automatable as guards** | Step 7 |
| Manual quality column (1–5) | Blank for human | **Not automatable** | — |
| Optional QLoRA keep/revert | `--check-baselines` | **Done**; tone judgment human | existing |

### What cannot be automated (and why)

1. **Choosing which knob to turn.** The symptom→knob table encodes causal
   judgment ("invented citations → prompts, not `top_k`"). Automation can rank
   candidates from metrics, but picking and editing is a design decision.
2. **Manual quality scoring (1–5).** `write_markdown_report()` deliberately
   leaves this column blank (`src/lds_study/eval/report.py:101`). Whether an
   answer is *pastorally useful* has no metric in this repo. An LLM-judge would
   be new scope and a new failure mode.
3. **"Raise `min_coverage` only with evidence."** The gate exists precisely to
   stop a metric from being moved to make itself pass. Any automation that
   raises a *threshold* to clear a failure inverts the control. Only
   `eval.baselines` (harness-emitted floors) may be written automatically —
   never `citation.min_coverage`, `retrieval.min_score`, or `final_top_k`.
   `suggest_min_score()` may *print* a suggestion; a human applies it.
4. **Prompt rewrites** (`prompts/*.md`). Wording changes for refusal or citation
   behavior are authorship, not parameter search.
5. **License verification.** `assert_source_ingestible()` requires a human to
   set `verified_on` in `configs/sources.yaml` after checking `license_url`
   (`src/lds_study/data/manifest.py:33`). Deliberately unautomatable.
6. **Authoring golden questions and `gold_chunk_ids`.** Labeling ground truth is
   the ground truth. Also, `eval/golden.local.yaml` is gitignored BYOF content.
7. **Whether a QLoRA adapter's tone is better.** Floors only prove it is not
   *worse* on groundedness/refusal. Style preference is human.
8. **Full eval in CI.** GPU + Ollama + a built index; the index is gitignored
   and ~42k chunks. Local-only, permanently.
9. **The revert itself.** `lds iterate` returns REVERT; `git restore` /
   `git revert` stays a human action so intent is recorded.

## Implementation

### 1. Committed machine-readable eval summary

Unblocks all comparison work.

- Add `write_summary_json()` to `src/lds_study/eval/report.py`, writing
  `outputs/eval/{stem}.summary.json`. Schema v1, **aggregates-only**:
  `schema_version`, `generated_at`, `profile`, `k`, `models`, `retrieval_only`,
  `include_local`, `source_counts`, `golden_hash`, `golden_local_hash`,
  `recall_shared`, per-model aggregate dicts, `suggested_baselines`,
  `suggested_min_score`, `coverage_stats`, plus a new `config_fingerprint`
  (see Step 2).
- **[eval — steal, 3/3] Persist the gate result, not just the metrics.** Add
  `baselines_checked` (the floors actually compared against) and
  `baseline_verdicts` (`{model: {keep: bool, failures: [str]}}`) to both the
  summary and the markdown report. `EvalResult` already carries both fields
  (`src/lds_study/eval/run.py:65-66`) but they are printed to console and then
  discarded — so a committed report cannot today answer "was this run a KEEP,
  and against which floors?". Render them as a "## Keep-or-revert" section in
  `write_markdown_report()`. This also gives Step 5's anti-regression gate and
  Step 7's integrity checker a durable record to read.
- Also record `buckets` and `limit` in the summary — Step 4 needs them to detect
  a narrowed run, and Step 5 must refuse to promote from one.
- **No `items` array** — that is where restricted BYOF question text lives. Add
  an explicit unit test asserting no per-item payload and no free text fields.
- Call it from `run_eval()` alongside the existing writers
  (`src/lds_study/eval/run.py:378-411`); add `summary_path` to `EvalResult`.
- `.gitignore`: add `!outputs/eval/**/*.summary.json` after the existing
  `*.md` allowlist line.
- Extend `scripts/check_staged_data.py` to allow `*.summary.json` under
  `outputs/eval/` while continuing to reject the full `*.json` sidecar.

*Done when:* an eval run produces a committable `*.summary.json`; the full
`*.json` sidecar is still refused by the copyright check; a test asserts the
summary contains no question text.

### 2. Build fingerprints into the index manifest **and prepare stats**

Today `index_manifest.json` records `profile`, `chunk_count`, `dense_count`,
`chunks_path`, `embedder`, and three `rag` top-k values — not enough to detect
staleness. `prepare_stats.json` records no provenance at all.

- Add `src/lds_study/index/fingerprint.py` with
  `config_fingerprint(rag_cfg, models_cfg) -> dict[str, str]` returning stable
  per-section hashes (`chunking`, `retrieval`, `citation`, `embeddings`) so
  prepare, index, and eval all record the same shape. Hash canonicalized YAML
  (sorted keys, comments stripped) so a comment edit is not a false positive.
- In `src/lds_study/index/build.py` (manifest write, ~line 129) add:
  `chunks_sha256` (hash of `data/processed/chunks.jsonl`),
  `chunking_fingerprint`, `embedder_fingerprint` (model id + resolved local
  revision from `src/lds_study/index/model_paths.py`), `built_at`,
  `schema_version`. **[eval — nit]** Drop the previously proposed `chunks_mtime`:
  `chunks_sha256` is authoritative and mtime only invites disagreement between
  the two.
- **[eval — blocking] Extend `prepare_stats.json`** so Step 3's prepare check is
  real. In `src/lds_study/data/prepare.py` (report dict, ~line 91) add:
  `schema_version`, `prepared_at`, `sources_yaml_sha256`,
  `chunking_fingerprint`, `chunks_sha256`, and per-source
  `input_files: [{path, sha256, size}]` for everything actually ingested under
  `data/raw/`. Hashing 42k chunks plus raw inputs is a few seconds and runs once
  per prepare — acceptable. Paths must be stored repo-relative; the existing
  absolute `chunks_path` in `index_manifest.json` is already a portability wart,
  do not repeat it.
- Keep reading old artifacts: missing fields mean "unknown", which Step 3 must
  report as *unknown*, never as *fresh*.

*Done when:* `lds index` and `lds prepare` both write the new fields; a manifest
or stats file lacking them is handled without crashing; editing a comment in
`configs/rag.yaml` does not change any fingerprint.

### 3. `lds status` — replaces the refresh decision table

New command in `src/lds_study/cli.py`, logic in
`src/lds_study/index/staleness.py`.

Compares on-disk state against the manifest and prints a table with a verdict
per stage:

| Check | Compares | Verdict |
|---|---|---|
| `prepare` | `data/raw/**` file hashes + `sources_yaml_sha256` + `chunking_fingerprint` vs `prepare_stats.json` (Step 2 fields) | `stale` → `lds prepare` |
| `index` | `chunks_sha256` + `chunking_fingerprint` + `embedder_fingerprint` vs `index_manifest.json` | `stale` → `lds index` (or `--rebuild`, below) |
| `eval` | `retrieval`/`citation` fingerprints + `golden_hash` vs newest `*.summary.json` | `stale` → `lds eval` |
| `baselines` | `configs/rag.yaml eval.baselines` vs the summary named in its provenance stamp | `drifted` / `hand-edited` |

**[eval — blocking] Emit an ordered remediation plan, not just per-stage flags.**
Staleness cascades and the required command depends on *which* fingerprint
changed. `lds status` must compute and print the exact ordered command list:

| What changed | Correct remediation (in order) |
|---|---|
| Raw files / `sources.yaml` | `lds prepare` → `lds index` |
| `chunking.*` | `lds prepare` → `lds index --rebuild` |
| Embedder id or revision | `lds index --rebuild` (never plain `index` — `run_index()` resumes and would keep old vectors) |
| `retrieval.*` / `citation.*` only | `lds eval` (no re-index; matches the doc's config-only row) |
| `golden.yaml` | `lds eval` |

Implement as `remediation_plan(state) -> list[str]` in
`src/lds_study/index/staleness.py`, unit-tested per row — this function is the
single source of truth that Step 6 consumes, so the ordering rule is written
once.

Flags: `--profile`, `--json` (machine-readable for the wrapper), `--exit-code`
(non-zero if anything is stale, for scripting).

*Done when:* touching a file under `data/raw/` flips `prepare` to stale; editing
`retrieval.final_top_k` flips `eval` (not `index`) to stale; editing
`chunking.prose_tokens` flips both `prepare` and `index` to stale and yields
`prepare → index --rebuild`; changing the embedder id yields a plan containing
`--rebuild`.

### 4. `lds eval --compare` — automated regression diff

- Add `--compare <path|auto|none>` to `eval_cmd` (`src/lds_study/cli.py:189`),
  default `auto`.
- **[eval] Resolve `auto` git-aware, not by directory listing.** "Newest
  committed summary" must mean *tracked in git*, not *newest mtime in
  `outputs/eval/`* — the directory also holds untracked local runs, and picking
  one silently makes the diff unreproducible for anyone else. Resolution order:
  1. explicit `--compare <path>`;
  2. **[eval — steal, 1/3]** `eval.reference_report` in `configs/rag.yaml`, if
     set — an explicitly blessed reference (also what Step 5's anti-regression
     gate compares against);
  3. newest summary that `git ls-files` reports as tracked, excluding this run's
     own output.
  Print which one was chosen and why. If none resolves, report *no reference*
  and continue — never fall back to an untracked file.
- Add `src/lds_study/eval/compare.py` with
  `diff_summaries(prev, curr) -> ComparisonResult`, producing per-metric deltas
  (recall@k, citation validity, invalid-marker rate, coverage fail, adversarial
  refusal) with direction and a `regressed` flag.
- **[eval] Apply a noise tolerance to trend verdicts.** Generation metrics are
  stochastic; on a ~50-question golden set a single flipped item moves a rate by
  ~2 points. Mark a metric `regressed` only when it drops by more than
  `eval.trend_tolerance` (new key in `configs/rag.yaml`, default `0.02`), and
  always print the raw delta alongside the verdict. Recall on a fixed index at
  `--retrieval-only` is deterministic — tolerance `0` applies there. This
  tolerance is for *trend reporting only*; the `--check-baselines` floors are
  exact and get no tolerance.
- Render a "## Comparison vs previous" section into the markdown report via a new
  `comparison=` kwarg on `write_markdown_report()`, and print the delta table to
  console.
- Guard mismatched runs: if `golden_hash`, `k`, `profile`, `include_local`,
  `retrieval_only`, `buckets`, or `limit` differ, mark the diff **not
  comparable** and say which field differs rather than printing misleading
  deltas.
- `--check-baselines` semantics unchanged (floors from config). `--compare` is
  the *trend*; floors are the *gate*. Both must pass for KEEP.

*Done when:* two consecutive runs produce a delta table; a run against a
different `golden_hash` refuses to diff with a clear reason; an untracked
summary is never auto-selected; a 1-point drop is reported but not flagged as a
regression.

### 5. `lds eval --promote-baselines` — replaces the copy-paste ritual

Automates the three-step "Baselines" section of the doc.

- New flag on `eval_cmd`. Preconditions, all enforced:
  1. Working tree clean for `configs/rag.yaml` and `MODEL_CARD.md`
     (`git status --porcelain`); refuse otherwise.
  2. This run must be a full run — refuse when `--retrieval-only`,
     `--limit`, or `--buckets` narrowed the set.
  3. `--check-baselines` verdict must be KEEP for every model.
  4. Refuse if `include_local` is true **and** the summary would gate public
     baselines on restricted questions — require `--no-local` for promotion.
  5. **[eval — blocking] Comparable to the reference, and no regression against
     it.** KEEP alone is not sufficient: a run can clear the floors while sitting
     well below the previous best, and promoting it writes *lower* floors —
     ratcheting the gate down and permanently hiding the regression. Require
     that the run is comparable to the Step 4 reference (same `golden_hash`, `k`,
     `profile`, run shape) and that no gated metric regressed beyond
     `eval.trend_tolerance`. Refuse with the offending metric named. Override is
     `--force-promote`, which additionally requires `--reason "<text>"` and
     stamps that reason into the provenance comment — so a deliberate floor
     reduction is possible but never silent, and is discoverable in `git blame`.
- **[eval — steal, 3/3] `--dry-run` is the default posture.** Add
  `--promote-baselines --dry-run` which runs every precondition, renders the
  exact unified diff it *would* apply to `configs/rag.yaml` and `MODEL_CARD.md`,
  and writes nothing. Given the ratchet risk, print the diff on the real path
  too and require `--yes` to skip the confirmation prompt in interactive use
  (`--yes` is implied when stdin is not a TTY, so `lds iterate --promote` stays
  scriptable).
- Add `src/lds_study/eval/promote.py`:
  - Write `suggested_baselines` verbatim into `configs/rag.yaml` →
    `eval.baselines` using `ruamel.yaml` round-trip so the calibration comments
    survive. Add `ruamel.yaml` to `pyproject.toml` dependencies.
  - Stamp a provenance comment above the block: source report stem, summary
    filename, golden hash, UTC date, and `--reason` when `--force-promote` was
    used. This comment is what Step 7's integrity checker reads, so treat its
    format as an interface and parse it with one shared helper.
  - Optionally set `eval.reference_report` to the promoted stem, so the blessed
    comparison target advances with the floors.
  - Rewrite the `MODEL_CARD.md` "Latest comparison" line to point at the new
    `outputs/eval/{stem}.md`.
- Print the exact `git add` command for the report + summary + config; **do not
  commit** (see "Out of scope").

*Done when:* `--dry-run` shows a diff and leaves the tree untouched; promotion
updates both files, preserves every existing comment in `rag.yaml`, and refuses
on a dirty tree, a narrowed run, an incomparable reference, or a regression
against it.

### 6. `lds iterate` — the one-command loop

Wrapper implementing the doc's "One iteration" block:

```text
lds status → (warn/abort if stale) → lds eval → compare → check-baselines → verdict
```

- New command in `src/lds_study/cli.py`, orchestration in
  `src/lds_study/eval/iterate.py`.
- Flags: `--profile`, `--models`, `--buckets`, `--retrieval-only`, `--stem`,
  `--auto-refresh` (see below; default off), `--promote` (chain Step 5 on KEEP).
- **[eval — steal, 3/3] `check_env.py` preflight first.** Call
  `scripts.check_env.main()` (importable — `scripts/__init__.py` exists; returns
  an int, supports `--allow-cpu`) before doing any work, and print its summary.
  **Warn-only**: a failing GPU check must not block `--retrieval-only` or a CPU
  box, but "eval was mysteriously slow / OOM" is almost always this. Surface it,
  don't gate on it.
- **[eval — blocking] `--auto-index` is renamed `--auto-refresh` and delegates
  to the Step 3 remediation plan.** The original sketch ("run `lds index` when
  stale") is unsafe in two ways: a `chunking:` change needs `prepare` to run
  first, and an embedder change needs `index --rebuild` or the resume path keeps
  the old vectors. `--auto-refresh` therefore executes
  `remediation_plan(state)` in order — never a hardcoded `lds index` — printing
  each command before running it, and aborting the whole iteration if any stage
  exits non-zero. It stays **off by default**: re-embedding 42k chunks is a
  long GPU job that should not start as a side effect of asking for a
  measurement. With it off, staleness is reported and the run exits 2.
- Exit codes: `0` KEEP, `1` REVERT, `2` stale prerequisites (nothing measured),
  `3` not comparable.
- **[eval] Document the exit-2 difference from `lds eval`.** Plain `lds eval`
  always runs regardless of staleness; `lds iterate` refuses and exits 2. That is
  the intended contract — the loop's value is not measuring a stale index — but
  any existing script that swaps one for the other will see a new failure mode.
  State this in `docs/IMPROVEMENT_CYCLE.md` (Step 9) and in `--help`. Use
  `lds iterate --auto-refresh` or plain `lds eval` to opt out of the check.
- On REVERT, print the failing metrics **and** the diagnose hints: map each
  failing metric to its knobs from the symptom→knob table, held in one dict in
  `src/lds_study/eval/iterate.py` so the doc table and the code cannot drift.
  This is a hint list, not an action.

*Done when:* a single `lds iterate --retrieval-only --no-local` on a clean repo
prints staleness, metrics, deltas, and a KEEP/REVERT verdict with matching exit
code.

### 7. Guardrails — enforce "What not to do"

| Doc rule | Enforcement |
|---|---|
| Don't commit `data/`, `indexes/`, model weights | Already in `scripts/check_staged_data.py` — add a regression test |
| Don't force-stage `eval/golden.local.yaml` | Already covered — add explicit test case |
| Don't edit numbers in an old eval report | New `scripts/check_eval_reports.py`, **field-scoped** (below) |
| Don't hand-edit baselines | Same script: `configs/rag.yaml eval.baselines` must byte-match `suggested_baselines` in the summary named by its provenance stamp |

**[eval — blocking] The report guard must be field-scoped, not whole-file.** The
manual quality column is *designed* to be filled in after the fact
(`src/lds_study/eval/report.py:101`), so "any modified file under
`outputs/eval/` fails" would block the one post-hoc edit the workflow requires.
Instead, for each modified report, `check_eval_reports.py` diffs the old and new
content and allows the change **only if** every difference is confined to the
`quality` column of a per-item row:

- Parse both versions' per-item tables; compare row-by-row on all columns except
  `quality`. Any difference elsewhere — a metric cell, the comparison table, the
  suggested-baselines block, the header, row count, row order — fails.
- New values in `quality` must be empty or `1`–`5`.
- Reject changes to the corresponding `*.summary.json` outright; it has no
  human-editable field, so it is genuinely immutable once committed.

This is the one piece of parsing this plan accepts against the markdown layout,
so keep it tolerant: on a parse failure, fail closed with "cannot verify — report
format changed; update `check_eval_reports.py`" rather than silently passing.

**[eval — blocking] Bootstrap ships in this same PR.** The current floors in
`configs/rag.yaml` predate summaries, so the checker fails on day one unless
provenance exists. Do **both**, in PR6d (the same PR as the checker):

1. Backfill `outputs/eval/2026-07-21-r2.summary.json` from the existing
   gitignored `outputs/eval/2026-07-21-r2.json` sidecar via a one-shot
   `scripts/backfill_summary.py`, running it through the same aggregates-only
   writer from Step 1 so no per-item text can leak. Verify by hand that the
   backfilled `suggested_baselines` matches the three floors currently in
   `configs/rag.yaml` (`0.711` / `0.9` / `0.825`) — if they do not match, stop:
   that means the committed floors were not harness-emitted, which is itself a
   finding worth recording before automating on top of it.
2. Accept a `# baseline-provenance: legacy` marker in the provenance comment as
   a permanent escape hatch for pre-automation floors. The checker passes it
   with a warning. Needed regardless of (1), because `outputs/eval/*.json` is
   gitignored and any fresh clone lacks the sidecar to backfill from.

- Wire into `.pre-commit-config.yaml` as a second local hook and add a CI step in
  `.github/workflows/ci.yml` after the copyright check. Both are pure-CPU and
  need no models, so they run in Actions.

*Done when:* editing a metric cell in `outputs/eval/2026-07-21-r2.md` fails
pre-commit; filling its `quality` column with `4` passes; editing
`min_recall_at_k` by hand fails CI; a clean clone passes CI with the backfilled
summary present.

### 8. Local scheduled full eval (optional)

Since CI cannot run eval, add `scripts/nightly_eval.ps1`:
`lds status --json` → if anything stale, exit; else
`lds iterate --no-local --stem nightly-{date}` → write outcome to
`outputs/eval/` and exit non-zero on REVERT. Document registering it as a
Windows scheduled task in `docs/IMPROVEMENT_CYCLE.md`. Thin shim only — all
logic stays in the CLI.

### 9. Rewrite `docs/IMPROVEMENT_CYCLE.md`

Once Steps 1–7 land the doc keeps *why* and drops *how*:

- Keep: Goal, the symptom→knob table, "What not to do" (annotated with which
  guard enforces each), Optional QLoRA, the "cannot be automated" list above.
- Replace: "Steady state vs refresh" → `lds status`. "One iteration" 6 steps →
  `lds iterate`. "Commands (PowerShell)" → shortened; keep the raw `lds eval`
  forms as an escape hatch. "Baselines" 3 manual steps → `--promote-baselines`.
- Add: exit-code table, and a pointer that the symptom→knob mapping is mirrored
  in `src/lds_study/eval/iterate.py`.

### 10. Tests

New `tests/test_pr6_iterate.py`, following the offline pattern of
`tests/test_pr4_eval.py` (no GPU, no Ollama, no network):

- `write_summary_json()` round-trip; asserts no per-item payload **and** that
  `baseline_verdicts` / `baselines_checked` survive to both summary and markdown.
- **[eval]** Copyright regression test: build a summary from a run with
  `include_local=True` and assert no golden-local question text appears anywhere
  in the serialized output. This is the schema's license boundary — test it
  directly, not by inspection.
- `diff_summaries()`: improvement, regression, not-comparable (one case per
  guarded field), and a sub-tolerance drop that reports but does not flag.
- Staleness: fixture manifests and stats files (fresh / stale chunks / stale
  chunking config / stale embedder / legacy artifacts missing fields), plus
  `remediation_plan()` asserted per row of the Step 3 table — especially that an
  embedder change yields `--rebuild` and a chunking change yields
  `prepare` before `index`.
- **[eval]** Fingerprint stability: editing only a comment in `configs/rag.yaml`
  leaves every fingerprint unchanged.
- Promotion: **byte-stable** `ruamel.yaml` round-trip — assert the file is
  identical outside the `eval.baselines` block and its provenance comment, not
  merely that comments still exist; `--dry-run` writes nothing and returns the
  diff; refuses on dirty tree, `--retrieval-only`, narrowed buckets,
  `--include-local`, incomparable reference, and regression-vs-reference;
  `--force-promote` without `--reason` refuses.
- Guards: `check_eval_reports.py` **allows** a `quality` column fill (empty → `4`)
  and **rejects** a metric-cell edit, a suggested-baselines edit, a row
  reordering, a summary-json edit, and a hand-edited baseline; passes on a newly
  added report; fails closed on an unparseable report.
- `iterate` exit codes 0/1/2/3 with a stubbed retriever and generator, including
  exit 2 with `--auto-refresh` off and successful remediation with it on.

## PR split

**[eval] PR6a is deliberately thin** — evaluators flagged total scope (4 PRs +
nightly + hooks) as the main delivery risk. PR6a must be independently useful and
mergeable on its own; if it grows, split the fingerprints out rather than
widening it.

1. **PR6a — summaries + comparison:** Steps 1 and 4 + tests. Adds
   `*.summary.json` (with persisted verdicts), the gitignore allowlist, and
   `--compare`. No new commands, no config writes, no behavior change to existing
   commands. Ships value immediately: "did this run regress?" becomes answerable.
2. **PR6b — fingerprints + status:** Steps 2 and 3 + tests. Extends
   `index_manifest.json` and `prepare_stats.json`, adds `lds status` and
   `remediation_plan()`. Read-only.
3. **PR6c — the loop:** Step 6 (`lds iterate`) + tests. Depends on 6a and 6b;
   adds no new persistence of its own.
4. **PR6d — write-back and guards:** Steps 5, 7, 8 + tests, **including the
   baseline bootstrap** (backfilled summary + legacy marker) in this same PR —
   the checker cannot land without it. Highest risk; behind explicit flags.
5. **PR6e — docs:** Step 9. After the commands exist and have been used for at
   least one real iteration, so the doc describes observed behavior.

## Verification

Offline (CI-safe, must pass in Actions):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
ruff check src scripts tests
python scripts/check_staged_data.py --paths outputs/eval/2026-07-21-r2.md
python scripts/check_eval_reports.py --paths configs/rag.yaml
```

Local, with index + Ollama:

```powershell
# 1. Staleness reflects reality
.\.venv\Scripts\python.exe -m lds_study.cli status --profile default
#    then touch configs/rag.yaml chunking.prose_tokens -> index must go stale

# 2. Comparison works end-to-end (fast leg)
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default `
  --retrieval-only --no-local --stem verify-a
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default `
  --retrieval-only --no-local --stem verify-b --compare auto

# 3. One-command loop; exit code is the verdict
.\.venv\Scripts\python.exe -m lds_study.cli iterate --profile default `
  --retrieval-only --no-local --stem verify-iter
echo $LASTEXITCODE   # 0 KEEP / 1 REVERT / 2 stale / 3 not comparable

# 4. Promotion refuses unsafe input
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default `
  --retrieval-only --promote-baselines   # must refuse: narrowed run

# 5. Dry-run shows the diff and writes nothing
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default --no-local `
  --stem verify-promote --promote-baselines --dry-run
git diff --exit-code configs/rag.yaml MODEL_CARD.md   # must be clean
```

Invariants to spot-check:

- `configs/rag.yaml` after promotion: byte-identical outside `eval.baselines`
  and its provenance comment — verify with `git diff`, not by eye.
- No `outputs/eval/*.json` (non-summary) is ever stageable.
- No `*.summary.json` contains question text or `golden.local` content.
- `lds eval` without new flags behaves exactly as before (report path, exit
  codes, console output unchanged).
- **[eval]** Filling a `quality` cell in a committed report passes pre-commit;
  changing any metric cell in the same file fails it.
- **[eval]** With the embedder id changed, `lds status` proposes `--rebuild`;
  with `chunking.prose_tokens` changed, it proposes `prepare` before `index`.
- **[eval]** `--compare auto` never selects an untracked summary: create an
  untracked `outputs/eval/zz-local.summary.json` and confirm it is skipped.

## Risks

- **Summary artifact leaks restricted content.** Highest-severity risk: summaries
  are committed. Mitigated by aggregates-only schema, an explicit test, and the
  `--no-local` requirement for promotion — but any future field added to the
  summary must be re-reviewed. Treat the schema as a copyright boundary.
- **`ruamel.yaml` round-trip mangles `configs/rag.yaml`.** The comments are the
  calibration record. Mitigated by a byte-level comment-preservation test and a
  clean-tree precondition, so `git diff` is always reviewable before commit.
- **Automated comparison creates false confidence.** A green delta on a
  `--retrieval-only --buckets adversarial` run says almost nothing about overall
  quality. Mitigated by recording run shape in the summary and refusing
  cross-shape diffs — but the doc must keep saying floors are the gate.
- **Staleness false negatives.** **[eval]** Resolved for `prepare` by hashing raw
  inputs in Step 2 rather than trusting mtimes. Residual: a source file that
  changes without its hash changing is impossible, but a source *removed* from
  `configs/sources.yaml` while its chunks remain in `chunks.jsonl` is only caught
  via `sources_yaml_sha256` — so keep that field in the comparison, and treat
  `--rebuild` as the documented escape hatch.
- **Baseline-integrity bootstrap.** **[eval]** Resolved: PR6d ships the
  backfilled `2026-07-21-r2.summary.json` *and* the permanent
  `# baseline-provenance: legacy` marker (Step 7). Residual risk is that the
  backfill reveals the committed floors do not match harness output — treat that
  as a stop-and-investigate, not something to paper over.
- **Ratchet in both directions.** Promotion writes 90%-of-best floors, so
  repeated promotion after lucky runs can ratchet floors *up* past what is
  reproducible (later honest changes look like regressions). **[eval]** The
  more dangerous direction is *down*: a degraded run that still clears the floors
  would otherwise write lower floors and permanently hide the regression. Step 5
  now blocks that with the comparable-and-no-regression precondition and the
  audited `--force-promote --reason` override. The upward ratchet remains
  unmitigated; if it bites, add a "floors may rise at most N points per
  promotion" rule.
- **[eval] Summary merge conflicts across branches.** Two branches that each add
  a dated `*.summary.json` merge cleanly, but two runs on the same date collide
  on the stem — `run_eval()` already de-duplicates with a `-2` suffix locally
  (`src/lds_study/eval/run.py:369-376`), which does not coordinate across
  branches. Low impact (conflicts are additive and resolvable by keeping both),
  but prefer descriptive `--stem` values over the date default for anything that
  will be committed from a branch.
- **[eval] The report guard parses markdown.** Step 7's field-scoped check is
  coupled to `write_markdown_report()`'s table layout — the exact coupling this
  plan rejected for the comparison path. Accepted because the alternative is
  blocking a required human edit, and bounded by failing closed on a parse error.
  Any change to the per-item table format must update
  `scripts/check_eval_reports.py` in the same commit.
- **Scope creep into auto-tuning.** `suggest_min_score()` already exists and is
  tempting to apply automatically. Doing so would let the system move its own
  refusal threshold. Explicitly out of scope below.

## Out of scope

- Auto-applying `retrieval.min_score`, `citation.min_coverage`, `final_top_k`, or
  any live ask knob. Suggestions print; humans apply.
- **[eval] An auto-experiment / snapshot-patch mode** that edits
  `configs/rag.yaml` or `prompts/*.md` on the model's own initiative and restores
  on regression. Unanimously rejected in the Phase B evaluation as scope creep
  with a corruption failure mode (crash or concurrent run leaves a half-applied
  config). The only config write this plan permits is `eval.baselines` via
  Step 5, gated as described there. Revisit only as a separate plan with its own
  transactional design.
- Auto-committing or auto-pushing. Automation prepares the change and prints the
  `git add` command; the human commits.
- LLM-as-judge for the manual quality column.
- Running eval in GitHub Actions, or any hosted GPU runner.
- Automatic prompt rewriting under `prompts/`.
- Auto-generating golden questions or `gold_chunk_ids`.
- Hyperparameter search / sweeps over `retrieval.*` (a natural follow-on once
  `lds iterate` exists, but a separate plan — it needs a cost model and a
  guard against overfitting to `golden.yaml`).
- Changes to QLoRA training flow beyond reusing the existing keep-or-revert gate.

**Ready for implementation whenever you are.**
