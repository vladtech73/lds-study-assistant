# Automate the RAG improvement cycle

*Author: grok · 2026-07-22*

## Goal

Encode `docs/IMPROVEMENT_CYCLE.md` as a **composable, fail-closed CLI pipeline** so measure → (optional one-knob experiment) → re-measure → KEEP/REVERT is mostly mechanical. Success looks like:

- One command (or a small set) can: optionally prepare/index, run eval (full or focused), **diff vs the last committed report**, gate on `configs/rag.yaml` `eval.baselines`, and optionally **apply suggested baselines** only with an explicit flag.
- Operators still choose *what* to change and *whether* to ship; the tooling removes copy-paste, forgotten re-index, and silent metric regressions.
- The plan explicitly lists what **cannot** be automated so expectations stay honest.

## Constraints

- **Fail-closed copyright:** never stage/commit `data/`, `indexes/`, adapters, or `eval/*.local.yaml`; only `outputs/eval/**/*.md` reports are allowlisted (`scripts/check_staged_data.py`).
- **One knob at a time** for auto-experiments; no multi-parameter Bayesian search in v1.
- **Do not hand-edit baseline numbers** — only paste harness-emitted `suggested_baselines` (existing rule in IMPROVEMENT_CYCLE).
- **No silent config mutation** — writing `rag.yaml` / `models.yaml` requires `--apply` / `--write` + dry-run default.
- **GPU/Ollama eval stays local** — CI (`.github/workflows/ci.yml`) remains offline unit tests; live cycle is opt-in on the workstation.
- **Adapters:** keep only if `--check-baselines` KEEP; never publish restricted-trained adapters (PR5 rules).
- Prefer extending `src/lds_study/cli.py` + `src/lds_study/eval/*` over a parallel PowerShell-only toolchain; thin `.ps1` wrappers OK for Windows DX.
- Match existing patterns: Typer CLI, YAML configs, markdown reports + gitignored JSON sidecars.

## Approach

**Primary:** add a small **cycle orchestrator** (`lds cycle` or `lds improve`) plus **eval comparison / baseline-apply helpers**, then an optional **single-knob experiment** mode that snapshots config, applies one documented knob, re-measures, and restores on REVERT.

Reuse what already exists:

| Piece | Path |
|---|---|
| Manual playbook | `docs/IMPROVEMENT_CYCLE.md` |
| Eval run + `--check-baselines` | `src/lds_study/eval/run.py`, `src/lds_study/cli.py` |
| Metrics / suggested floors / min_score heuristic | `src/lds_study/eval/metrics.py` |
| Report writers | `src/lds_study/eval/report.py` |
| Floors | `configs/rag.yaml` → `eval.baselines` |
| Last ship report | `outputs/eval/2026-07-21-r2.md` (and future stems) |
| Preflight | `scripts/check_env.py` |

**Rejected alternatives:**

- **Fully autonomous “AI agent picks knobs forever”** — conflicts with one-knob discipline, prompt quality judgment, and copyright gates; defer indefinitely.
- **CI-gated live Ollama eval on every PR** — too slow/flaky/costly for this hardware-bound repo; keep as optional workflow later if desired.
- **Makefile-only orchestration** — weaker on Windows; CLI-first matches the product.

### Automation matrix (what this plan covers)

| Cycle step | Automate? | How |
|---|---|---|
| Diagnose symptom (“feels wrong”) | **Partial** | Suggest knobs from last metrics / score dist; human confirms |
| Choose *one* knob | **Partial** | Catalog of safe knobs + presets; human or `--knob=` |
| Apply config change | **Yes** | Snapshot → patch YAML → restore on revert |
| Decide re-prepare / re-index | **Yes (heuristic)** | Knobs tagged `needs_prepare` / `needs_index`; fingerprint chunks/embedder |
| Run eval (full / bucket / retrieval-only) | **Yes** | Existing `lds eval` |
| Compare to last committed report | **Yes (new)** | Parse prior `outputs/eval/*.md` tables + JSON sidecar if present |
| KEEP/REVERT vs floors | **Yes** | Existing `--check-baselines` (+ persist verdict into report) |
| Paste baselines into `rag.yaml` | **Yes (opt-in)** | `--apply-baselines` from suggested block |
| Commit report / update MODEL_CARD | **Partial** | Emit suggested commit paths + MODEL_CARD link text; human commits |
| Prompt / golden authoring | **No** | Human |
| Subjective quality 1–5 | **No** | Human |
| Ship / product judgment when metrics trade off | **No** | Human |

## Implementation

### 1. Document the automation contract in the playbook

Update `docs/IMPROVEMENT_CYCLE.md` with an **“Automated cycle”** section that maps each manual step to CLI flags, and a **“Still manual”** subsection (see Out of scope / can’t automate below). Cross-link `eval/README.md` and `README.md`.

**Done when:** playbook describes both human and automated paths without contradicting current floors/rules.

### 2. Persist KEEP/REVERT into eval artifacts

Thread `baseline_verdicts` / `baselines_checked` into `write_markdown_report` and `write_json_sidecar` (`src/lds_study/eval/report.py`, callers in `src/lds_study/eval/run.py`). Render a one-row KEEP/REVERT section so committed markdown is self-contained (closes the known PR5 nit).

**Done when:** `lds eval --check-baselines` writes verdicts into `{stem}.md` + `.json`; unit test asserts presence.

### 3. Add report compare helper

New module e.g. `src/lds_study/eval/compare.py`:

- Resolve **baseline report**: `--vs outputs/eval/2026-07-21-r2.md` or default = newest committed-looking stem under `outputs/eval/` (prefer known “ship” stem via config key `eval.reference_report` optional).
- Prefer JSON sidecar when present; else parse comparison table from markdown (robust enough for our own writer format).
- Emit delta table: Δ recall, Δ cite validity, Δ adversarial refusal per model; flag regressions vs floors and vs prior report.
- CLI: `lds eval-compare --current <stem> --vs <path>` and/or integrate into cycle.

**Done when:** comparing two fixture reports in tests shows expected deltas; CLI prints clear KEEP-ish / REGRESS summary.

### 4. Add `lds cycle` orchestrator (measure path)

New command in `src/lds_study/cli.py` (implementation in e.g. `src/lds_study/eval/cycle.py` or `src/lds_study/cycle/run.py`):

```text
lds cycle measure
  [--profile default]
  [--models …]          # default: doc recipe qwen2.5:14b,qwen3:14b (not full shortlist)
  [--buckets …]
  [--retrieval-only]
  [--prepare / --index / --auto-deps]
  [--check-baselines]
  [--vs <report>]
  [--stem …]
  [--dry-run]
```

Behavior:

1. Optional `scripts/check_env.py` preflight (warn, don’t hard-fail CPU if `--allow-cpu`).
2. If `--prepare` / `--index` / `--auto-deps`: call existing prepare/index entrypoints.
3. Run `run_eval(...)` with `check_baselines` as requested.
4. Run compare vs `--vs` / reference report.
5. Exit non-zero on REVERT or regression vs prior (configurable: `--fail-on prior|baselines|both`).

**Done when:** dry-run prints the planned steps; live path is a thin wrapper over existing functions (no duplicated eval logic).

### 5. Knob catalog + safe experiment mode

Add `configs/cycle_knobs.yaml` (or a section under `configs/rag.yaml`) listing **named knobs** aligned with the symptom table:

| Knob id | Path | Re-index? | Notes |
|---|---|---|---|
| `retrieval.min_score` | `rag.yaml` | No | Use `suggest_min_score` as *suggestion only* |
| `retrieval.final_top_k` / dense/bm25 tops | `rag.yaml` | No* | *Yes if embedder/chunking changed separately |
| `citation.min_coverage` | `rag.yaml` | No | |
| `citation.max_regenerate` | `rag.yaml` | No | |
| `generator.id` | `models.yaml` | No | Eval via `--models` |
| `prompts.*` | file path | No | Experiment = swap file contents from a patch dir — **careful** |

```text
lds cycle experiment --knob retrieval.min_score --value 0.08 \
  --models qwen2.5:14b --buckets adversarial --check-baselines
```

Algorithm:

1. Snapshot touched YAML (and optional prompt files) to `outputs/cycle/snapshots/{ts}/`.
2. Apply single change.
3. Run measure path (no prepare/index unless knob metadata says so).
4. On KEEP: leave change + print “commit configs/… and outputs/eval/…”.
5. On REVERT: restore snapshot; exit 1; leave eval report for forensics.

**Done when:** unit tests use tmp configs; REVERT restores bytes; KEEP leaves new value; attempting two knobs in one invocation errors.

### 6. Opt-in baseline apply + MODEL_CARD hint

```text
lds cycle apply-baselines --from outputs/eval/{stem}.json|--from-last-eval
  [--dry-run] [--write]
```

- Read `suggested_baselines` from sidecar (or recompute from aggregates).
- Replace only `eval.baselines` mapping in `configs/rag.yaml` (ruamel/yaml round-trip preferred to preserve comments where feasible; if too hard, replace the `baselines:` block with a clearly delimited generated section).
- Print suggested `MODEL_CARD.md` “Latest comparison” link line; do **not** auto-edit MODEL_CARD unless `--write-model-card` (default off).

**Done when:** dry-run shows diff; `--write` updates floors; test with fixture YAML; never touches unrelated keys.

### 7. Dependency / re-index heuristic

Lightweight fingerprint helpers (e.g. in `src/lds_study/cycle/deps.py`):

- Hash `configs/models.yaml` embeddings/reranker ids + `configs/rag.yaml` `chunking.*`.
- Compare to `indexes/{profile}/.cycle_fingerprint` written at end of successful `lds index`.
- `lds cycle measure --auto-deps` runs prepare/index only when fingerprint mismatch or missing index.

**Done when:** changing embedder id forces index; changing `min_score` alone does not.

### 8. Tests + docs polish

- Extend `tests/test_pr4_eval.py` / add `tests/test_cycle.py`: compare, apply-baselines dry-run, experiment revert, fingerprint.
- Keep tests **offline** (no Ollama); mock `run_eval` where needed.
- Update `docs/IMPROVEMENT_CYCLE.md`, `eval/README.md`, short README pointer.

**Done when:** `pytest -q` green offline; ruff clean.

## Verification

- Offline: `.\.venv\Scripts\python.exe -m pytest -q` and `ruff check src/ tests/`.
- Manual (GPU/Ollama, operator):
  1. `lds cycle measure --models qwen2.5:14b --retrieval-only --stem cycle-smoke --vs outputs/eval/2026-07-21-scores.md`
  2. `lds cycle experiment --knob retrieval.min_score --value 0.12 --models qwen2.5:14b --buckets adversarial --check-baselines` → expect REVERT + config restored (per known scores doc).
  3. `lds cycle measure --check-baselines --vs outputs/eval/2026-07-21-r2.md` on current default → KEEP.
  4. `lds cycle apply-baselines --from-last-eval --dry-run` shows verbatim suggested block.
- Invariant: experiment never leaves half-applied multi-knob state; copyright gate still rejects `eval/golden.local.yaml` / `adapters/`.

## Risks

- **Markdown table parse fragility** if report format drifts — mitigate by preferring JSON sidecar + version field.
- **YAML comment loss** on baseline apply — mitigate with block-replace or ruamel; document if comments strip.
- **False confidence from automating knob selection** — suggestions must be labeled heuristic; default experiment still requires `--knob`.
- **Long wall-clock** for full dual-model eval — default cycle models to the playbook’s two-model recipe; support `--retrieval-only` / `--buckets`.
- **Fingerprint false positives** forcing slow re-index — allow `--skip-deps` escape hatch.

## What cannot be automated

Be explicit with operators (also mirror in IMPROVEMENT_CYCLE):

1. **Symptom diagnosis / taste** — “answers feel weak,” pastoral tone, lesson usefulness. Metrics catch groundedness/refusal, not spiritual helpfulness.
2. **Choosing *which* product tradeoff to accept** — e.g. higher `min_score` improves adversarial refusal but can hurt recall; floors don’t decide preference when both stay above baseline.
3. **Authoring or editing prompts** that actually improve quality — tooling can A/B two prompt files you supply; it cannot write good doctrinal phrasing.
4. **Authoring golden / local golden questions** — especially BYOF / restricted `eval/golden.local.yaml` (must stay uncommitted).
5. **Human quality column (1–5)** on eval reports — remains manual if used.
6. **Legal / publish decisions** — whether an adapter or dataset is redistributable; gate tooling can only enforce path allowlists and redistributable filters already in PR5.
7. **Committing and shipping** — git commit, PR, MODEL_CARD narrative, changelog voice.
8. **Fixing root causes outside knobs** — bad OCR, missing sources, wrong `gold_chunk_ids`, index corruption — need human investigation (automation can only flag smoke/index failures).
9. **Full closed-loop “AI SRE”** that invents knobs overnight without supervision — out of scope forever for this repo’s risk profile.
10. **Guaranteeing WSL2/Unsloth train success** — cycle can chain `finetune-*` later as an optional profile; hardware/driver failures stay manual.

## Out of scope

- Autonomous multi-knob optimization / hyperparameter search.
- Running live Ollama eval in default GitHub Actions CI.
- Auto-committing reports or baselines.
- Auto-editing golden.yaml.
- Replacing RAG with fine-tune-for-facts.
- Music mode / non-study product surfaces.
- Building a web UI for the cycle.

## PR split

1. **PR-A — Observe:** persist baseline verdicts; `eval-compare`; `cycle measure` (prepare/index/eval/compare/gate); docs matrix.
2. **PR-B — Experiment:** knob catalog + snapshot/restore experiment command + fingerprint `--auto-deps`.
3. **PR-C — Apply:** `apply-baselines` (+ optional MODEL_CARD hint); playbook finalized.

## Open questions

- Command name: `lds cycle` vs `lds improve` vs subcommands under `lds eval`? Prefer `cycle` to match the doc title.
- Should `eval.reference_report` live in `rag.yaml` pointing at `outputs/eval/2026-07-21-r2.md`?
- Include optional `cycle finetune` profile in PR-B or defer to a later plan?

**Ready for implementation whenever you are.**
