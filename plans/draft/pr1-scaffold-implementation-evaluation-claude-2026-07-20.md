# PR1 — Skeleton + Legal — Implementation Evaluation

*Evaluator: claude · 2026-07-20 · Reviews PR1 of `claude-2026-07-20.md` against the working tree.*

## Verdict: Substantially complete and well-aligned with the revised plan — but the copyright gate, PR1's headline deliverable, does not actually gate anything yet.

Every file PR1 called for exists, the docs faithfully encode the plan's revised legal and
architectural decisions, and all stated gates pass (`pytest` 5 passed, `ruff` clean).
However the repo is **not a git repository**, so no staged-file check has ever run for
real; `check_staged_data.py` **fails open** when git is unavailable; and the CI job
exercises the gate only with synthetic `--paths`, never against the PR's actual changed
files. Separately, the venv contains `torch 2.13.0+cpu` on an sm_120 machine, so PR1's own
done-when ("prints GPU name, CUDA version, free VRAM") cannot currently be met.
Not safe to treat the legal guardrail as active until findings 1–3 are fixed.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Repo scaffold / tree layout** | Complete | All plan-named paths present; `src/lds_study/` with `data/ index/ rag/ eval/ finetune/` stubs; `tests/`, `prompts/`, `docs/`, `configs/` |
| **`configs/` (models, sources, rag)** | Complete | [configs/models.yaml](configs/models.yaml) has interim `qwen2.5:14b`, `num_ctx: 8192`, `kv_cache_quant: q8_0`, `reranker device: cpu`, shortlist for PR4; [configs/rag.yaml](configs/rag.yaml) encodes `min_coverage: 0.8`, `max_regenerate: 1`; [configs/sources.yaml](configs/sources.yaml) empty + `unverified` as planned |
| **`check_env.py`** | Complete (behavior correct) | [scripts/check_env.py:120-136](scripts/check_env.py#L120-L136) warns-with-fix on non-cu128, exits non-zero only when no CUDA device — exactly the softened contract the eval report asked for. Verified live |
| **`pull_models.py`** | Partial | Works ([src/lds_study/pull_models.py](src/lds_study/pull_models.py)), but default run pulls ~28 GB of HF generator weights no RAG user needs — see finding 4 |
| **`.gitignore` + allowlist** | Partial | [.gitignore:36-41](.gitignore#L36-L41) allowlist pattern is correct; conflicts with the plan's PR4 gate — see finding 8 |
| **CI staged-`data/` gate** | **Missing in effect** | [.github/workflows/ci.yml:22-28](.github/workflows/ci.yml#L22-L28) tests the *script*, not the *PR* — see findings 1–3 |
| **Pre-commit hook** | Missing | Plan step 8 says "Pre-commit hook **and** CI"; no `.pre-commit-config.yaml` or `.githooks/` exists |
| **README / DISCLAIMER / NOTICE / CONTRIBUTING** | Complete | All present; README leads with the unofficial disclaimer and a contains/does-not-contain table |
| **`docs/ARCHITECTURE.md` in PR1** | Complete | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the `prepare → index → ask` map, the RAG/adapter meeting point, and the deferred list |
| **`docs/LEGAL.md` (text vs edition)** | Complete | [docs/LEGAL.md](docs/LEGAL.md) reproduces the per-source policy accurately, including "no override flag" and mirror-provenance residual risk |
| **`docs/FINETUNE_WINDOWS.md` (WSL2 day one)** | Complete | Path A / failure-signature table / Path B all present |
| **`MODEL_CARD.md`** | Complete (early) | Plan put this in step 8; landing it in PR1 is harmless |
| **`.github/` issue + PR templates** | Partial / broken | PR template is issue-forms YAML, will render as raw text; no `ISSUE_TEMPLATE/` — see finding 6 |
| **Deferred items stayed deferred** | Complete | No `serve`, no `music` anywhere in `src/`; [src/lds_study/cli.py:50-71](src/lds_study/cli.py#L50-L71) stubs name their target PR |
| **Package rename `lds_study` / no `[rag]` extra** | Complete | [pyproject.toml:14-40](pyproject.toml#L14-L40) — RAG deps are base; only `finetune` and `dev` extras |
| **Environment actually on cu128** | **Missing** | `torch 2.13.0+cpu` installed — see finding 3 |

## Findings (ranked)

### 1. The repo is not a git repository, so the copyright gate has never run. *(Critical)*

`git status` and `git log` both return `fatal: not a git repository`. PR1's stated gate is
"copyright gate blocks a test commit containing a restricted file" — that has not been
demonstrated, because there are no commits, no staging area, and no `.git` at all. The
plan's own Verification invariant (`git status` shows no new tracked files under `data/`)
is unrunnable.

This also means `.gitignore` itself is untested: the nested negation pattern
`data/**` + `!data/**/` + `!data/**/.gitkeep` is subtle and git-version-sensitive, and
nobody has confirmed git actually honors it here.

**Remediation:** `git init`, commit the scaffold, then prove the gate end-to-end: stage a
dummy `data/raw/user/test.txt`, confirm the hook/script rejects it, and confirm
`git status --ignored` shows `data/` content ignored while `data/README.md` and the
`.gitkeep` files are tracked.

### 2. `check_staged_data.py` fails open when git is unavailable. *(Critical)*

[scripts/check_staged_data.py:51-61](scripts/check_staged_data.py#L51-L61): if `git` is
missing, or the directory is not a repo, or the command errors for any reason,
`staged_paths()` returns `[]` and `main()` prints `OK — 0 path(s) checked` and exits 0.
Verified live in the current tree:

```
$ python scripts/check_staged_data.py
OK — 0 path(s) checked; no allowlist violations.
exit=0
```

A guard whose failure mode is "silently pass" is not a guard. This is the same class of
defect the plan spent its Risks section warning about — the allowlist is a soft spot — and
it is worse here because the failure is invisible. `subprocess.run(..., check=False)` also
swallows a non-zero git exit without distinguishing "no staged files" from "git broke".

**Remediation:** distinguish the three cases. Exit 0 only on a successful git call
returning zero violations; exit non-zero with an explicit "cannot verify staged files"
message when git is absent or returns non-zero. Add a unit test that stubs a failing git
invocation and asserts a non-zero exit.

### 3. CI validates the script, not the pull request. *(Critical)*

[.github/workflows/ci.yml:22-28](.github/workflows/ci.yml#L22-L28) runs
`check_staged_data.py --paths data/README.md …` and `--paths data/raw/user/test.txt` —
hardcoded synthetic inputs. On a GitHub runner the checkout has **no staged files**, so
the gate never sees the PR's real contents. A pull request that genuinely adds
`data/raw/user/oct-2025-nelson.pdf` passes this job green.

Combined with finding 2, the project currently has zero effective protection against the
exact failure the plan names as its top legal risk.

**Remediation:** add a step that checks the PR's actual changed paths, e.g.
`git diff --name-only --diff-filter=ACMR origin/${{ github.base_ref }}...HEAD` piped into
`check_staged_data.py --paths`, with `fetch-depth: 0` on the checkout. Keep the synthetic
self-test as a separate step — it is a good regression test for the script, just not a gate.

### 4. `pull-models` downloads ~28 GB of HF generator weights nobody in v1 needs. *(High)*

Verified via dry run:

```
$ python -m lds_study.cli pull-models --dry-run
$ ollama pull qwen2.5:14b
huggingface_hub.snapshot_download BAAI/bge-m3 -> models\BAAI--bge-m3
huggingface_hub.snapshot_download BAAI/bge-reranker-v2-m3 -> models\BAAI--bge-reranker-v2-m3
huggingface_hub.snapshot_download Qwen/Qwen2.5-14B-Instruct -> models\Qwen--Qwen2.5-14B-Instruct
```

[src/lds_study/pull_models.py:85-91](src/lds_study/pull_models.py#L85-L91) pulls
`generator.hf_id` unconditionally, with the comment "for Unsloth/QLoRA path." But QLoRA is
PR5 behind an optional extra, and the plan is explicit that RAG users should never touch
the finetune stack. The default command therefore costs ~37 GB (9 GB Ollama Q4 + ~28 GB
fp16 HF) instead of ~9 GB, on the first command a new user runs.

**Remediation:** gate the `hf_id` pull behind an explicit `--include-finetune-weights`
flag (default off) and mention it in `docs/FINETUNE_WINDOWS.md` rather than the quickstart.

### 5. `get_settings()` silently discards the documented `LDS_STUDY_ROOT` setting. *(High)*

[src/lds_study/config.py:51-58](src/lds_study/config.py#L51-L58) reassigns
`settings.root = repo_root()` unconditionally after re-reading `.env`. Reproduced with a
`.env` containing `LDS_STUDY_ROOT=D:/tmp/pwtest`:

```
get_settings root= WindowsPath('D:/GitHub/lds-study-assistant')
raw Settings root= WindowsPath('D:/tmp/pwtest')
```

`.env.example` advertises `LDS_STUDY_ROOT=` as a knob, and it does nothing whenever a
`.env` file exists. This is a silent env-override break: the user's configuration is read,
then thrown away. It will surface later as "why is my `data_dir` pointing at the repo when
I moved my corpus?"

The same function is also fragile for a non-editable install — `repo_root()` is
`parents[2]` of `config.py`, which lands in `site-packages`' parent rather than a repo.

**Remediation:** only fall back to `repo_root()` when `root` was not explicitly supplied
(check whether the field is in `Settings.model_fields_set`), or drop `LDS_STUDY_ROOT` from
`.env.example` if the root is meant to be derived rather than configured. Pick one story
and make code and docs agree.

### 6. The PR template is written in issue-forms YAML and will not render. *(High)*

[.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md) uses the
`name:/description:/body:/type: checkboxes` schema. GitHub supports that schema only for
**issue forms** under `.github/ISSUE_TEMPLATE/*.yml`. As `PULL_REQUEST_TEMPLATE.md` it is
treated as plain markdown, so every PR description will open pre-filled with raw YAML and
**no clickable checklist** — including the "contains no copyrighted Church text" item the
plan specifically wanted enforced at review time.

Plan step 8 also asked for issue templates; `.github/ISSUE_TEMPLATE/` does not exist.

**Remediation:** rewrite the PR template as plain markdown `- [ ]` checkboxes. Add
`.github/ISSUE_TEMPLATE/` separately if issue forms are still wanted.

### 7. The working venv has a CPU-only torch on an sm_120 machine. *(High)*

`check_env.py` reports `torch 2.13.0+cpu`, `torch.version.cuda=''`, `cuda.is_available: False`,
`device_count: 0`, exit 1. `pip list` shows `sentence-transformers 5.6.0` pulled in by
`llama-index-embeddings-huggingface`, which is what dragged the PyPI CPU wheel in.

The README quickstart order — `pip install -r requirements-cu128.txt` **then**
`pip install -e ".[dev]"` — is exactly the order that lets the second command resolve a
CPU torch over the cu128 one. The guardrail worked (it warned correctly, which is a real
credit to the implementation), but PR1's done-when says `check_env.py` prints GPU name and
free VRAM, and it currently cannot.

**Remediation:** reinstall torch from the cu128 index after the editable install, and
change the README to put `pip install -e ".[dev]"` **first**, then the cu128 wheel — with a
note to re-run `check_env.py` after any dependency change. Consider adding
`--extra-index-url` guidance or pinning torch in `pyproject.toml` to avoid the silent
downgrade.

### 8. `.gitignore` blocks the artifact PR4's gate requires. *(Low)*

[.gitignore:32-33](.gitignore#L32-L33) ignores `outputs/**` except `.gitkeep`. The plan's
PR4 gate is "comparison table for ≥2 generators **committed** under `outputs/eval/`". As
written, that commit will be silently ignored.

Related inconsistency: `outputs/` is absent from `MONITORED_PREFIXES` in
[check_staged_data.py:21](scripts/check_staged_data.py#L21) yet `outputs/.gitkeep` sits in
the allowlist — dead allowlist entry, and it diverges from the plan's Verification
invariant, which names `outputs/` alongside `data/`, `indexes/`, `models/`.

**Remediation:** decide now whether eval reports are committed. If yes, add
`!outputs/eval/*.md` to `.gitignore` and keep `outputs/` out of the monitored prefixes. If
no, change the PR4 gate in the plan. Either way, remove the orphan allowlist entry.

### 9. No test covers the gate's failure modes. *(Low)*

[tests/test_pr1_scaffold.py](tests/test_pr1_scaffold.py) tests the allowlist's happy and
reject paths with explicit `--paths`, which is the code path CI already exercises. Nothing
tests the `staged_paths()` branch — the one that actually runs in anger and the one that
fails open (finding 2). `pull_models.run_pull(dry_run=True)` is also untested despite being
trivially testable offline.

**Remediation:** add a test that monkeypatches `subprocess.run` to simulate a git failure
and asserts non-zero exit, plus a `run_pull(dry_run=True)` test asserting no network call.

### 10. Small cleanups. *(Trivial)*

- [check_staged_data.py:35](scripts/check_staged_data.py#L35): `path.lstrip("./")` strips a
  *character set*, not a prefix — `".data/x"` and `"..//data"` normalize surprisingly. Use
  `removeprefix("./")`.
- [check_staged_data.py:81-84](scripts/check_staged_data.py#L81-L84): the second `if` is
  dead — line 81 already falls back to `staged_paths()` when `--paths` is empty.
- `configs/models.yaml` `quant: "Q4_K_M"` is not read by any code; the Ollama tag carries
  the quantization. Either wire it or comment it as documentation-only.
- `src/lds_study.egg-info/` and `__pycache__/` are on disk but covered by `.gitignore`;
  harmless once git is initialized.

### 11. Things done well. *(Noted — no action)*

Worth recording so they are not lost in a later refactor: `check_env.py`'s warn-vs-fail
split matches the softened contract precisely; `configs/rag.yaml` encodes the
regenerate-once-then-refuse semantics as data rather than prose; `sources.yaml` correctly
ships **empty with `unverified` examples** instead of inventing `verified_on` dates; CLI
stubs exit non-zero with the owning PR named; and `docs/LEGAL.md` reproduces the
text-vs-edition reasoning without overclaiming.

## Net assessment

PR1's *documentation and configuration* work is genuinely good — it is a faithful,
disciplined encoding of the revised plan, and several decisions (empty `sources.yaml`,
warn-not-fail env check, PR-tagged CLI stubs) show the plan was actually read rather than
skimmed. The *enforcement* work is where it falls short, and unfortunately enforcement is
what PR1 was for.

Before merge: findings 1, 2, and 3 — initialize git and prove the gate, close the fail-open
path, and make CI check real changed files. Those three are one focused sitting and they
are the difference between a legal guardrail and a comment that says "guardrail." Finding 6
is cheap and belongs in the same pass since it affects the review-time checklist.

After merge / before PR2: findings 4, 5, 7, 8. Finding 7 in particular should be resolved
before anyone claims the hardware path works, and finding 8 should be settled before PR4
discovers it the hard way.

Findings 9–10 are cleanup and can ride along with PR2.

## Verification performed

- `python -m pytest -q` → **5 passed in 2.12s**
- `python -m ruff check src scripts tests` → **All checks passed!**
- `python scripts/check_env.py` → exit **1**; `torch 2.13.0+cpu`, `cuda.is_available: False`,
  `device_count: 0`, warning text correct and actionable
- `python scripts/check_staged_data.py` (no args, no git repo) → exit **0**, `OK — 0 path(s) checked` (fail-open, finding 2)
- `python -m lds_study.cli version` → `0.1.0`, exit 0
- `python -m lds_study.cli prepare` → "not implemented yet (planned for PR2)", exit 1
- `python -m lds_study.cli pull-models --dry-run` → exit 0; enumerated 1 Ollama pull + 3 HF snapshots incl. `Qwen/Qwen2.5-14B-Instruct` (finding 4)
- `git status` / `git log` → `fatal: not a git repository` (finding 1)
- `pip list` → `torch 2.13.0`, `sentence-transformers 5.6.0`, `chromadb 1.5.9`,
  `llama-index-core 0.14.23` — confirms the CPU-torch transitive path (finding 7)
- Config override spot-check: `.env` with `LDS_STUDY_ROOT=D:/tmp/pwtest` →
  `get_settings().root` = repo root, `Settings().root` = `D:/tmp/pwtest` (finding 5)
- File inventory vs plan step 1 tree → all named paths present except
  `.pre-commit-config.yaml` and `.github/ISSUE_TEMPLATE/`
- Read in full: `check_env.py`, `check_staged_data.py`, `pull_models.py` (both copies),
  `cli.py`, `config.py`, `pyproject.toml`, `.gitignore`, `ci.yml`,
  `PULL_REQUEST_TEMPLATE.md`, all three `configs/*.yaml`, all three `docs/*.md`,
  `README.md`, `data/README.md`, `.env.example`, `tests/test_pr1_scaffold.py`
