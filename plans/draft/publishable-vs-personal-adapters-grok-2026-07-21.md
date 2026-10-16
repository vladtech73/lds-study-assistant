# Publishable vs personal adapter training tracks

*Author: grok · 2026-07-21*

## Goal

Define a dual-track fine-tuning process so you can:

1. **Publishable track** — train a LoRA on redistributable-only data, gate it with `lds eval`, optionally upload to Hugging Face with a filled model card.
2. **Personal track** — train a separate LoRA that may include BYOF Conference/CFM, keep it gitignored forever, never upload.

Success = two physically separated artifact trees, one irreversible publish gate that refuses personal weights, and docs that make the wrong path hard to take by accident.

## Constraints

- Do **not** implement this before **PR4** (`lds eval` + baselines in `configs/rag.yaml`). Eval is the regression gate for any adapter.
- Respect existing legal posture: `docs/LEGAL.md`, `MODEL_CARD.md`, `configs/sources.yaml` (`redistributable: false` for `user-byof`).
- Personal/Conference material stays under gitignored paths (`data/raw/user/`, `private/`, local adapter dirs). Never commit talk text, personal SFT JSONL, or personal adapters.
- Publishable dataset builder must **unconditionally** drop `redistributable: false` rows — **no flag** re-enables them (matches `claude-2026-07-20.md` PR5).
- Personal train is opt-in, documented as local-only, and must fail closed if someone tries Hub upload.
- Base model licenses (e.g. Qwen Apache 2.0) still apply to any published adapter.
- 16GB Blackwell: QLoRA path already fragile on native Windows — reuse `docs/FINETUNE_WINDOWS.md` / WSL2; do not invent a second stack.

## Approach

**Build order:** finish prep index → **PR4 eval** → **PR5 dual-track finetune** (extend the planned scaffold; do not train for real until eval baselines exist).

**Chosen design:** one shared train script, two **profiles** (`publishable` | `personal`) that differ only in dataset filter, output directory, and publish eligibility. Same Unsloth/PEFT stack; hard separation at I/O boundaries.

Rejected alternatives:

- Single mixed dataset with a “strip before upload” step — too easy to leak restricted signal into published weights.
- Two entirely separate codebases — duplicated train bugs; profiles are enough.
- Publishing merged full weights by default — oversized and unnecessary; default Hub artifact = LoRA adapter only.

## Implementation

### 1. Sequencing (do this first — not finetune)

| Step | Action | Done-when |
|---|---|---|
| Prep | `lds index --profile default` | `indexes/default/` exists |
| PR4 | `golden.yaml`, `lds eval`, ≥2 generators | Report under `outputs/eval/*.md`; baselines written to `configs/rag.yaml` |
| Branch | `pr5-qlora-dual-track` off `main` after PR4 merges | Ready to implement this plan |

### 2. Directory & naming layout

```text
data/processed/
  sft.publishable.jsonl    # gitignored; redistributable-only
  sft.personal.jsonl       # gitignored; may include BYOF talks

adapters/                  # gitignored (already in .gitignore)
  publishable/<run-id>/    # Hub-eligible after eval pass
  personal/<run-id>/       # NEVER Hub; local ask only

private/                   # already gitignored — optional personal train wrappers
```

Tag every run with `track: publishable|personal` in a small `run.json` next to the adapter.

### 3. Dataset builder (`src/lds_study/finetune/build_dataset.py` — PR5)

- CLI: `lds finetune-dataset --track publishable|personal` (or script entry).
- **Publishable:** only chunks/sources with `redistributable: true` + verified license; unit test that a restricted fixture **cannot** appear in output.
- **Personal:** may include `user-byof` / `redistributable: false`; write only to `sft.personal.jsonl`; print a loud banner: “NOT FOR PUBLICATION”.
- Pair types (both tracks): cite-and-explain, cross-ref, lesson/talk outline formatting — personal track may add talk-grounded pairs.

### 4. Train (`src/lds_study/finetune/train_qlora.py` — PR5)

- Require `--track` and refuse to start if output dir track mismatches dataset path.
- Defaults: Unsloth 4-bit, LoRA r=16/α=32, bsz 1 + accum 8, seq 2048, `--max-steps 20` debug path.
- Write adapter under `adapters/{track}/{run-id}/` + `run.json` (`track`, base model id, dataset path, git commit if available, created_at).

### 5. Eval gate before keep / publish

- Wire adapter path into `configs/models.yaml` `generator.adapter` (PR5 hybrid wiring).
- Run `lds eval` with adapter on vs PR4 baseline.
- **Keep** only if citation validity and adversarial refusal meet or beat baseline.
- Document “tried and reverted” in README / model card if it fails.

### 6. Publish path (publishable track only)

New script (PR5 or small follow-up): `src/lds_study/finetune/publish_hub.py` (or `scripts/publish_adapter.py`):

1. Load `run.json`; **exit non-zero** if `track != publishable`.
2. Recheck dataset path is `sft.publishable.jsonl` (or recorded checksum of that file).
3. Require `--i-confirm-redistributable-only` flag.
4. Upload **adapter folder only** via `huggingface_hub` + filled card from `MODEL_CARD.md` template.
5. Refuse if `data/raw/user/` paths appear in training manifest.

Personal track: no publish command; docs say use local `generator.adapter` only.

### 7. Docs & gates

- Extend `docs/FINETUNE_WINDOWS.md` with the two-track flowchart and Hub rules.
- README: one short “Publishing adapters” section pointing at publishable-only.
- Ensure `adapters/` and both SFT JSONLs stay gitignored; copyright gate already covers `data/`.
- Optional: `check_staged_data.py` already ignores publishing weights; keep `private/` blocked (already done).

### 8. Local ask with personal weights

- Set `generator.adapter: adapters/personal/<run-id>` in a **gitignored** override (e.g. `.env` / local `configs/models.local.yaml` if introduced) so personal paths never hit git.
- Same RAG retrieve → generate → cite path; adapter is style-only.

## Verification

- Unit: restricted fixture never in `sft.publishable.jsonl`.
- Unit: `publish_hub` rejects `track=personal` and missing confirm flag.
- Integration: `--max-steps 20` publishable train completes; adapter loads.
- Integration: personal train writes under `adapters/personal/` only.
- Manual: `lds eval` before/after publishable adapter; baselines held.
- Manual: `git status` clean of talk text / personal adapters / `private/` when committing PR5 code-only.

## Risks

- Accidental Hub upload of personal adapter — mitigate with `run.json` track check + confirm flag + no default publish in README for personal.
- Personal signal improving “style” while hurting refusal — mitigate with mandatory eval gate.
- Dual datasets confusing operators — mitigate with track-required CLI and banners.
- PR5 scope creep before PR4 — **do not start training work until eval exists.**

## Out of scope

- Implementing PR4 or PR5 in this plan (process design only).
- Scraping Church sites in the published package (personal fetch stays in `private/`).
- Publishing full merged 14B weights or training datasets.
- Multi-user hosted deployment of either adapter.
- Changing the legal definition of redistributable sources.

## PR split

| PR | Contents |
|---|---|
| **PR4** (existing) | Eval harness + baselines — **prerequisite** |
| **PR5a** | Finetune scaffold + publishable dataset/train/export + eval wiring |
| **PR5b** | Personal track + Hub publish script with fail-closed guards + docs |

(PR5a/PR5b may be one PR if small; prefer split if review noise is high.)

## Open questions

- Local config override file (`models.local.yaml`) vs only env for personal adapter path?
- Whether personal track is documented in the public README (high-level “local-only track exists”) or only under `docs/FINETUNE_WINDOWS.md` / `private/README.md`.

**Recommendation:** Do **not** fully build dual-track training first. Finish index prep + **PR4**, then implement PR5 using this process. Drafting the plan now is useful; coding it before eval would optimize the wrong layer.

**Ready for implementation whenever you are — after PR4.**
