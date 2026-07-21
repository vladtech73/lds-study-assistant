# LDS Study Assistant

> **Unofficial. Not affiliated with or endorsed by The Church of Jesus Christ of
> Latter-day Saints.** See [DISCLAIMER.md](DISCLAIMER.md) and [NOTICE.md](NOTICE.md).

Private, **local**, CLI-first study assistant for scripture Q&A with **citations**.
Designed for an RTX 5070 Ti 16GB (Blackwell `sm_120`) on Windows.

v1 is **RAG-first** (retrieve then answer). Optional QLoRA is for response *style*,
not facts, and lands in a later PR.

## What this repo does and does not contain

| Contains | Does not contain |
|---|---|
| Code, configs, docs | Conference / Come Follow Me full texts |
| License-verified public source *pipelines* (PR2+) | Built indexes or model weights |
| Tiny test fixtures (PR2+) | Scrapers of Church sites by default |

Bring your own Conference/CFM files into gitignored `data/raw/user/` only.

## Hardware notes

- **GPU:** RTX 5070 Ti 16GB → needs **CUDA 12.8+** and a **`cu128`** (or newer) PyTorch wheel.
- Run `python scripts/check_env.py` to report GPU name, CUDA, torch build, VRAM, and Ollama.
- Non-cu128 builds get a **warning** with the exact fix command; the script exits non-zero
  only when no usable CUDA device is found.
- Fine-tuning on Windows is fragile — see [docs/FINETUNE_WINDOWS.md](docs/FINETUNE_WINDOWS.md)
  (WSL2 fallback documented from day one). Native RAG does **not** need Unsloth.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# Install the package first, then force the Blackwell cu128 torch wheel
# (editable install can otherwise pull a CPU torch via sentence-transformers).
pip install -e ".[dev]"
pip install --index-url https://download.pytorch.org/whl/cu128 torch
# Optional equivalent: pip install -r requirements-cu128.txt
.\.venv\Scripts\python.exe scripts\check_env.py
# Re-run check_env after any dependency change that might reinstall torch.
.\.venv\Scripts\python.exe scripts\pull_models.py --dry-run
# First prepare downloads the license-verified scripture JSON (~18MB) into data/raw/public/
.\.venv\Scripts\python.exe -m lds_study.cli prepare --scripture-only --stats
```

`pull-models` downloads the Ollama generator tag plus embed/rerank weights.
Full Hugging Face generator weights (~28GB) are **not** pulled by default — only with
`--include-finetune-weights` (QLoRA / PR5; see [docs/FINETUNE_WINDOWS.md](docs/FINETUNE_WINDOWS.md)).

`prepare` writes `data/processed/chunks.jsonl` (gitignored).

```powershell
# Embed + BM25 under indexes/default/ (gitignored). Unloads Ollama first.
.\.venv\Scripts\python.exe -m lds_study.cli index --profile default --verbose
# Optional: 10/10 phrase smoke on the full corpus (IdentityReranker; real BGE-M3 required)
# .\.venv\Scripts\python.exe -m lds_study.cli index --profile default --smoke

.\.venv\Scripts\python.exe -m lds_study.cli ask "What does Alma teach about experimenting upon the word?"
# Useful flags: --mode study|lesson|talk  --strict  --show-context  --json
# Filters: --volume bofm --book alma --source-type scripture --date-from/--date-to
```

### Answer statuses and exit codes

| Status | Exit | Meaning |
|---|---|---|
| `ok` | 0 | Answer returned; every `[[chunk_id]]` is in the retrieved set and coverage ≥ `citation.min_coverage` |
| `unsupported` | 2 | Citation gate still failing after one regenerate (or immediately with `--strict`); sources listed, no synthesized prose |
| `no_evidence` | 3 | Nothing retrieved above `retrieval.min_score` — refuse before generating |

Hardware note: quantized KV cache (`kv_cache_quant` in `configs/models.yaml`) is **server-side** — set `OLLAMA_KV_CACHE_TYPE=q8_0` in the Ollama environment.

Optional pre-commit (copyright gate on every commit):

```powershell
pip install pre-commit
pre-commit install
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): `prepare → index → ask` (+ optional eval/tune).

## Legal

Per-source license verification (no blanket "scripture is public domain" claim):
[docs/LEGAL.md](docs/LEGAL.md).

## Model card

Template: [MODEL_CARD.md](MODEL_CARD.md) (filled as eval results land).

## License

[MIT](LICENSE) for **code only**. Third-party texts retain their own rights.
