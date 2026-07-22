# QLoRA Scaffold (PR5) — Implementation Evaluation (Round 2)

*Evaluator: claude · 2026-07-21 · Re-reviews the PR5 slice of `claude-2026-07-20.md` against the working tree (uncommitted, branch `pr5-qlora-scaffold`) after Round-1 remediation.*

## Verdict: Ship it. All three Round-1 findings are fixed correctly, each with new test coverage; suite is 74/74 green and lint-clean. One minor, non-blocking observation remains, plus the same GPU-bound acceptance gate that no offline round can close.

Since [Round 1](pr5-qlora-scaffold-implementation-evaluation-claude-2026-07-21.md), the author wired the keep-or-revert regression gate into `lds eval` behind `--check-baselines` (with KEEP/REVERT output and a non-zero exit on revert), replaced the plain-text training formatter with one that applies the tokenizer chat template, and extended the path-based copyright gate to monitor `adapters/`. Each fix is functionally verified below and guarded by a test. The remaining item — the keep-or-revert *verdict* is surfaced to stdout + exit code but not persisted into the committed `outputs/eval/` report — is a documentation-completeness nit, not a defect. The plan's "Done when" (real 20-step train, adapter loads, eval no-regression) is still GPU-bound and remains proven only by construction.

## Round-1 findings — disposition

| # (Round 1) | Severity | Status | Evidence |
|---|---|---|---|
| 1. `meets_regression_baselines` unwired | Low | **Fixed** | [run.py:351-363](../../src/lds_study/eval/run.py#L351-L363) computes per-model verdicts behind `check_baselines`, reading `eval.baselines`; [cli.py:270-280](../../src/lds_study/cli.py#L270-L280) prints KEEP/REVERT and `raise typer.Exit(1)` on any revert; `--check-baselines` flag at [cli.py:226](../../src/lds_study/cli.py#L226). Test `test_run_eval_check_baselines_keep_and_revert` ([test_pr4_eval.py:222](../../tests/test_pr4_eval.py#L222)) exercises both outcomes and the missing-config `ValueError`. |
| 2. Training formatter bypasses chat template | Low | **Fixed** | [train_qlora.py:63-96](../../src/lds_study/finetune/train_qlora.py#L63-L96): `format_chat_text` calls `tokenizer.apply_chat_template(..., tokenize=False)`; `_ROLE_MAP` maps `human→user`/`gpt→assistant`; plain dump kept only as a fallback when the method is absent. Wired at [train_qlora.py:230,254](../../src/lds_study/finetune/train_qlora.py#L230). Tests cover `conversations_to_messages`, `format_chat_text`, `make_formatting_func` ([test_pr5_finetune.py:268-284](../../tests/test_pr5_finetune.py#L268-L284)). |
| 3. Copyright gate ignores `adapters/` | Low | **Fixed** | `MONITORED_PREFIXES` now includes `"adapters/"` ([check_staged_data.py:29-36](../../scripts/check_staged_data.py#L29-L36)), no allowlist entries. Functionally confirmed: `is_allowed("adapters/lds-qlora/Modelfile")` → `False`, `is_allowed("adapters/lds-qlora/ollama_tag")` → `False`, `is_allowed("data/.gitkeep")` → `True`. Test `test_pr1_scaffold.py:74-83` stages `adapters/lds-qlora/{Modelfile,train_config.json}` and asserts rejection. |
| 4. Acceptance gate GPU-bound / unproven | Noted | **Unchanged (inherent)** | Still no test runs a training step or loads a real PEFT adapter; dry-run paths validate inputs + file-writing only. Correct under the no-GPU rule; run the real slice on WSL2 before recording the step-7 decision. |
| 5. Eval ignores `generator.adapter` (by design) | Noted | **Improved** | Still intentional (compare named `--models` tags), but the loop is now closed: point `--models` at the adapter's Ollama tag and add `--check-baselines` to get the computed keep/revert verdict. README + MODEL_CARD document this path. |

## Findings (ranked)

### 1. Keep-or-revert verdict is not persisted into the eval report artifact. *(Low / Noted)*

The `--check-baselines` verdict is returned on `EvalResult.baseline_verdicts` ([run.py:427](../../src/lds_study/eval/run.py#L427)) and surfaced to the operator via console + exit code, but it is **not** passed to `write_markdown_report` or `write_json_sidecar` ([run.py:378-411](../../src/lds_study/eval/run.py#L378-L411) — neither call receives it; `write_markdown_report`'s signature has no such parameter, [report.py:56-74](../../src/lds_study/eval/report.py#L56-L74)). So the committed `outputs/eval/{date}.md` records the adapter's raw numbers but not the explicit PASS/FAIL against the floors. Step 7 asks to "document that result honestly in the README either way, including 'we tried it and reverted'"; today that documentation depends on the operator transcribing the transient console verdict. A reader can recompute from the persisted numbers + `configs/rag.yaml eval.baselines`, so this is completeness, not correctness.

**Remediation (optional):** thread `baseline_verdicts` + `baselines_checked` into `write_markdown_report`/`write_json_sidecar` and render a one-row KEEP/REVERT line, so the artifact is self-contained. Or accept as-is and rely on the exit code for CI gating.

### 2. Acceptance gate remains demonstrated by construction, not by evidence. *(Noted — carried from Round 1)*

Unchanged and expected: the offline suite cannot run Unsloth/CUDA, so "20-step train completes / adapter loads / eval no regression" is exercised only through `dry_run=True` file-writing. Not a code issue — track the real WSL2 slice as an explicit manual verification before the hybrid is adopted.

## Net assessment

Merge-ready — more so than at Round 1. The three Low findings are closed with correct, tested fixes rather than papered over, the legal boundary remains airtight and now has adapter-output coverage in the path gate, and the keep/revert rule is a computed, exit-code-bearing verdict instead of a dead helper. Only Finding #1 (persist the verdict into the report) is worth a follow-up, and it is optional. Nothing here blocks the PR. A third full round is not warranted; the only remaining "work" is the GPU-bound real-train verification (#2), which happens on hardware, not in review.

## Verification performed

- `.venv/Scripts/python.exe -m pytest -q` → **74 passed** (was 71 at Round 1; +3 for the fixes), no GPU, no network
- `.venv/Scripts/python.exe -m ruff check src/ scripts/check_staged_data.py tests/` → **All checks passed!**
- Staged-gate functional check: `is_allowed` → `False` for `adapters/lds-qlora/Modelfile` and `.../ollama_tag`, `True` for `data/.gitkeep`
- Grep gates: `meets_regression_baselines` now referenced at `run.py:29,362` (wired); `apply_chat_template` present in `train_qlora.py`; `"adapters/"` present in `MONITORED_PREFIXES`
- Spot-checks: `--check-baselines` raises `ValueError` when `eval.baselines` is absent ([run.py:355-359](../../src/lds_study/eval/run.py#L355-L359)); CLI exits non-zero on REVERT ([cli.py:279-280](../../src/lds_study/cli.py#L279-L280)); chat-template path is inside the real-train branch (after `_require_finetune_deps`), so `--dry-run` still needs no tokenizer; PR4 eval reports relocated to `plans/archive/` (unrelated to PR5 code)
