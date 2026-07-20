# Contributing

Thank you for interest in improving this personal study tool.

## Hard rules

1. **Do not submit PRs containing copyrighted Church text** (Conference talks,
   Come Follow Me manuals, hymn arrangements, modern edition apparatus, etc.).
2. Do not commit files under `data/`, `indexes/`, `models/`, or `outputs/` except
   the structural allowlist (see `scripts/check_staged_data.py`).
3. Do not add scrapers that hit churchofjesuschrist.org as a default code path.
4. Keep the project **unofficial** — no branding that implies Church endorsement.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install --index-url https://download.pytorch.org/whl/cu128 torch
.\.venv\Scripts\python.exe scripts\check_env.py
.\.venv\Scripts\python.exe -m pytest -q
pre-commit install
```

`pip install -e ".[dev]"` includes `pre-commit`. Run `pre-commit install` once so the
copyright allowlist gate runs on every commit (CI is the second layer).

## PR checklist

- [ ] Contains no copyrighted text or restricted corpora
- [ ] `scripts/check_staged_data.py` passes
- [ ] Tests pass offline (no network, no GPU required)
- [ ] Scope matches an agreed PR slice (PR1–PR5 in the plan)
