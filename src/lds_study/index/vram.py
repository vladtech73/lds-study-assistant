"""VRAM helpers and Ollama unload for index/ask discipline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from rich.console import Console

console = Console()


def device_vram_used_gb() -> float | None:
    """Device-level used VRAM in GiB (total - free), including other CUDA processes."""
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    try:
        free_b, total_b = torch.cuda.mem_get_info()
        return float(total_b - free_b) / (1024**3)
    except Exception:  # noqa: BLE001 — best-effort telemetry
        return None


def process_vram_allocated_gb() -> float | None:
    """This process's PyTorch allocator peak (excludes Ollama and other processes)."""
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    try:
        torch.cuda.synchronize()
        return float(torch.cuda.max_memory_allocated()) / (1024**3)
    except Exception:  # noqa: BLE001
        return None


def peak_vram_gb() -> float | None:
    """Headline VRAM figure: prefer device occupancy, else in-process allocator."""
    device = device_vram_used_gb()
    if device is not None:
        return device
    return process_vram_allocated_gb()


def reset_peak_vram() -> None:
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()


def unload_ollama_generator(host: str, model_id: str | None = None) -> None:
    """Ask Ollama to drop resident models so embedding can claim VRAM.

    Uses keep_alive=0 generate ping (supported broadly) and best-effort /api/ps unload.
    Failures are logged but non-fatal — index can proceed if Ollama is down.
    """
    host = host.rstrip("/")
    models = _running_ollama_models(host)
    targets = models
    if model_id:
        targets = list({*models, model_id})
    if not targets and model_id:
        targets = [model_id]
    for name in targets:
        _keep_alive_zero(host, name)


def _running_ollama_models(host: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"{host}/api/ps", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    models: list[str] = []
    for item in data.get("models") or []:
        name = item.get("name") or item.get("model")
        if name:
            models.append(str(name))
    return models


def _keep_alive_zero(host: str, model: str) -> None:
    payload = json.dumps(
        {"model": model, "prompt": "", "keep_alive": 0, "stream": False}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        console.print(f"[dim]Unloaded Ollama model {model} (keep_alive=0)[/dim]")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        console.print(f"[yellow]Ollama unload skipped for {model}:[/yellow] {exc}")


def log_peak_vram(verbose: bool, label: str = "peak VRAM") -> float | None:
    """Log device + process VRAM when verbose; return device occupancy as headline."""
    device = device_vram_used_gb()
    process = process_vram_allocated_gb()
    if verbose:
        if device is not None:
            console.print(f"[cyan]{label} (device used):[/cyan] {device:.2f} GiB")
        if process is not None:
            console.print(
                f"[cyan]{label} (this process PyTorch):[/cyan] {process:.2f} GiB"
            )
        if device is None and process is None:
            console.print(f"[dim]{label}: CUDA unavailable[/dim]")
    return device if device is not None else process


def cuda_device_name() -> str | None:
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    return torch.cuda.get_device_name(0)
