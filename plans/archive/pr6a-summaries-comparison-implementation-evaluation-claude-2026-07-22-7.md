# Summaries + Comparison (PR6a) — Implementation Evaluation

*Evaluator: claude · 2026-07-22 · Round 7 · Reviews PR6a of `improvement-cycle-automation-claude-2026-07-22.md` against the working tree (uncommitted changes on `pr6a-eval-summaries-compare` vs `main`). Follows rounds [1](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22.md)–[6](pr6a-summaries-comparison-implementation-evaluation-claude-2026-07-22-6.md).*

## Verdict: One High found — the default workflow can report a regression that did not happen.

All three round 6 findings are fixed with dedicated tests; the suite is at **97 passed**, `ruff` clean.

I said last round that six was past useful return. That was wrong, and it is worth being precise about why: rounds 5 and 6 probed *inputs a user has to opt into by typing*, found only opt-in edges, and I generalized from that to "nothing substantive left." This round I probed the **default** path instead — `--include-local` is on by default — and found the most consequential comparison defect of the series.

`golden_local_hash` is recorded in every summary and never guarded. Two runs whose local golden set changed compare as `comparable: True` and report a **−0.667 recall regression flagged `regressed=True`**, when nothing regressed at all: the retrieval system was byte-identical between the runs and only the measuring stick moved. The natural workflow this PR is built to serve — add a golden question, re-run, ask "did this regress?" — produces a confidently wrong answer.

## Round 6 finding disposition

| # (R6) | Severity | Status | Evidence |
|---|---|---|---|
| 1 — `--compare` accepts the restricted sidecar | Medium | **Fixed** | `load_summary` rejects payloads containing `items` with a message pointing at `*.summary.json` ([compare.py:89-93](../../src/lds_study/eval/compare.py#L89-L93)); `test_compare_rejects_full_sidecar_filename` ([test_pr6_iterate.py:442](../../tests/test_pr6_iterate.py#L442)) |
| 2 — `schema_version` never validated | Medium | **Fixed** | Rejects any version ≠ `SUMMARY_SCHEMA_VERSION` ([compare.py:94-99](../../src/lds_study/eval/compare.py#L94-L99)); `test_load_summary_rejects_unknown_schema_version` ([test_pr6_iterate.py:471](../../tests/test_pr6_iterate.py#L471)). Docstring now states both guards and why |
| 3 — `trend_tolerance` config read untested | Low | **Fixed** | Fixture uses a distinctive `0.25` with the comment *"Distinctive fixture value proves eval.trend_tolerance was read (not defaulted)"* ([test_pr6_iterate.py:96](../../tests/test_pr6_iterate.py#L96), [:534](../../tests/test_pr6_iterate.py#L534)) |
| 4 | Noted | Unchanged, correctly | — |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Step 1 — schema v1, aggregates-only** | Complete | Fail-closed projection; import-time key invariant; version now enforced on read |
| **Step 1 — copyright boundary (both artifacts)** | Complete | Verified round 5 |
| **Step 1 — `golden_local_hash` recorded** | Complete | Present in every summary — but unused, Finding 1 |
| **Step 1 — gitignore + allowlist** | Complete | Deny-before-allow confirmed round 6 |
| **Step 4 — `--compare` resolution** | Complete | Explicit fail-fast, `auto` git-tracked and chronological; verified in a repo path containing spaces and parentheses |
| **Step 4 — comparability guard** | **Partial** | 8 fields correct; the local golden set is unguarded — Finding 1 |
| **Step 4 — tolerance, rendering, CLI, exit codes** | Complete | Verified rounds 4–6 |
| **Step 10 — tests** | Complete for what is guarded | 97 pass; no case covers a changed local golden set |
| Steps 2, 3, 5–9 | Deferred-as-planned | — |

## Findings (ranked)

### 1. A changed local golden set produces a false regression verdict. *(High)*

`COMPARABILITY_FIELDS` is `('golden_hash', 'k', 'profile', 'include_local', 'retrieval_only', 'buckets', 'limit', 'models')` — `golden_local_hash` is absent, and `compare.py` never references it or `source_counts` anywhere.

Two real `run_eval` runs, identical retriever and configuration, with only `eval/golden.local.yaml` edited between them (one local question replaced by two different ones):

```
golden_hash       A==B : True
golden_local_hash A==B : False
source_counts     A / B: {'golden': 2, 'local': 1} / {'golden': 2, 'local': 2}
recall_shared     A / B: 1.0 / 0.3333333333333333
COMPARABLE?            : True | reason: ok
recall delta reported  : -0.6666666666666667 regressed= True
```

The tool reports a 67-point recall collapse, flagged as a regression, for a system that did not change. Recall runs at tolerance 0 by design (deterministic on a fixed index), so this is not even softened by the noise band — it is reported as hard, certain regression.

Three things make this the most severe comparison defect found across seven rounds:

- **It fires on the default path, not an opt-in one.** `--help` shows `--include-local … [default: include-local]`. And `golden.local.yaml` is BYOF content the user is *expected* to grow — plan Step 1 calls out authoring golden questions as inherently human work. Add a question, re-run, get a fabricated regression.
- **It fails toward confidence, not caution.** Every other guarded field degrades to "not comparable" with the offending field named. This one asserts `comparable: True` and prints a verdict.
- **The evidence is already in the file.** `golden_local_hash` differs and `source_counts` differs; both sit in the summary, both are ignored. Same shape as the round 2 `generated_at` finding — the right datum recorded and unread.

**Plan fidelity:** the implementation is faithful. Step 4's guard list is *"if `golden_hash`, `k`, `profile`, `include_local`, `retrieval_only`, `buckets`, or `limit` differ"* — the plan omits `golden_local_hash` too, and the implementer already went beyond it by adding `models`. So this is an inherited plan gap, not an implementation slip. But it defeats Step 4's stated purpose (*"mark the diff not comparable and say which field differs rather than printing misleading deltas"*) and lands squarely on the risk the plan itself registers: *"Automated comparison creates false confidence."*

**Remediation:** Add `golden_local_hash` to `COMPARABILITY_FIELDS` — one line, and the existing per-field test loop covers it with one more tuple entry. Consider `source_counts` as a second guard, since a local file that changes without changing its hash is impossible but a *count* mismatch is a cheap independent check. This also needs correcting in the plan's Step 4 list before PR6d's promotion gate reuses the same comparability check to decide whether floors may be written — a false "comparable" there writes wrong floors.

### 2. Carried notes. *(Noted — no action)*

TOCTOU stem dedup; no committed summary yet; trend regression not gating the exit code; four pre-existing U+2192 arrows in `prepare` / `index` / `finetune-dataset`. All unchanged, all correct for PR6a.

## Net assessment

Fix Finding 1 before merge. It is one line plus one test tuple, and the alternative is shipping a comparison feature that answers "did this regress?" with a confident yes on a workflow the user is expected to perform. Everything else on the branch is green and has been stable since round 3.

The plan's Step 4 guard list should be amended in the same pass — not for this PR's sake, but because PR6d's `--promote-baselines` precondition explicitly reuses "comparable to the reference" to decide whether new floors may be written. An unguarded local-set change there means a run that looks like a regression blocks a legitimate promotion, or a run that looks fine ratchets floors from an incomparable baseline. The plan already identifies floor-ratcheting as its most dangerous failure direction.

On the review series: I called round 6 the stopping point and was wrong, for a reason worth naming rather than glossing. Rounds 5–6 probed opt-in inputs, found only opt-in edges, and I read that as exhaustion of the space. The actual signal was that I had been probing the *periphery* — typed paths, malformed files, hostile encodings — while the default configuration went unexercised. A cheaper heuristic than "have the last two rounds found much?" is "have I run the thing the way a user actually runs it?" For PR6a the answer was no until this round, seven reviews in.

## Verification performed

- `.\.venv\Scripts\python.exe -m pytest -q` → **97 passed in 7.70s** (86 → 89 → 92 → 93 → 94+1F → 95 → 97)
- `.\.venv\Scripts\python.exe -m ruff check src scripts tests` → **All checks passed!**
- **R6 Finding 1 regression check**: `load_summary` rejects `items`-bearing payloads; covered by `test_compare_rejects_full_sidecar_filename`
- **R6 Finding 2 regression check**: `load_summary` rejects unknown `schema_version`; covered by `test_load_summary_rejects_unknown_schema_version`
- **R6 Finding 3 regression check**: fixture `trend_tolerance: 0.25` with an asserting comment
- **Finding 1 repro**: two `run_eval` runs, identical retriever/config, `golden.local.yaml` swapped between them → `golden_local_hash A==B: False`, `source_counts` differ, `COMPARABLE?: True`, recall delta `-0.667` with `regressed=True`
- `python -m lds_study.cli eval --help` → `--include-local … [default: include-local]` (confirms the defect is on the default path)
- `grep -n "golden_local\|source_counts" src/lds_study/eval/compare.py` → no matches (neither field is consulted anywhere in the comparison)
- **Windows path robustness** (new this round): full `--compare auto` lifecycle inside a repo rooted at `…/my repo (test)/` — commit, re-run, resolve → `comparable: True`, report line `- Previous: \`outputs/eval/sp-a.summary.json\`` (spaces and parentheses handled correctly by `git ls-files`, `display_path`, and the stem dedup)

*Not run (require GPU/Ollama/built index): the plan's local verification block against a real index — still the largest unknown, and now the only substantial one.*
