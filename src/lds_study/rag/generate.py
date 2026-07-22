"""Generator backends — Ollama chat + injectable mock for tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rich.console import Console

console = Console()


def resolve_generator_model_id(models_cfg: dict, *, root: Path | None = None) -> str:
    """Resolve Ollama model id, honoring optional ``generator.adapter``.

    ``adapter`` may be:
    - ``null`` / empty — use ``generator.id``
    - a directory containing ``ollama_tag`` (written by merge_and_export)
    - an Ollama model tag string (no path separators, or a non-existent path)
    """
    gen = models_cfg.get("generator") or {}
    base_id = str(gen.get("id") or "").strip()
    if not base_id:
        raise ValueError("generator.id missing in configs/models.yaml")

    raw = gen.get("adapter")
    if raw is None:
        return base_id
    adapter = str(raw).strip()
    if not adapter or adapter.lower() in {"null", "none"}:
        return base_id

    candidate = Path(adapter)
    if root is not None and not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.expanduser()
        if not candidate.is_absolute():
            candidate = candidate.resolve()

    if candidate.is_dir():
        tag_file = candidate / "ollama_tag"
        if tag_file.is_file():
            tag = tag_file.read_text(encoding="utf-8").strip()
            if tag:
                return tag
        raise ValueError(
            f"generator.adapter directory {candidate} has no ollama_tag file. "
            "Run merge_and_export.py (or set adapter to an Ollama model name)."
        )

    # Treat as Ollama tag (e.g. lds-study-adapter).
    return adapter


class Generator(Protocol):
    def complete(self, *, system: str, user: str, temperature: float) -> str:
        """Return assistant text for one turn."""


@dataclass
class OllamaGenerator:
    host: str
    model: str
    num_ctx: int = 8192
    keep_alive: str = "5m"

    def complete(self, *, system: str, user: str, temperature: float) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host.rstrip('/')}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        message = body.get("message") or {}
        content = message.get("content")
        if not content:
            # Some models put text in `response`
            content = body.get("response")
        if not content:
            raise RuntimeError(f"Ollama returned empty content: {body!r}")
        return str(content).strip()


@dataclass
class ScriptedGenerator:
    """Deterministic generator for unit tests — pops scripted replies in order."""

    replies: list[str]
    calls: list[dict] | None = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    def complete(self, *, system: str, user: str, temperature: float) -> str:
        assert self.calls is not None
        self.calls.append(
            {"system": system, "user": user, "temperature": temperature}
        )
        if not self.replies:
            raise RuntimeError("ScriptedGenerator exhausted replies")
        return self.replies.pop(0)


def build_ollama_generator(
    models_cfg: dict,
    host: str,
    *,
    root: Path | None = None,
) -> OllamaGenerator:
    gen = models_cfg.get("generator") or {}
    model = resolve_generator_model_id(models_cfg, root=root)
    return OllamaGenerator(
        host=host,
        model=model,
        num_ctx=int(gen.get("num_ctx") or 8192),
        keep_alive=str(gen.get("keep_alive") or "5m"),
    )
