# PR1 — Skeleton + Legal — Implementation Evaluation (round 2)

*Evaluator: claude · 2026-07-20 · Re-reviews PR1 of `claude-2026-07-20.md` after remediation of
[`pr1-scaffold-implementation-evaluation-claude-2026-07-20.md`](pr1-scaffold-implementation-evaluation-claude-2026-07-20.md).*

## Verdict: All three Critical findings are genuinely fixed and the copyright gate now works end-to-end — but the config fix introduced a new latent break, and the machine still has no CUDA torch.

The repo is now a git repository with a clean commit, `check_staged_data.py` fails closed
with a distinct exit code, and CI checks the PR's real changed files. I proved the gate by
staging an actual restricted file: it rejected it. Test count went 5 → 11 with the right
tests added. Two things stop this from being a clean pass: `.env.example` ships
`LDS_STUDY_ROOT=`, and the new emptiness guard mis-handles it, so copying the example
verbatim silently sets the root to `.` and breaks config loading from any directory other
than the repo root (finding 1 — a regression the previous unconditional override was
accidentally masking). PR1's own done-when — `check_env.py` prints GPU name and free VRAM —
is still unmet because the venv holds `torch 2.13.0+cpu` (finding 2); the docs were fixed,
the environment was not.

Merge-ready once finding 1 is closed. Finding 2 is a one-command environment fix that
should happen before anyone claims the hardware path works.

## Round-1 findings — disposition

| # | Round-1 finding | Severity | Status | Evidence |
|---|---|---|---|---|
| 1 | Not a git repo; gate never ran | Critical | **Fixed** | `git log` → `a4537f8 Add PR1 scaffold with fail-closed copyright gate.`; 51 tracked files; only allowlisted paths tracked under `data/ indexes/ models/ outputs/` |
| 2 | Gate fails open when git unavailable | Critical | **Fixed** | [check_staged_data.py:39-92](scripts/check_staged_data.py#L39-L92) raises `GitUnavailableError`; `main` returns **2**; two tests cover git-missing and git-error |
| 3 | CI validated script, not the PR | Critical | **Fixed** | [ci.yml:32-58](.github/workflows/ci.yml#L32-L58) diffs `origin/$BASE_REF...HEAD` (PR) / `HEAD^...HEAD` (push) / `git ls-files` (initial), `fetch-depth: 0`; self-test kept as a separate step |
| 4 | `pull-models` pulled ~28 GB by default | High | **Fixed** | [pull_models.py:85-98](src/lds_study/pull_models.py#L85-L98) gated on `include_finetune_weights`; dry run prints `Skipping generator.hf_id (~28GB)`; two tests assert both directions |
| 5 | `LDS_STUDY_ROOT` silently discarded | High | **Partial — new break** | Explicit non-empty root now honored, but empty value regresses. See finding 1 below |
| 6 | PR template in issue-forms YAML | High | **Fixed** | [PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md) is plain markdown checkboxes; `.github/ISSUE_TEMPLATE/{bug,data,config}.yml` added |
| 7 | venv has CPU torch on sm_120 | High | **Docs fixed, env not** | README install order corrected and `requirements-cu128.txt` reworded, but `check_env.py` still exits 1. See finding 2 below |
| 8 | `.gitignore` blocked PR4's eval artifact | Low | **Fixed** | [.gitignore:34-36](.gitignore#L34-L36) `!outputs/eval/`, `!outputs/eval/**/*.md`; `outputs/eval/.gitkeep` committed; gate docstring explains outputs is unmonitored |
| 9 | No test for gate failure modes | Low | **Fixed** | `test_staged_paths_fail_closed_when_git_errors`, `..._when_git_missing`, `test_run_pull_dry_run_skips_hf_generator_by_default`, `test_run_pull_include_finetune_weights` |
| 10 | Cleanups (`lstrip`, dead branch, `quant`) | Trivial | **Fixed** | `normalize` uses `removeprefix` loop; `nargs="+"` removed the dead fallback; `quant` annotated documentation-only |
| — | Pre-commit hook missing (step 8) | Low | **Mostly fixed** | `.pre-commit-config.yaml` added; see finding 4 |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Git repo + committed scaffold** | Complete | One commit, clean tree, `.gitignore` verified by `git status --ignored` |
| **CI staged-`data/` gate** | Complete | Real changed-file step + self-test step; proven locally against a staged restricted file |
| **Pre-commit hook** | Partial | Config present but opt-in and `pre-commit` is not in `[dev]` — finding 4 |
| **`check_env.py`** | Complete (code) / Unmet (env) | Warn-vs-fail contract correct; machine still CPU-only |
| **`pull_models.py`** | Complete | Default ~9 GB, finetune weights opt-in, CLI + argparse flags aligned |
| **`configs/` (models, sources, rag)** | Complete | Unchanged from round 1 and still accurate to the plan |
| **`config.py` settings** | **Regressed** | Finding 1 |
| **`.github/` templates** | Complete | PR markdown + three issue forms, both carrying the copyright checkbox |
| **Docs (README / ARCHITECTURE / LEGAL / FINETUNE_WINDOWS)** | Complete | Install order fixed; `--include-finetune-weights` documented in README and finetune doc |
| **Tests** | Complete | 11 passed; covers fail-closed paths, eval-markdown allowance, pull gating, explicit root |
| **Deferred items stayed deferred** | Complete | Still no `serve`, no `music` in `src/` |

## Findings (ranked)

### 1. `.env.example` ships an empty `LDS_STUDY_ROOT` that the new guard treats as explicit. *(High — regression)*

[config.py:64-69](src/lds_study/config.py#L64-L69) guards with:

```python
root_value = str(settings.root).strip() if settings.root is not None else ""
if not root_explicit or not root_value:
    settings.root = repo_root()
```

The check runs on `str(Path(...))`, not the raw env value. Pydantic coerces the empty
string from `LDS_STUDY_ROOT=` into `Path('')`, whose `str()` is **`'.'`** — non-empty. So
`root_explicit` is True, `root_value` is `"."`, the fallback is skipped, and `root` becomes
`Path('.')`, i.e. the current working directory.

Reproduced by copying `.env.example` verbatim (what the file's own first line instructs)
and running from another directory:

```
root= WindowsPath('.')
configs= configs
models.yaml exists= False
```

From the repo root it happens to work, which is why `pytest` (11 passed) and
`test_package_imports` do not catch it — they run with `cwd == repo root`.
`test_get_settings_honors_explicit_root` only exercises a **non-empty** `tmp_path`.

This is worse than the round-1 bug it replaced: previously the unconditional override made
the value harmless. Now the documented-but-blank knob actively breaks `load_yaml`, and it
will surface in PR2/PR3 as "config not found" for anyone running `lds` from a subdirectory.

**Remediation:** compare against the raw environment/dotenv value rather than the coerced
`Path`, or make the field `root: Path | None = None` and treat `None`/`""` as unset. Then
add a test with `.env` containing a blank `LDS_STUDY_ROOT` executed from `tmp_path` as cwd.
Simplest alternative: delete the `LDS_STUDY_ROOT=` line from `.env.example` and leave it
commented, since the derived root is the intended default.

### 2. The venv still has CPU-only torch; PR1's done-when remains unmet. *(High)*

```
$ python scripts/check_env.py
torch version: 2.13.0+cpu
cuda.is_available: False
device_count: 0
Result: FAIL — no usable CUDA device.
exit=1
```

The documentation half of round-1 finding 7 was addressed well — README now installs the
package first and *then* forces the cu128 wheel, with an explicit note about
`sentence-transformers` pulling a CPU torch, and `requirements-cu128.txt` was reworded to
match. But nobody ran the corrected sequence. PR1's stated gate is that `check_env.py`
prints GPU name, CUDA version, torch build, and free VRAM; it currently prints none of the
GPU fields because there is no CUDA device visible.

**Remediation:** run
`pip install --index-url https://download.pytorch.org/whl/cu128 torch` in `.venv`, re-run
`check_env.py`, and paste the passing output into the PR description. Until then, do not
describe the Blackwell path as verified.

### 3. CI's shallow base fetch may not support the three-dot range. *(Low — untested)*

[ci.yml:39-40](.github/workflows/ci.yml#L39-L40) does
`git fetch origin "$BASE_REF" --depth=1` then uses `origin/${BASE_REF}...HEAD`. The
three-dot form requires a **merge base**; with a depth-1 base fetch, git may not have
enough history to find one and can fail with `no merge base`. `fetch-depth: 0` on the
checkout deepens the *checked-out* ref, not the freshly fetched base branch.

No PR has run through this job yet, so it is unproven either way. Cheap to make robust.

**Remediation:** drop `--depth=1` from the fetch (checkout already used `fetch-depth: 0`),
or switch to the two-dot `origin/${BASE_REF}..HEAD`, which needs no merge base. Verify on
the first real PR rather than assuming.

### 4. The pre-commit hook is opt-in and its tool is not a declared dependency. *(Low)*

`.pre-commit-config.yaml` exists and is correct (`pass_filenames: false`, `always_run`,
system language). But `pre-commit` is absent from `[dev]` in
[pyproject.toml:37-40](pyproject.toml#L37-L40), and README instructs a separate
`pip install pre-commit && pre-commit install`. Plan step 8 says "Pre-commit hook **and**
CI" — as shipped, a contributor who skips the optional step has only CI, and CI runs after
the restricted file already exists in a pushed commit.

**Remediation:** add `pre-commit` to the `[dev]` extra so `pip install -e ".[dev]"` makes
the hook one `pre-commit install` away, and mention it in CONTRIBUTING.md rather than only
the README quickstart.

### 5. `outputs/.gitkeep` is a dead allowlist entry. *(Trivial)*

[check_staged_data.py:26](scripts/check_staged_data.py#L26) monitors only
`("data/", "indexes/", "models/")`, and the module docstring now correctly states that
`outputs/` is deliberately unmonitored — yet `outputs/.gitkeep` remains in
`ALLOWLIST_PATTERNS` at line 35. It can never be reached. Harmless, but it is the kind of
stale entry that later makes someone think `outputs/` *is* guarded.

**Remediation:** delete the line, or add `outputs/` to the monitored prefixes with
`outputs/eval/**/*.md` allowlisted (which would also align the gate with the plan's
Verification invariant, where `outputs/` is named alongside the others).

### 6. Defense in depth is working. *(Noted — no action)*

Worth recording from the live check: staging a restricted file required `git add -f`,
because `.gitignore` already refuses it — the allowlist gate is the *second* layer, not the
only one. Both layers were exercised:

```
$ echo restricted > data/raw/user/test.txt && git add -f data/raw/user/test.txt
$ python scripts/check_staged_data.py
ERROR: restricted paths staged (not on structural allowlist):
  - data/raw/user/test.txt
exit=1
```

The `GitUnavailableError` exit code **2** is also a good choice — it distinguishes "cannot
verify" from "found a violation" (1), so CI failures will be diagnosable.

## Net assessment

This was a solid remediation pass. The three Critical findings were not merely acknowledged
but properly closed, with the right tests added for each — the fail-closed tests in
particular target exactly the branch that previously went unexercised, and the CI job now
separates "test the script" from "gate the PR," which is the correct decomposition.

Before merge: finding 1 only. It is a ten-line fix plus one test, and leaving it means
shipping a `.env.example` that breaks the tool if used as documented.

Before claiming the hardware path works: finding 2 — one `pip install`, then re-run
`check_env.py`.

Findings 3–5 can ride along with PR2. Finding 3 in particular will announce itself on the
first real pull request; just don't be surprised by it.

## Verification performed

- `python -m pytest -q` → **11 passed in 2.23s** (was 5)
- `python -m ruff check src scripts tests` → **All checks passed!**
- `git log --oneline` → `a4537f8 Add PR1 scaffold with fail-closed copyright gate.`
- `git ls-files -- data indexes models outputs` → exactly 8 structural files, no corpora
- `git status --short --ignored` → only caches/`.venv`/egg-info ignored; working tree clean
- **End-to-end gate proof:** staged `data/raw/user/test.txt` via `git add -f` →
  `check_staged_data.py` exit **1** with the offending path named; reverted cleanly
- `python scripts/check_staged_data.py` (clean tree, real repo) → exit **0**, 0 paths
- `python scripts/check_env.py` → exit **1**, `torch 2.13.0+cpu`, `device_count: 0` (finding 2)
- `python -m lds_study.cli pull-models --dry-run` → Ollama tag + 2 embed/rerank snapshots,
  `Skipping generator.hf_id (~28GB)` (finding 4 fixed)
- **Config regression repro:** `cp .env.example .env` in a foreign cwd →
  `root=WindowsPath('.')`, `configs=configs`, `models.yaml exists=False` (finding 1)
- Read in full: `check_staged_data.py`, `config.py`, `pull_models.py`, `cli.py`, `ci.yml`,
  `.pre-commit-config.yaml`, `PULL_REQUEST_TEMPLATE.md`, `ISSUE_TEMPLATE/*.yml`,
  `test_pr1_scaffold.py`, `conftest.py`, `.gitignore`, `.env.example`,
  `requirements-cu128.txt`, README quickstart section
