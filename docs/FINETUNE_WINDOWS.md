# Fine-tuning on Windows (Blackwell / sm_120)

RAG (`pip install -e .`) does **not** need this document. Fine-tuning
(`pip install -e ".[finetune]"`) is optional and lands in **PR5**.

bitsandbytes / Unsloth / Triton on **RTX 50-series (sm_120) + native Windows** are the
most fragile part of the stack. Documented from day one so you are not stuck mid-train.

## Path A — Native Windows (try first)

1. Install CUDA Toolkit **12.8+**.
2. Create `.venv` and install:

   ```powershell
   pip install -e ".[finetune]"
   pip install --index-url https://download.pytorch.org/whl/cu128 torch
   # or: pip install -r requirements-cu128.txt  (after editable install)
   ```

3. Run `python scripts/check_env.py` and confirm a usable CUDA device + cu128-ish torch.
4. After PR5: run the train entrypoint with `--max-steps 20` for a debug slice.

### Pulling HF generator weights (large)

RAG uses Ollama (`qwen2.5:14b`) and does **not** need the ~28GB Hugging Face
`generator.hf_id` snapshot. Only when preparing for Unsloth/QLoRA:

```powershell
.\.venv\Scripts\python.exe scripts\pull_models.py --include-finetune-weights
# or: lds pull-models --include-finetune-weights
```

### Known failure signatures (native)

| Symptom | Likely cause | Next step |
|---|---|---|
| `CUDA error: no kernel image is available` | Torch wheel predates sm_120 | Reinstall from `requirements-cu128.txt` |
| bitsandbytes DLL / Triton compile errors | Windows + sm_120 gaps | **Use Path B (WSL2)** |
| OOM during QLoRA on 14B | VRAM | Drop to 7–8B base or shorten `seq` |

## Path B — WSL2 fallback (recommended if Path A fails)

1. Install WSL2 + Ubuntu 24.04 and NVIDIA CUDA on WSL (same 12.8+ driver/toolkit story).
2. Clone the repo inside the Linux filesystem (`~/…`), not a slow `/mnt/d` working tree if possible.
3. Same commands:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-cu128.txt
   pip install -e ".[finetune]"
   python scripts/check_env.py
   # PR5: identical train_qlora.py invocation as on Windows
   ```

Adapters trained on **restricted** (`redistributable: false`) material must **never** be
published. The dataset builder excludes them unconditionally (no override flag).
