# Model Card — LDS Study Assistant (template)

> Fill fields as PR3–PR5 land. Do not claim Church affiliation.

## Model details

- **Name:** lds-study (local RAG + optional LoRA)
- **Base generator (interim):** Qwen2.5-14B-Instruct (Q4_K_M via Ollama)
- **Base license:** Apache 2.0 (Qwen2.5) — confirm when swapping models
- **Developers:** independent / unofficial
- **Hardware target:** NVIDIA RTX 5070 Ti 16GB (Blackwell sm_120)

## Intended use

- Personal gospel study Q&A with **citations** to indexed chunks
- Lesson / talk preparation outlines grounded in retrieved sources

## Out-of-scope use

- Presenting output as official Church doctrine or prophetic counsel
- Medical, legal, or safety-critical advice
- Redistributing Conference / Come Follow Me text or derived weights
- Multi-user hosted deployment

## Training data (when Option B is used)

- Instruction pairs from sources marked `redistributable: true` with verified licenses only
  (`lds finetune-dataset` → `data/processed/sft.jsonl`)
- **Never** Conference talks or Come Follow Me
- Adapters trained on restricted material must **not** be published

## Evaluation data

- Harness: `lds eval` over `eval/golden.yaml` (see `eval/README.md`)
- Latest comparison: [outputs/eval/2026-07-21-r2.md](outputs/eval/2026-07-21-r2.md)
  (qwen2.5:14b vs qwen3:14b at `min_score: 0.05`; harness-emitted baselines)
- Score calibration: [outputs/eval/2026-07-21-scores.md](outputs/eval/2026-07-21-scores.md)
- PR5 keep-or-revert: compare adapter eval against `configs/rag.yaml` `eval.baselines`

## Known limitations

- Archaic English retrieval may miss paraphrases
- Hallucinated attribution risk if citation validation is bypassed
- Mirror / edition provenance residual risk (see docs/LEGAL.md)

## Ethical considerations

- Unofficial; see DISCLAIMER.md
- User is responsible for BYOF copyright compliance
