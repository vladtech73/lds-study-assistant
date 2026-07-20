#!/usr/bin/env python3
"""Thin wrapper around lds_study.pull_models."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running without install: add src/ to path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _main() -> int:
    from lds_study.pull_models import main

    return main()


if __name__ == "__main__":
    sys.exit(_main())
