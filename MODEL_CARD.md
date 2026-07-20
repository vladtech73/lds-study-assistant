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
- **Never** Conference talks or Come Follow Me

## Evaluation data

- See `lds eval` reports under `outputs/eval/` (reports only; no corpus)

## Known limitations

- Archaic English retrieval may miss paraphrases
- Hallucinated attribution risk if citation validation is bypassed
- Mirror / edition provenance residual risk (see docs/LEGAL.md)

## Ethical considerations

- Unofficial; see DISCLAIMER.md
- User is responsible for BYOF copyright compliance
