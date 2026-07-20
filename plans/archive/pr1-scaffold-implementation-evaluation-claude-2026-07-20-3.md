# PR1 — Skeleton + Legal — Implementation Evaluation (round 3)

*Evaluator: claude · 2026-07-20 · Re-reviews PR1 of `claude-2026-07-20.md` after the round-2
remediation pass. Scope: uncommitted working tree vs `a4537f8`.*

> **Disclosure:** I applied several of these fixes myself in the preceding session, so this
> round is self-review. Every claim below was re-derived from a fresh command run rather
> than from my own summary, and I went looking specifically for things my own patch broke.
> Two of the five findings below are defects in the remediation itself.

## Verdict: All round-2 findings are closed and PR1's hardware gate finally passes on real silicon — remaining issues are consistency gaps, not correctness failures.

`check_env.py` now exits 0 with `RTX 5070 Ti sm_120`, `torch 2.11.0+cu128`, 14.68/15.92 GiB
free — the plan's PR1 done-when is met for the first time. The blank-`LDS_STUDY_ROOT`
regression is fixed at the validator level and covered by tests that `chdir` away from the
repo. 14 tests pass, ruff is clean, and the copyright gate still blocks a genuinely staged
restricted file. No Critical or High findings remain.

What is left is a `.gitignore`-vs-gate disagreement that would silently swallow a nested PR4
eval report, and a pre-commit hook that is declared but not actually installed anywhere.
Safe to commit; fix finding 1 before PR4 depends on it.

## Round-2 findings — disposition

| # | Round-2 finding | Severity | Status | Evidence |
|---|---|---|---|---|
| 1 | Blank `LDS_STUDY_ROOT` → `Path('.')` | High | **Fixed** | [config.py:27-46](src/lds_study/config.py#L27-L46): `root: Path \| None = None` + `_blank_root_means_unset` validator; `resolve()`/`configs_dir` fall back to `repo_root()`. Repro from `d:\tmp\pwtest` with copied `.env.example` → `root=D:\GitHub\lds-study-assistant`, `models.yaml exists=True` |
| 2 | venv on CPU torch | High | **Fixed** | `torch 2.11.0+cu128`, `cuda.is_available: True`, `device_count: 1`, `sm_120`, exit 0 |
| 3 | CI shallow fetch vs three-dot range | Low | **Fixed** | [ci.yml:38-42](.github/workflows/ci.yml#L38-L42): full `git fetch origin "$BASE_REF"`, two-dot `origin/${BASE_REF}..HEAD`. See finding 4 for the semantic caveat |
| 4 | `pre-commit` not in `[dev]` | Low | **Declared, not installed** | `pyproject.toml` extras now `['pytest>=8.0', 'ruff>=0.5', 'pre-commit>=3.7']`; CONTRIBUTING updated. But not present in `.venv` and no `.git/hooks/pre-commit`. See finding 2 |
| 5 | Dead `outputs/.gitkeep` allowlist entry | Trivial | **Fixed, the better way** | `outputs/` added to `MONITORED_PREFIXES`, aligning the gate with the plan's Verification invariant — and this surfaced a real bug, below |

**Bug caught during remediation (worth recording):** taking option B on finding 5 initially
allowlisted only `outputs/eval/**/*.md`. Under `fnmatch`, `**/` requires an intervening
directory, so `outputs/eval/2026-07-20.md` — exactly the flat artifact PR4 must commit —
was **rejected** (verified: exit 1). Fixed by adding a sibling `outputs/eval/*.md` pattern
with a comment explaining why both are needed. This is the kind of thing that would have
shipped green and only failed in PR4.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Git repo + gate proven end-to-end** | Complete | `git add -f data/raw/user/test.txt` → gate exit 1 naming the path; `.gitignore` refuses it first (two layers) |
| **`check_env.py` + Blackwell path** | **Complete (finally verified)** | Exit 0 with GPU name, `sm_120`, cu128 build, VRAM — the plan's done-when, met on hardware |
| **`config.py` root handling** | Complete | Validator + fallbacks; 3 tests incl. two that `chdir` to a temp dir |
| **CI changed-file gate** | Complete | Two-dot range, full base fetch; self-test kept separate |
| **Pre-commit hook** | Partial | Config + declaration + docs present; not installed in practice — finding 2 |
| **Copyright allowlist scope** | Complete | `data/ indexes/ models/ outputs/` monitored; eval markdown allowlisted flat and nested |
| **`.gitignore` ↔ gate agreement** | **Partial** | Diverge on nested eval reports — finding 1 |
| **Docs (README / CONTRIBUTING / FINETUNE_WINDOWS)** | Complete | Install order corrected consistently in both quickstarts; `pre-commit install` documented |
| **Tests** | Complete (with redundancy) | 14 passed in 2.73s; two near-duplicate blank-root tests — finding 3 |
| **Deferred items stayed deferred** | Complete | No `serve`, no `music` in `src/` |
| **Scope discipline** | Complete | Diff is 7 files / +103 −30, all traceable to a round-2 finding; no drive-by refactors |

## Findings (ranked)

### 1. `.gitignore` and the gate disagree about nested eval reports. *(Low)*

The gate allows `outputs/eval/sub/nested.md`; git silently ignores it. Verified:

```
outputs/eval/flat.md        -> TRACKABLE
outputs/eval/sub/nested.md  -> IGNORED
outputs/scratch.txt         -> IGNORED

$ check_staged_data.py --paths outputs/eval/flat.md outputs/eval/sub/nested.md
OK — 2 path(s) checked; no allowlist violations.
```

Cause: [.gitignore:32-36](.gitignore#L32-L36) excludes `outputs/**` and re-includes
`!outputs/eval/` (the directory) plus `!outputs/eval/**/*.md`. Git cannot re-include a file
whose *parent directory* is still excluded, and there is no `!outputs/eval/**/` directory
negation — so the flat case works and the nested case does not.

The fail direction is safe (git is stricter than the gate, so nothing leaks). The risk is
the opposite kind: a PR4 author files `outputs/eval/qwen3-vs-qwen25/report.md`, the gate
says OK, `git add` silently does nothing, and the comparison table the plan requires as a
gate artifact never lands.

**Remediation:** add `!outputs/eval/**/` to `.gitignore` so nested directories are
re-included, then re-run the `git check-ignore` check above. Alternatively narrow the gate
to `outputs/eval/*.md` only and drop the nested pattern — but decide deliberately, since
the plan's PR4 gate is what depends on it.

### 2. The pre-commit hook is declared but installed nowhere. *(Low)*

`pyproject.toml` now lists `pre-commit>=3.7` under `[dev]` and CONTRIBUTING tells
contributors to run `pre-commit install`. Neither has happened here:

```
$ pip show pre-commit    → (no output — not installed in .venv)
$ ls .git/hooks/pre-commit → no such file
```

The declaration was added without re-running `pip install -e ".[dev]"`, so the round-2
finding is closed on paper only. Plan step 8 wants the hook *and* CI; right now CI is the
sole enforcing layer, and CI only sees a restricted file after it is already in a pushed
commit — which for copyrighted material is exactly the moment you did not want it to reach.

**Remediation:** `pip install -e ".[dev]"` then `pre-commit install` in this repo, and
confirm with `ls .git/hooks/pre-commit`. Worth doing before the next commit, since that
commit is the one carrying all these fixes.

### 3. CI's range semantics changed from three-dot to two-dot. *(Low — untested)*

[ci.yml:42](.github/workflows/ci.yml#L42) now uses `origin/${BASE_REF}..HEAD`. Two-dot is a
plain endpoint diff, so it includes changes made on the *base* branch since divergence,
not only the PR's own changes. For the default `actions/checkout` behavior on
`pull_request` (which checks out the merge commit) this is equivalent in practice, because
HEAD already contains base. It stops being equivalent if the workflow later switches to
`ref: ${{ github.event.pull_request.head.sha }}`.

Trading exact semantics for robustness was the right call given the merge-base fragility,
but it is now an assumption nobody has exercised — no PR has run this workflow.

**Remediation:** no code change. Watch the first real PR, and if the workflow ever pins the
head SHA, revisit the range. A one-line comment in the yml recording *why* two-dot was
chosen would keep a future editor from "fixing" it back.

### 4. Two near-duplicate tests for the same regression. *(Trivial)*

`test_blank_root_env_does_not_become_cwd` (lines 131-142) and
`test_blank_lds_study_root_falls_back_from_foreign_cwd` (lines 154-172) assert essentially
the same thing — blank env, `chdir` to tmp, expect `repo_root()`. The second adds only
`got.root != tmp_path` and `got.root != Path(".")`. This is remediation collision, not
deliberate coverage.

Both also drive the validator through the **environment variable**, not through an actual
`.env` file — which is how the bug was originally reported. The two paths converge on the
same validator so coverage is real, but the closest-to-repro case is untested.

**Remediation:** merge into one test, and write a `tmp_path/.env` containing a literal
`LDS_STUDY_ROOT=` line to exercise the dotenv path end to end.

### 5. `resolve()` and `configs_dir` duplicate the None-fallback. *(Trivial)*

[config.py:49](src/lds_study/config.py#L49) and [config.py:56](src/lds_study/config.py#L56)
each carry `root = self.root if self.root is not None else repo_root()`. Two copies of one
rule; a third accessor added in PR2 will need a third copy or will silently get `None`.

**Remediation:** expose a single `effective_root` property and have both call it. Five-line
change, best done when PR2 first needs the root.

### 6. Verification quality this round. *(Noted — no action)*

Recording what the fixes got right, since the failure modes were subtle: the validator uses
`mode="before"`, which is the only place that can intercept the empty string *before*
pydantic coerces it to `Path('')` — a post-validator or a `get_settings()` check would have
seen `'.'` and been fooled again, which is precisely how the round-2 attempt failed. And
the new tests `monkeypatch.chdir(tmp_path)`, so they would actually catch a cwd-rooted
regression; the round-2 tests passed only because pytest ran from the repo root.

## Net assessment

PR1 is now in good shape and, for the first time across three rounds, its central hardware
claim is backed by a passing `check_env.py` on the actual GPU rather than by documentation.
The diff is tightly scoped — 7 files, every hunk traceable to a numbered finding, no
opportunistic refactoring.

Commit-ready. Do finding 2 first (`pip install -e ".[dev]"; pre-commit install`) so the
commit carrying these fixes is itself covered by the hook. Finding 1 before PR4 starts —
it is a one-line `.gitignore` addition and a re-run of `git check-ignore`. Findings 3-5 are
housekeeping for PR2.

One process note: this was the third remediation round, and rounds 2 and 3 each introduced
a fresh defect while closing the previous one (round 2's `Path('.')` coercion, round 3's
`**/` fnmatch pattern). Both were caught only by running the exact reported repro rather
than by reading the patch. Worth keeping that habit for PR2's data pipeline, where the
equivalent mistakes are silent chunk loss rather than a loud exit code.

## Verification performed

- `python -m pytest -q` → **14 passed in 2.73s** (was 11, was 5)
- `python -m ruff check src scripts tests` → **All checks passed!**
- `python scripts/check_env.py` → **exit 0**; `torch 2.11.0+cu128`, `cuda 12.8`,
  `cuda.is_available: True`, `[0] NVIDIA GeForce RTX 5070 Ti sm_120 VRAM 14.68/15.92 GiB`
- **Finding-1 repro (round 2), re-run:** `cp .env.example .env` in `d:\tmp\pwtest` →
  `root=D:\GitHub\lds-study-assistant`, `models.yaml exists=True` — **closed**
- **Gate end-to-end:** `echo restricted > data/raw/user/test.txt; git add -f` →
  exit **1**, path named; reverted, tree clean
- `check_staged_data.py --paths outputs/eval/2026-07-20.md outputs/eval/sub/x.md outputs/eval/.gitkeep`
  → exit **0**
- `check_staged_data.py --paths outputs/scratch.txt indexes/default/chroma.sqlite3` → exit **1**
- `git check-ignore` on `outputs/eval/flat.md` / `outputs/eval/sub/nested.md` /
  `outputs/scratch.txt` → TRACKABLE / IGNORED / IGNORED (finding 1)
- `pip show pre-commit` → not installed; `ls .git/hooks/pre-commit` → absent (finding 2)
- `tomllib` parse of `pyproject.toml` → extras resolve correctly incl. `pre-commit>=3.7`
- `grep` for `Settings()` / `.root` outside tests → only `config.py` internals and
  `pull_models.py:57` (`get_settings()`), so no caller sees `root=None`
- `git diff --stat` → 7 files, +103 −30; `git diff CONTRIBUTING.md` reviewed (install order
  + `pre-commit install`, consistent with README)
