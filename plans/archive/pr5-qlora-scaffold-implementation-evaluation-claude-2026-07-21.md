# QLoRA Scaffold (PR5) — Implementation Evaluation

*Evaluator: claude · 2026-07-21 · Reviews the PR5 slice of `claude-2026-07-20.md` against the working tree (uncommitted changes on branch `pr5-qlora-scaffold`).*

## Verdict: Complete and safe to merge as a scaffold; the legal boundary is solid, but two of the plan's own contracts land as tested-but-unwired code, and the acceptance gate is unproven.

The restricted-source exclusion — the one non-negotiable in this PR — is enforced unconditionally with no override surface, and is guarded by three independent tests (behavioral, signature, and source-scan). All five PR5 deliverables (`[finetune]` extra, dataset builder, `train_qlora.py`, `merge_and_export.py`, WSL2 docs) plus the step-7 hybrid wiring are present, lint-clean, and pass 71/71 tests offline. The gaps are not correctness bugs: the keep-or-revert regression gate exists only as an uncalled helper, the training formatter bypasses the chat template (a quality issue for any real train), and the plan's "Done when" (real 20-step train + adapter loads + eval no-regression) is GPU-bound and therefore demonstrated only via dry-run scaffolding.

## Completeness & accuracy by workstream

| Workstream (step) | Status | Evidence |
|---|---|---|
| `[finetune]` extra, documented "not needed for RAG" | **Complete** | [pyproject.toml:34-40](../../pyproject.toml#L34-L40) (unsloth/peft/trl/bitsandbytes/datasets); [finetune/__init__.py:1](../../src/lds_study/finetune/__init__.py#L1) |
| `build_dataset.py` — unconditional restricted exclusion, no flag | **Complete** | [build_dataset.py:48-80](../../src/lds_study/finetune/build_dataset.py#L48-L80); tests `test_restricted_chunks_never_reach_sft_jsonl`, `test_filter_sft_drops_restricted_unconditionally`, `test_build_dataset_sig_has_no_restricted_override` all pass |
| `train_qlora.py` — Unsloth, r16/α32 attn+MLP, bsz1/accum8, seq2048 | **Complete (real train unverified)** | [train_qlora.py:140-217](../../src/lds_study/finetune/train_qlora.py#L140-L217); dry-run verified via CLI (`train_config.json` written); Unsloth path never executed (no GPU) |
| `merge_and_export.py` — merge → GGUF → Ollama register | **Complete (real merge unverified)** | [merge_and_export.py:65-154](../../src/lds_study/finetune/merge_and_export.py#L65-L154); dry-run writes `Modelfile` + `ollama_tag`; `subprocess.run` uses arg-list, not shell |
| WSL2 docs (native → failure signatures → WSL2) | **Complete** | [docs/FINETUNE_WINDOWS.md](../../docs/FINETUNE_WINDOWS.md) updated with real command sequence; referenced flags `--scripture-only` / `--include-finetune-weights` verified to exist |
| Step 7 hybrid wiring — `generator.adapter` used by `ask` | **Complete** | [generate.py:17-56](../../src/lds_study/rag/generate.py#L17-L56) `resolve_generator_model_id`; [ask.py:88-96](../../src/lds_study/rag/ask.py#L88-L96) passes `root`; tested |
| Step 7 keep-or-revert regression gate | **Partial** | [metrics.py:201-231](../../src/lds_study/eval/metrics.py#L201-L231) `meets_regression_baselines` defined + tested but **called by no command** |
| CLI surface (`finetune-dataset/-train/-export`) | **Complete** | [cli.py:263-355](../../src/lds_study/cli.py#L263-L355); dry-run flow exercised end-to-end, exit code 1 on missing input |
| README / MODEL_CARD "adapters on restricted must not be published" | **Complete** | [README.md](../../README.md) QLoRA section; [MODEL_CARD.md:28-30](../../MODEL_CARD.md#L28-L30) |
| PR5 "Done when" (20-step train completes; adapter loads; eval no regression) | **Unproven (GPU-bound)** | No test runs a training step or loads a real PEFT adapter; only dry-run file-writing is exercised |

## Findings (ranked)

### 1. `meets_regression_baselines` is a tested helper that nothing calls. *(Low)*

Step 7 states the keep-or-revert rule as a hard gate: keep the adapter **"only if citation validity and adversarial refusal rate meet or beat the PR4 baseline."** The implementation adds `meets_regression_baselines` ([metrics.py:201](../../src/lds_study/eval/metrics.py#L201)) and a unit test, and `configs/rag.yaml` carries the floors (`eval.baselines`: recall 0.711 / citation 0.9 / refusal 0.825). But a repo-wide grep shows the function is referenced only in its own definition and the test — no CLI path, `eval/run.py`, or report writer invokes it. So `lds eval --models lds-study-adapter` prints the adapter's numbers but never computes or surfaces a PASS/FAIL against the baseline. The plan's gate is therefore documentation plus a dead helper; the human must eyeball the table and apply the rule by hand, exactly the "vibes" outcome PR4's baselines were meant to eliminate.

**Remediation:** call `meets_regression_baselines` from the eval command when a single adapter model is evaluated (or behind a `--check-baselines` flag), read floors from `configs/rag.yaml eval.baselines`, and print `KEEP`/`REVERT` with the failing metrics. Alternatively, document explicitly that keep-or-revert is a manual step and the helper is a library convenience.

### 2. Training formatter bypasses the tokenizer chat template. *(Low)*

`_formatting` ([train_qlora.py:167-186](../../src/lds_study/finetune/train_qlora.py#L167-L186)) renders each pair as literal `"human: …\ngpt: …"` text rather than `tokenizer.apply_chat_template(...)`. The adapter would then learn the `human:`/`gpt:` scaffolding as surface tokens, which does not match the Qwen chat format the Ollama inference path actually uses at `ask` time. For a fine-tune whose entire purpose is *style/citation-discipline transfer*, training on an off-template surface form is the mechanism most likely to make the style fail to transfer — a silent quality regression, not a crash. The 20-step slice will still "complete," so the plan's gate passes while the adapter is miscalibrated.

**Remediation:** build training text with `apply_chat_template` (map `from: human|gpt → role: user|assistant`), keeping the `messages` fallback. Verify against one real slice before claiming step 7's "no regression."

### 3. Copyright staged-file gate does not monitor `adapters/`. *(Low)*

PR5 introduces `adapters/` as the output directory for merged weights, GGUF, and Modelfiles derived from training — precisely the artifact the plan's Risks section flags ("someone … publishes an adapter trained on [a talk]"). That risk names two mitigations: gitignore **and** the path-based CI staged-file check. Only the first covers `adapters/`: it is in `.gitignore`, and weight extensions (`*.safetensors`/`*.bin`/`*.gguf`) are globally ignored, so an accidental `git add .` is caught and the weights themselves are doubly protected. But `check_staged_data.py`'s `MONITORED_PREFIXES = ("data/", "indexes/", "models/", "outputs/", "private/")` omits `adapters/`, so a **force-added** adapter directory (`git add -f`) — Modelfile, `export_meta.json`, `train_config.json` (which records `base_model` + `data_path`), or a weight saved under a non-standard name — sails past the very gate the plan built to be un-bypassable ("path-based, not grep-based … trivially bypassed by a rename"). The catastrophic case (raw weights) stays contained by the extension globs; this is a defense-in-depth gap, not an open door.

**Remediation:** add `"adapters/"` to `MONITORED_PREFIXES` in [scripts/check_staged_data.py](../../scripts/check_staged_data.py) with no allowlist entries, so any staged path under it fails the gate.

### 4. PR5 acceptance gate is scaffolded, not demonstrated. *(Noted)*

The plan's "Done when" is three GPU-bound facts: a `--max-steps 20` train completes, the adapter loads, and `lds eval` shows no regression. None is exercised by the offline suite — `dry_run=True` validates the dataset and writes `train_config.json`/`Modelfile` but never enters Unsloth, and no test instantiates a real PEFT adapter. This is the correct behavior under the repo's "no GPU, no network" test rule, and the dry-run substitute is well-built, but the gate remains met *by construction*, not by evidence. Anyone merging on the strength of "PR5 done" should run the real slice on WSL2 first.

**Remediation:** none for the scaffold. Track the real 20-step run + adapter-load + adapter-eval as an explicit manual verification item before step 7's keep/revert decision is recorded.

### 5. Eval intentionally ignores `generator.adapter`. *(Noted — no action)*

[eval/run.py:70-80](../../src/lds_study/eval/run.py#L70-L80) documents that eval compares named `--models` tags and does not honor `generator.adapter`; to eval an adapter you pass its Ollama tag as a model. This is a coherent, documented choice consistent with the README example, and it correctly avoids a hidden global toggle changing eval results. Flagged only so no reader expects `eval` to auto-pick up a configured adapter — it will not.

## Net assessment

Merge-ready as a scaffold. The legal boundary that gates this PR is airtight and over-tested, the deps are correctly optional, the CLI/docs are coherent, and lint + the full suite are green. Nothing here is a blocker. Before the *hybrid* is actually adopted (step 7), three things are worth doing — in priority order: fix the chat-template formatter (#2) so the adapter that gets evaluated is the one you'd ship; wire `meets_regression_baselines` into `eval` (#1) so keep/revert is a computed verdict rather than a manual read; and add `adapters/` to the staged-file gate (#3). All three are small, local edits. Findings #4 and #5 need no code change, only honest tracking that the real training gate has not yet run.

## Verification performed

- `.venv/Scripts/python.exe -m pytest tests/test_pr5_finetune.py -q` → **8 passed**
- `.venv/Scripts/python.exe -m pytest -q` (full suite) → **71 passed** (no GPU, no network)
- `.venv/Scripts/python.exe -m ruff check src/lds_study/finetune/ tests/test_pr5_finetune.py src/lds_study/eval/metrics.py` → **All checks passed!**
- CLI dry-run flow: `finetune-train --max-steps 20 --dry-run` → wrote `train_config.json` (exit 0); `finetune-export --dry-run` → wrote `Modelfile` + `ollama_tag=lds-study-adapter` (exit 0)
- Error path: `finetune-dataset --chunks <missing>` → "Missing chunks file … Run `lds prepare` first.", **exit 1**
- Grep gates: `meets_regression_baselines` referenced only in its definition + tests (unwired); `adapters/` absent from `MONITORED_PREFIXES` in `check_staged_data.py`; `allow-restricted`/`include-restricted` absent from every `add_argument` line
- Spot-checks: `Chunk` carries `source_id`/`source_type`/`redistributable` and the flag propagates from source through `prepare.py`/`user_files.py`/`public_scripture.py`, so `filter_sft_chunks` filters real prepare output, not just fixtures; `Settings.effective_root`/`resolve`/`load_yaml` used by the adapter resolver all exist; referenced doc flags `--scripture-only` and `--include-finetune-weights` exist in the CLI; `adapters/`, `*.gguf`, `*.bin`, `*.safetensors`, and `data/processed/**` are all gitignored
