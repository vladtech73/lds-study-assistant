"""Merge LoRA adapter, export GGUF, register with Ollama for the hybrid ask path.

After export, set ``generator.adapter`` in configs/models.yaml to the adapter
directory (reads ``ollama_tag``) or to the Ollama model name directly.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from lds_study.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_TAG = "lds-study-adapter"


def write_ollama_tag(adapter_dir: Path, tag: str) -> Path:
    path = adapter_dir / "ollama_tag"
    path.write_text(tag.strip() + "\n", encoding="utf-8")
    return path


def read_ollama_tag(adapter_dir: Path) -> str | None:
    path = adapter_dir / "ollama_tag"
    if not path.is_file():
        return None
    tag = path.read_text(encoding="utf-8").strip()
    return tag or None


def write_modelfile(adapter_dir: Path, *, from_gguf: Path, system: str | None = None) -> Path:
    lines = [f"FROM {from_gguf.resolve().as_posix()}"]
    if system:
        # Ollama SYSTEM lines are plain text; keep short.
        escaped = system.replace('"""', "")
        lines.append(f'SYSTEM """{escaped}"""')
    path = adapter_dir / "Modelfile"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def register_ollama_model(
    *,
    adapter_dir: Path,
    tag: str,
    modelfile: Path,
    dry_run: bool = False,
) -> None:
    cmd = ["ollama", "create", tag, "-f", str(modelfile)]
    if dry_run:
        logger.info("Dry run: would execute %s", " ".join(cmd))
        write_ollama_tag(adapter_dir, tag)
        return
    subprocess.run(cmd, check=True, cwd=str(adapter_dir))
    write_ollama_tag(adapter_dir, tag)


def merge_and_export(
    *,
    adapter_dir: Path,
    base_model: str,
    ollama_tag: str = DEFAULT_OLLAMA_TAG,
    gguf_name: str = "merged-q4_k_m.gguf",
    dry_run: bool = False,
    skip_ollama: bool = False,
) -> Path:
    """Merge PEFT adapter into base, save GGUF, optionally ``ollama create``.

    ``dry_run`` writes a placeholder Modelfile + ``ollama_tag`` without GPU/merge.
    """
    adapter_dir = adapter_dir.resolve()
    if not adapter_dir.is_dir():
        raise FileNotFoundError(f"Adapter directory not found: {adapter_dir}")

    gguf_path = adapter_dir / gguf_name
    meta = {
        "base_model": base_model,
        "adapter_dir": str(adapter_dir),
        "ollama_tag": ollama_tag,
        "gguf": str(gguf_path),
        "dry_run": dry_run,
    }
    (adapter_dir / "export_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    if dry_run:
        # Placeholder FROM so Modelfile exists for wiring tests; real export replaces it.
        write_modelfile(adapter_dir, from_gguf=gguf_path)
        write_ollama_tag(adapter_dir, ollama_tag)
        logger.info(
            "Dry run: wrote Modelfile + ollama_tag=%s (no merge/GGUF).", ollama_tag
        )
        return adapter_dir

    try:
        from unsloth import FastLanguageModel
    except ImportError as exc:
        raise SystemExit(
            'Install fine-tune deps: pip install -e ".[finetune]". '
            "See docs/FINETUNE_WINDOWS.md."
        ) from exc

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(adapter_dir),
        max_seq_length=2048,
        load_in_4bit=True,
        dtype=None,
    )
    # Save merged 16-bit then GGUF (Unsloth helper).
    merged_dir = adapter_dir / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained_merged(
        str(merged_dir),
        tokenizer,
        save_method="merged_16bit",
    )
    try:
        model.save_pretrained_gguf(
            str(adapter_dir),
            tokenizer,
            quantization_method="q4_k_m",
        )
    except Exception as exc:  # noqa: BLE001 — surface path for llama.cpp fallback
        logger.warning(
            "Unsloth GGUF export failed (%s). Merged weights are in %s; "
            "convert with llama.cpp and point Modelfile FROM at the GGUF.",
            exc,
            merged_dir,
        )

    # Prefer an existing .gguf under adapter_dir if Unsloth renamed the file.
    found = sorted(adapter_dir.glob("*.gguf"))
    if found:
        gguf_path = found[0]

    modelfile = write_modelfile(adapter_dir, from_gguf=gguf_path)
    if not skip_ollama:
        register_ollama_model(
            adapter_dir=adapter_dir,
            tag=ollama_tag,
            modelfile=modelfile,
            dry_run=False,
        )
    else:
        write_ollama_tag(adapter_dir, ollama_tag)
    return adapter_dir


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    settings = get_settings()
    models_cfg = settings.load_yaml("models.yaml")
    gen = models_cfg.get("generator") or {}
    default_base = str(gen.get("hf_id") or "")

    parser = argparse.ArgumentParser(
        description="Merge LoRA, export GGUF, register Ollama tag for hybrid ask."
    )
    parser.add_argument(
        "--adapter",
        type=Path,
        default=None,
        help="Adapter dir from train_qlora (default: adapters/lds-qlora)",
    )
    parser.add_argument(
        "--base-model",
        default=None,
        help="HF base id (default: generator.hf_id)",
    )
    parser.add_argument(
        "--ollama-tag",
        default=DEFAULT_OLLAMA_TAG,
        help=f"Ollama model name (default: {DEFAULT_OLLAMA_TAG})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write Modelfile + ollama_tag only (no GPU merge).",
    )
    parser.add_argument(
        "--skip-ollama",
        action="store_true",
        help="Skip `ollama create` (still writes ollama_tag).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    adapter_dir = args.adapter or settings.resolve(Path("adapters") / "lds-qlora")
    base = args.base_model or default_base
    if not base and not args.dry_run:
        print("train failed: --base-model / generator.hf_id required", file=sys.stderr)
        return 1
    try:
        merge_and_export(
            adapter_dir=adapter_dir,
            base_model=base or "dry-run",
            ollama_tag=args.ollama_tag,
            dry_run=args.dry_run,
            skip_ollama=args.skip_ollama,
        )
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return 1
    tag = read_ollama_tag(adapter_dir) or args.ollama_tag
    print(f"Adapter ready. Set generator.adapter to '{adapter_dir}' or Ollama tag '{tag}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
