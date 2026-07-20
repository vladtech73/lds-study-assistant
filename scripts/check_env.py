#!/usr/bin/env python3
"""Report CUDA / GPU / torch / Ollama environment for RTX 50-series (sm_120).

Exit codes:
  0 — at least one usable CUDA device (or --allow-cpu for CPU-only CI)
  1 — no usable CUDA device and --allow-cpu not set
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys


def _ollama_version() -> str:
    ollama = shutil.which("ollama")
    if not ollama:
        return "not found on PATH"
    try:
        out = subprocess.run(
            [ollama, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        text = (out.stdout or out.stderr or "").strip()
        return text or "found (version unknown)"
    except OSError as exc:
        return f"error: {exc}"


def _torch_info() -> dict[str, object]:
    info: dict[str, object] = {
        "installed": False,
        "version": None,
        "cuda_compiled": None,
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
        "looks_like_cu128": None,
        "warning": None,
    }
    try:
        import torch
    except ImportError:
        info["warning"] = "torch not installed — pip install -r requirements-cu128.txt"
        return info

    info["installed"] = True
    info["version"] = torch.__version__
    info["cuda_compiled"] = getattr(torch.version, "cuda", None)
    info["cuda_available"] = bool(torch.cuda.is_available())
    info["device_count"] = int(torch.cuda.device_count()) if info["cuda_available"] else 0

    # Heuristic: cu128 wheels usually advertise cuda 12.8+ in torch.version.cuda
    compiled = str(info["cuda_compiled"] or "")
    m = re.match(r"^(\d+)\.(\d+)", compiled)
    if m:
        major, minor = int(m.group(1)), int(m.group(2))
        info["looks_like_cu128"] = (major, minor) >= (12, 8)
    else:
        info["looks_like_cu128"] = False

    if info["installed"] and info["looks_like_cu128"] is False:
        info["warning"] = (
            "Installed torch does not look like a cu128+ build "
            f"(torch.version.cuda={compiled!r}). On RTX 5070 Ti (sm_120) prefer:\n"
            "  pip install --index-url https://download.pytorch.org/whl/cu128 torch"
        )

    devices = []
    if info["cuda_available"]:
        for i in range(int(info["device_count"])):
            props = torch.cuda.get_device_properties(i)
            free_b, total_b = torch.cuda.mem_get_info(i)
            major, minor = props.major, props.minor
            devices.append(
                {
                    "index": i,
                    "name": props.name,
                    "capability": f"sm_{major}{minor}",
                    "total_vram_gb": round(total_b / (1024**3), 2),
                    "free_vram_gb": round(free_b / (1024**3), 2),
                }
            )
    info["devices"] = devices
    return info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="Exit 0 even when no CUDA device is present (CI / docs machines).",
    )
    args = parser.parse_args(argv)

    print("=== lds_study environment check ===")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Ollama: {_ollama_version()}")

    info = _torch_info()
    print(f"torch installed: {info['installed']}")
    if info["installed"]:
        print(f"torch version: {info['version']}")
        print(f"torch.version.cuda (compiled): {info['cuda_compiled']}")
        print(f"looks like cu128+: {info['looks_like_cu128']}")
        print(f"cuda.is_available: {info['cuda_available']}")
        print(f"device_count: {info['device_count']}")
        for d in info["devices"]:  # type: ignore[union-attr]
            print(
                f"  [{d['index']}] {d['name']}  {d['capability']}  "
                f"VRAM free/total {d['free_vram_gb']}/{d['total_vram_gb']} GiB"
            )

    if info.get("warning"):
        print(f"\nWARNING: {info['warning']}")

    usable = bool(info["cuda_available"] and info["device_count"])
    if usable:
        print("\nResult: OK — usable CUDA device found.")
        return 0

    if args.allow_cpu:
        print("\nResult: OK (--allow-cpu); no usable CUDA device.")
        return 0

    print(
        "\nResult: FAIL — no usable CUDA device. "
        "Install a cu128+ torch wheel and NVIDIA drivers, then re-run."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
