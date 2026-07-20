# LDS Study Assistant Plan Evaluation Report

*Date: 2026-07-20 · Evaluators: composer-2.5, gpt-5.6-sol-medium, gemini-3.1-pro · Mode: readonly parallel review*
*Plans compared:*
- [Claude](claude-2026-07-20.md)
- [Grok](grok-2026-07-20.md)

---

## Verdict

**Unanimous (3/3): execute the Claude plan.**

Claude is the safer baseline for citation integrity, restricted-content controls, hybrid retrieval, and Blackwell/Windows toolchain reality; fold Grok’s PR split and CLI-first delivery in before coding.

---

## Scoreboard

| Criterion | Composer — C / G | GPT — C / G | Gemini — C / G |
|-----------|------------------|-------------|----------------|
| Audit accuracy | 5 / 3 | 3 / 2 | 5 / 3 |
| Risk awareness | 5 / 3 | 4 / 2 | 5 / 4 |
| Implementability | 4 / 4 | 3 / 3 | 5 / 4 |
| Completeness vs scope | 4 / 3 | 2 / 3 | 4 / 4 |
| **Winner** | **Claude** | **Claude** | **Claude** |
| Confidence | high | high | high |

*Note: GPT scored Claude lower on audit accuracy and completeness (legal overclaims + scope creep) but still picked Claude for safety mechanics.*

---

## Why the winner won (shared themes)

1. **Hardware truth:** Claude pins RTX 5070 Ti Blackwell `sm_120`, CUDA 12.8+, and `cu128` PyTorch with `check_env.py`; Grok omits this first-day blocker.
2. **Citations as code:** verse-atomic chunks, hybrid BM25+dense+rerank, and post-generation citation validation vs Grok’s prompt + “citation present” heuristic.
3. **Legal hygiene in the pipeline:** `redistributable` flags, BYOF paths, CI staged-`data/` checks vs docs-only rules and unrestricted `instruct_pairs.py`.
4. **QLoRA subordinated:** eval harness and regression gates before adapters; Grok scaffolds QLoRA without a groundedness/refusal gate.
5. **RAG-first product risk framing:** misquotation/false attribution treated as the core failure mode, not an afterthought.

---

## Critical feedback — Claude

### Blocking
- Soften / verify the blanket “standard works are public domain” claim source-by-source (esp. D&C, PoGP, modern Church formatting/apparatus). (GPT)
- Remove or severely constrain `--allow-restricted` on SFT dataset generation — it undermines the stated legal boundary. (GPT)
- Specify citation failure semantics: invalid/unsupported citations must regenerate, refuse, or fail visibly — not silently strip markers and leave prose looking valid. (GPT)
- Add an explicit PR split (borrow Grok’s); eight stages + FastAPI UI is too large as one sequence. (Composer, GPT)
- Defer FastAPI + SPA `serve` and narrow v1 task modes; `music`/hymn corpus is scope creep until `study` works. (Composer, Gemini, GPT)

### Non-blocking
- Name a known-good interim default (e.g. Qwen2.5-14B) until `lds eval` picks from the shortlist; Qwen3 packaging may lag. (Composer)
- Document WSL2 fallback for Unsloth/bitsandbytes on Windows from day one. (Gemini)
- Pick Chroma **or** LanceDB for v1; don’t leave both open. (Composer, GPT)
- Fix package naming risk (`lds` → e.g. `lds_study`) and resolve `[rag]` extra vs “`pip install -e .` is enough” contradiction. (Composer, GPT)
- CI rule that rejects *all* staged `data/` paths conflicts with committed `data/.gitkeep` / README — carve an allowlist. (GPT)
- Soften absolute `cu121` failure language; report tested compatibility. (GPT)
- Treat “~30 minutes setup” as aspirational, not a gate. (Composer, GPT)
- Explicit load/unload / quantized KV notes for generator+embed+rerank on 16GB. (Gemini)

### Nits
- Document LlamaIndex surface area used (rip-out path). (Composer)
- Pin concrete license/sha256 manifest rules for public mirrors. (GPT)
- Specify unsupported-citation threshold. (GPT)

---

## Critical feedback — Grok

### Blocking
- Missing Blackwell `sm_120` / CUDA 12.8 / `cu128` guidance. (all 3)
- Scripture chunking “1–4 verses” weakens verse-level citations. (Composer, GPT)
- Dense-only retrieval without BM25/hybrid/rerank weak for exact-phrase lookup. (Composer, GPT)
- No programmatic citation validator / retrieval-set check. (all 3)
- `instruct_pairs.py` lacks restricted-source exclusion → Conference/CFM can enter SFT. (Composer, GPT, Gemini)
- No meaningful groundedness/refusal eval before QLoRA/hybrid. (Composer, GPT, Gemini)

### Non-blocking
- Open runtime questions unresolved; vLLM as easy Windows option is misleading. (GPT)
- Invalid/weak fallback model naming (Llama 3.2 8B Instruct). (GPT)
- Soft step-1 “tree exists conceptually” and “document skip if no GPU” weaken gates. (Composer, GPT)
- Grep-only copyright gate is easily bypassed. (GPT)

### Nits
- Axolotl/LangChain optional noise; `compileall` alone is a weak gate. (Composer, GPT)

---

## Cross-cutting risks

- **16GB VRAM contention** with generator + embedder + reranker + context growth.
- **Blackwell + Windows + Unsloth/bitsandbytes** fragility even with correct CUDA pins.
- **Public-domain mirror quality** (versification/typos) and edition/formatting copyright nuance.
- **Music/choir** mentioned by both plans without a defined legal hymn corpus.
- **Accidental restricted-content commits** if CI/gitignore allowlists are wrong.

---

## Steal list — fold into winner before execute

| Steal | Consensus | Notes |
|-------|-----------|-------|
| Explicit PR1–PR4 (further split QLoRA vs hybrid/docs) | 3/3 | Map onto Claude steps; CLI-first |
| CLI-first; defer FastAPI UI to later PR | 3/3 | Composer + GPT strongly |
| Qwen2.5-14B as interim default until eval | 2/3 | Composer; Gemini noted nomic embed alt |
| `docs/ARCHITECTURE.md` hybrid user flow | 1/3+ | Composer |
| Fixture-driven acceptance tests early in data PR | 2/3 | GPT + Composer spirit |
| Open-questions → short Decisions appendix | 1/3 | Composer |
| `nomic-embed-text-v1.5` as light embed alternate in config | 1/3 | Gemini |
| Narrower “starter design” framing for v1 | 1/3 | GPT |

### Split opinion
| Steal | Notes |
|-------|-------|
| Keep Grok’s simpler completeness score as a warning | GPT preferred Grok on scope; still lose on safety |

---

## Pre-execute checklist

- [ ] Adopt Claude as baseline; import Grok PR split (skeleton/legal → data+tests → RAG CLI → QLoRA; UI later)
- [ ] Defer `serve` UI and `music` mode from v1 MVP
- [ ] Fix legal language: per-source license verification; remove/constrain `--allow-restricted`
- [ ] Specify citation failure behavior (regen / refuse / fail — no silent strip)
- [ ] Keep `sm_120` + `cu128` + `check_env.py`; add WSL2 finetune fallback notes
- [ ] Set interim generator default (Qwen2.5-14B or documented Qwen3) + eval shortlist
- [ ] Pick vector store (Chroma) for v1; keep verse-atomic + hybrid retrieval + citation validator
- [ ] Resolve package name / extras vs install story; fix `data/` CI allowlist for `.gitkeep`/README
- [ ] Ensure SFT path hard-excludes `redistributable: false` by default

---

## Recommended next step

1. Treat the **Claude** plan as the execution baseline.
2. Incorporate steal-list + Claude blocking feedback (revise plan in place via Claude Code).
3. Then implement in a normal agent session — do **not** implement until the winner plan is updated.

---

## Evaluator session links

- [Composer](6a8f4a0b-fbad-43f8-a8a5-30945ce340ed)
- [GPT](425e2762-5c38-445f-9349-4e49fc5f1f21)
- [Gemini](a7c1f649-dee3-4101-b1ca-da371f8679ba)
