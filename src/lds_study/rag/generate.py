"""Generator backends — Ollama chat + injectable mock for tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from rich.console import Console

console = Console()


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


def build_ollama_generator(models_cfg: dict, host: str) -> OllamaGenerator:
    gen = models_cfg.get("generator") or {}
    model = str(gen.get("id") or "")
    if not model:
        raise ValueError("generator.id missing in configs/models.yaml")
    return OllamaGenerator(
        host=host,
        model=model,
        num_ctx=int(gen.get("num_ctx") or 8192),
        keep_alive=str(gen.get("keep_alive") or "5m"),
    )
