#!/usr/bin/env python3
"""Fail if paths under data/, indexes/, or models/ leave the structural allowlist.

Allowlist (must stay tight — review any change carefully):
  - data/**/.gitkeep
  - data/README.md
  - data/raw/user/EXAMPLE.meta.json
  - indexes/.gitkeep, models/.gitkeep, outputs/.gitkeep

Eval markdown under outputs/eval/ is intentionally *not* monitored (PR4 commits reports).
Content under indexes/ and models/ remains blocked.

Usage:
  python scripts/check_staged_data.py              # git staged files (fails closed if git broken)
  python scripts/check_staged_data.py --paths a b  # explicit paths (tests / CI)
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys

MONITORED_PREFIXES = ("data/", "indexes/", "models/")

ALLOWLIST_PATTERNS = (
    "data/**/.gitkeep",
    "data/.gitkeep",
    "data/README.md",
    "data/raw/user/EXAMPLE.meta.json",
    "indexes/.gitkeep",
    "models/.gitkeep",
    "outputs/.gitkeep",
)


class GitUnavailableError(RuntimeError):
    """Raised when staged paths cannot be verified via git."""


def normalize(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p.removeprefix("./")
    return p


def is_monitored(path: str) -> bool:
    p = normalize(path)
    return any(p == prefix.rstrip("/") or p.startswith(prefix) for prefix in MONITORED_PREFIXES)


def is_allowed(path: str) -> bool:
    p = normalize(path)
    return any(fnmatch.fnmatch(p, pattern) for pattern in ALLOWLIST_PATTERNS)


def staged_paths() -> list[str]:
    """Return staged paths, or raise GitUnavailableError if git cannot be queried."""
    if shutil.which("git") is None:
        raise GitUnavailableError("git is not on PATH; cannot verify staged files")

    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        err = (probe.stderr or probe.stdout or "").strip()
        raise GitUnavailableError(
            "not a git repository (run git init); cannot verify staged files"
            + (f": {err}" if err else "")
        )

    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise GitUnavailableError(
            "cannot verify staged files "
            f"(git exited {result.returncode}"
            + (f": {err}" if err else "")
            + ")"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_paths(paths: list[str]) -> list[str]:
    bad: list[str] = []
    for path in paths:
        if is_monitored(path) and not is_allowed(path):
            bad.append(normalize(path))
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="+",
        default=None,
        help="Explicit paths to check (skip git staged). Useful in tests/CI.",
    )
    args = parser.parse_args(argv)

    if args.paths is not None:
        paths = list(args.paths)
    else:
        try:
            paths = staged_paths()
        except GitUnavailableError as exc:
            print(f"ERROR: {exc}")
            return 2

    bad = check_paths(paths)
    if bad:
        print("ERROR: restricted paths staged (not on structural allowlist):")
        for p in bad:
            print(f"  - {p}")
        print(
            "\nAllowed structural paths only: data/**/.gitkeep, data/README.md, "
            "data/raw/user/EXAMPLE.meta.json, indexes/.gitkeep, models/.gitkeep, "
            "outputs/.gitkeep."
        )
        return 1

    print(f"OK — {len(paths)} path(s) checked; no allowlist violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
