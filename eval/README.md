# Evaluation harness (PR4)

- `golden.yaml` — committed public-domain scripture questions (~50).
- `golden.local.yaml` — optional, gitignored; BYOF / restricted-source questions for personal runs.

```powershell
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default --models qwen2.5:14b,qwen3:14b
```

Reports land in `outputs/eval/{date}.md` (committed allowlist) plus a local JSON sidecar.
