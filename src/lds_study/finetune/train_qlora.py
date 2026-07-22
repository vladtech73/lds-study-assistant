"""QLoRA training via Unsloth (optional ``[finetune]`` extra).

Hyperparams target a 14B 4-bit base on 16GB VRAM:
  LoRA r=16 / α=32 on attn+MLP, grad checkpointing, batch 1 + accum 8, seq 2048,
  ~2–3 epochs (or ``--max-steps`` for a debug slice).

If you OOM on 14B, drop to a 7–8B instruct base (set ``--base-model``) or shorten
``--max-seq-length``.

Native Windows + sm_120 may fail bitsandbytes/Triton — see docs/FINETUNE_WINDOWS.md
(WSL2 path runs this same script).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

from lds_study.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_LORA_R = 16
DEFAULT_LORA_ALPHA = 32
DEFAULT_BATCH = 1
DEFAULT_GRAD_ACCUM = 8
DEFAULT_SEQ = 2048
DEFAULT_EPOCHS = 2.0

_ROLE_MAP = {
    "human": "user",
    "gpt": "assistant",
    "user": "user",
    "assistant": "assistant",
    "system": "system",
}


def conversations_to_messages(turns: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """Map ShareGPT ``from``/``value`` turns to chat ``role``/``content`` messages."""
    messages: list[dict[str, str]] = []
    for turn in turns:
        raw = str(turn.get("from") or turn.get("role") or "user").lower()
        role = _ROLE_MAP.get(raw, "user")
        content = str(turn.get("value") or turn.get("content") or "")
        messages.append({"role": role, "content": content})
    return messages


def messages_from_row(row: dict[str, Any]) -> list[dict[str, str]]:
    if "messages" in row and row["messages"] is not None:
        return conversations_to_messages(row["messages"])
    conv = row.get("conversations")
    if not conv:
        raise ValueError("row needs ShareGPT 'conversations' or chat 'messages'")
    return conversations_to_messages(conv)


def format_chat_text(tokenizer: Any, messages: Sequence[dict[str, str]]) -> str:
    """Render training text via the tokenizer chat template when available.

    Falls back to a plain role/content dump only if ``apply_chat_template`` is missing
    (should not happen for Qwen instruct tokenizers).
    """
    apply = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply):
        text = apply(
            list(messages),
            tokenize=False,
            add_generation_prompt=False,
        )
        return str(text)
    parts = [f"{m['role']}: {m['content']}" for m in messages]
    return "\n".join(parts)


def make_formatting_func(tokenizer: Any):
    """Batched SFTTrainer formatting_func that uses the chat template."""

    def _formatting(examples: dict[str, Any]) -> list[str]:
        texts: list[str] = []
        conversations = examples.get("conversations")
        if conversations is not None:
            for conv in conversations:
                messages = conversations_to_messages(conv)
                texts.append(format_chat_text(tokenizer, messages))
            return texts
        for messages in examples["messages"]:
            texts.append(format_chat_text(tokenizer, conversations_to_messages(messages)))
        return texts

    return _formatting


def _require_finetune_deps() -> None:
    missing: list[str] = []
    for mod in ("unsloth", "peft", "trl", "datasets", "torch"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise SystemExit(
            "Missing fine-tune dependencies: "
            + ", ".join(missing)
            + '. Install with: pip install -e ".[finetune]" '
            "(and a cu128 torch wheel). See docs/FINETUNE_WINDOWS.md."
        )


def resolve_base_model(models_cfg: dict[str, Any], override: str | None) -> str:
    if override:
        return override
    gen = models_cfg.get("generator") or {}
    hf_id = gen.get("hf_id")
    if not hf_id:
        raise ValueError(
            "generator.hf_id missing in configs/models.yaml "
            "(needed for Unsloth; pull with --include-finetune-weights)"
        )
    return str(hf_id)


def validate_sft_jsonl(path: Path, *, min_rows: int = 1) -> int:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing SFT dataset: {path}. Run `lds finetune-dataset` first."
        )
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if "conversations" not in row and "messages" not in row:
                raise ValueError(
                    f"{path}:{line_no}: expected ShareGPT 'conversations' or chat 'messages'"
                )
            count += 1
    if count < min_rows:
        raise ValueError(f"{path} has {count} rows; need at least {min_rows}")
    return count


def run_train(
    *,
    data_path: Path,
    output_dir: Path,
    base_model: str,
    max_steps: int | None = None,
    num_train_epochs: float = DEFAULT_EPOCHS,
    max_seq_length: int = DEFAULT_SEQ,
    lora_r: int = DEFAULT_LORA_R,
    lora_alpha: int = DEFAULT_LORA_ALPHA,
    per_device_train_batch_size: int = DEFAULT_BATCH,
    gradient_accumulation_steps: int = DEFAULT_GRAD_ACCUM,
    dry_run: bool = False,
) -> Path:
    """Train a LoRA adapter. With ``dry_run=True``, only validate inputs."""
    n = validate_sft_jsonl(data_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "base_model": base_model,
        "data_path": str(data_path),
        "rows": n,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "max_seq_length": max_seq_length,
        "per_device_train_batch_size": per_device_train_batch_size,
        "gradient_accumulation_steps": gradient_accumulation_steps,
        "max_steps": max_steps,
        "num_train_epochs": None if max_steps else num_train_epochs,
        "dry_run": dry_run,
    }
    (output_dir / "train_config.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    if dry_run:
        logger.info("Dry run OK (%s rows). Skipping Unsloth train.", n)
        return output_dir

    _require_finetune_deps()

    # Heavy imports only when actually training.
    import torch
    from datasets import load_dataset
    from unsloth import FastLanguageModel
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for QLoRA. On native Windows sm_120 failures, "
            "use the WSL2 path in docs/FINETUNE_WINDOWS.md."
        )

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
        dtype=None,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    dataset = load_dataset("json", data_files=str(data_path), split="train")
    formatting_func = make_formatting_func(tokenizer)

    args_kw: dict[str, Any] = {
        "output_dir": str(output_dir),
        "per_device_train_batch_size": per_device_train_batch_size,
        "gradient_accumulation_steps": gradient_accumulation_steps,
        "warmup_steps": 5,
        "learning_rate": 2e-4,
        "fp16": not torch.cuda.is_bf16_supported(),
        "bf16": torch.cuda.is_bf16_supported(),
        "logging_steps": 1,
        "optim": "adamw_8bit",
        "seed": 42,
        "report_to": "none",
    }
    if max_steps is not None:
        args_kw["max_steps"] = int(max_steps)
    else:
        args_kw["num_train_epochs"] = float(num_train_epochs)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        formatting_func=formatting_func,
        args=SFTConfig(**args_kw),
    )
    trainer.train()
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    logger.info("Adapter saved to %s", output_dir)
    return output_dir


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    settings = get_settings()
    models_cfg = settings.load_yaml("models.yaml")

    parser = argparse.ArgumentParser(description="QLoRA train (Unsloth) for style adapters.")
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="SFT JSONL (default: data/processed/sft.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Adapter output dir (default: adapters/lds-qlora)",
    )
    parser.add_argument(
        "--base-model",
        default=None,
        help="HF model id override (default: generator.hf_id)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Debug slice (e.g. 20). Overrides epochs when set.",
    )
    parser.add_argument("--epochs", type=float, default=DEFAULT_EPOCHS)
    parser.add_argument("--max-seq-length", type=int, default=DEFAULT_SEQ)
    parser.add_argument("--lora-r", type=int, default=DEFAULT_LORA_R)
    parser.add_argument("--lora-alpha", type=int, default=DEFAULT_LORA_ALPHA)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate dataset + write train_config.json without loading Unsloth.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    data_path = args.data or settings.resolve(
        settings.data_dir / "processed" / "sft.jsonl"
    )
    output_dir = args.output or settings.resolve(Path("adapters") / "lds-qlora")
    base = resolve_base_model(models_cfg, args.base_model)

    try:
        run_train(
            data_path=data_path,
            output_dir=output_dir,
            base_model=base,
            max_steps=args.max_steps,
            num_train_epochs=args.epochs,
            max_seq_length=args.max_seq_length,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"train failed: {exc}", file=sys.stderr)
        return 1
    print(f"Adapter directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
