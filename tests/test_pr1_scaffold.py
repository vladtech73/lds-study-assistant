"""PR1 tests: copyright allowlist gate + smoke imports + pull dry-run."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_staged_data.py"


def test_allowlist_accepts_structural_files() -> None:
    code = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--paths",
            "data/README.md",
            "data/raw/public/.gitkeep",
            "data/raw/user/EXAMPLE.meta.json",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert code.returncode == 0, code.stdout + code.stderr


def test_allowlist_rejects_user_corpus_file() -> None:
    code = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--paths",
            "data/raw/user/test.txt",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert code.returncode == 1
    assert "data/raw/user/test.txt" in code.stdout


def test_allowlist_rejects_indexes_and_models() -> None:
    code = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--paths",
            "indexes/default/chroma.sqlite3",
            "models/Qwen--Qwen2.5-14B-Instruct/config.json",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert code.returncode == 1


def test_allowlist_allows_eval_markdown() -> None:
    """outputs/eval reports are not monitored (PR4 commits them)."""
    code = subprocess.run(
        [
            sys.executable,
            str(CHECK),
            "--paths",
            "outputs/eval/2026-07-20.md",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert code.returncode == 0, code.stdout + code.stderr


def test_staged_paths_fail_closed_when_git_errors() -> None:
    import scripts.check_staged_data as gate

    with patch.object(gate.shutil, "which", return_value="git"):
        with patch.object(
            gate.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=128, stdout="", stderr="not a git repository"),
        ):
            code = gate.main([])
    assert code == 2


def test_staged_paths_fail_closed_when_git_missing() -> None:
    import scripts.check_staged_data as gate

    with patch.object(gate.shutil, "which", return_value=None):
        code = gate.main([])
    assert code == 2


def test_package_imports() -> None:
    import lds_study
    from lds_study.config import get_settings

    assert lds_study.__version__
    settings = get_settings()
    assert (settings.root / "configs" / "models.yaml").exists()


def test_get_settings_honors_explicit_root(tmp_path: Path, monkeypatch) -> None:
    from lds_study.config import Settings, get_settings

    monkeypatch.setenv("LDS_STUDY_ROOT", str(tmp_path))
    settings = Settings()
    assert settings.root == tmp_path
    got = get_settings()
    assert got.root == tmp_path


def test_check_env_allow_cpu() -> None:
    script = ROOT / "scripts" / "check_env.py"
    code = subprocess.run(
        [sys.executable, str(script), "--allow-cpu"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert code.returncode == 0, code.stdout + code.stderr
    assert "environment check" in code.stdout.lower() or "lds_study" in code.stdout.lower()


def test_run_pull_dry_run_skips_hf_generator_by_default(monkeypatch) -> None:
    from lds_study import pull_models as pm

    calls: list[str] = []

    def fake_ollama(model_id: str, dry_run: bool) -> int:
        calls.append(f"ollama:{model_id}")
        return 0

    def fake_hf(repo_id: str, local_dir: str, dry_run: bool) -> int:
        calls.append(f"hf:{repo_id}")
        return 0

    monkeypatch.setattr(pm, "pull_ollama", fake_ollama)
    monkeypatch.setattr(pm, "pull_hf", fake_hf)
    code = pm.run_pull(dry_run=True, include_finetune_weights=False)
    assert code == 0
    assert any(c.startswith("ollama:") for c in calls)
    assert "hf:BAAI/bge-m3" in calls
    assert "hf:BAAI/bge-reranker-v2-m3" in calls
    assert not any("Qwen/Qwen2.5-14B-Instruct" in c for c in calls)


def test_run_pull_include_finetune_weights(monkeypatch) -> None:
    from lds_study import pull_models as pm

    calls: list[str] = []

    monkeypatch.setattr(pm, "pull_ollama", lambda *a, **k: 0)
    monkeypatch.setattr(
        pm,
        "pull_hf",
        lambda repo_id, local_dir, dry_run: calls.append(repo_id) or 0,
    )
    code = pm.run_pull(dry_run=True, skip_ollama=True, include_finetune_weights=True)
    assert code == 0
    assert "Qwen/Qwen2.5-14B-Instruct" in calls
