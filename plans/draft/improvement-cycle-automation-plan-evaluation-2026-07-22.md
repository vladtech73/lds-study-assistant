# Improvement Cycle Automation Plan Evaluation Report

*Date: 2026-07-22 · Evaluators: composer-2.5, gpt-5.6-sol-medium, gemini-3.1-pro · Mode: readonly parallel review*
*Plans compared:*
- [Claude](improvement-cycle-automation-claude-2026-07-22.md)
- [Grok](improvement-cycle-automation-grok-2026-07-22.md)

---

## Verdict

**Unanimous (3/3): execute the Claude plan.**

It correctly solves the committed-history / copyright constraint with aggregates-only `*.summary.json`, keeps humans in charge of knob changes, and adds enforceable offline guardrails — fold the steal list before coding.

---

## Scoreboard

| Criterion | Composer — C / G | GPT — C / G | Gemini — C / G |
|-----------|------------------|-------------|----------------|
| Audit accuracy | 5 / 3 | 4 / 3 | 5 / 3 |
| Risk awareness | 5 / 3 | 4 / 2 | 5 / 3 |
| Implementability | 4 / 3 | 4 / 3 | 5 / 4 |
| Completeness vs scope | 4 / 2 | 3 / 2 | 5 / 3 |
| **Winner** | **Claude** | **Claude** | **Claude** |
| Confidence | high | high | high |

---

## Why the winner won (shared themes)

1. **Committed machine-readable history** — only `outputs/eval/**/*.md` is allowlisted today; full JSON sidecars are gitignored and can carry per-item / local golden text. Claude’s aggregates-only `*.summary.json` unblocks safe “vs last committed” diffs; Grok prefers gitignored sidecars or fragile markdown parsing.
2. **Safer mutation model** — Claude automates measure / compare / promote with hard preconditions; Grok’s `cycle experiment` snapshot-patches YAML and prompts (crash → dirty tree / half-applied state).
3. **Playbook rules become code** — Claude’s `check_eval_reports.py` + CI/pre-commit encode “don’t hand-edit baselines / old reports”; Grok leaves that honor-system.
4. **Load-bearing `rag.yaml` comments** — Claude requires `ruamel.yaml` round-trip; Grok allows “replace the block if too hard.”
5. **Staleness via extended `index_manifest.json`** — cleaner than Grok’s parallel `.cycle_fingerprint`.

---

## Critical feedback — Claude

### Blocking
- **Baseline-integrity bootstrap** — checker will fail day one unless PR6c ships a backfilled `*.summary.json` for `2026-07-21-r2` and/or an explicit `# baseline-provenance: legacy` escape hatch (same PR as the checker). (Composer)
- **`--auto-index` is unsafe as sketched** — chunking changes need `prepare` first; embedder changes need `lds index --rebuild` (incremental index keeps old vectors). (GPT)
- **`prepare` staleness metadata gap** — Step 3 assumes raw mtimes / sources hash vs `prepare_stats.json`, but Step 2 does not add those fields to prepare stats. (GPT; Composer notes mtime weakness)
- **“Never modify existing eval reports” vs manual quality column** — blank 1–5 column is intentional human scoring; enforcement must distinguish metric tampering from legitimate quality fills. (GPT)
- **Promotion can ratchet floors down** after a degraded-but-still-KEEP full run — require comparability + no regression vs reference + expected run shape before `--promote-baselines`. (GPT)

### Non-blocking
- Persist actual **checked floors + KEEP/REVERT verdicts** into summary + markdown (closes known PR5 console-only gap). (Composer, GPT)
- **`ruamel.yaml` round-trip risk** — require byte-stable tests on unmodified sections. (all)
- **`lds iterate` exit 2 (stale)** vs today’s always-run `lds eval` — document scripting semantics. (Composer)
- Scope breadth (4 PRs, nightly, integrity hooks) — keep PR6a thin. (GPT)
- “Newest committed summary” needs an explicit git-aware resolver. (GPT)
- Trend-regression tolerances for stochastic noise. (GPT)
- Possible CLI namespace clutter (`status` / `iterate` vs `cycle` / nested under `eval`). (Gemini)

### Nits
- Optional `nightly_eval.ps1` must stay a thin shim. (Composer)
- `chunks_mtime` redundant if `chunks_sha256` is authoritative. (GPT)
- Summary merge conflicts across branches. (Gemini)

---

## Critical feedback — Grok

### Blocking
- Compare / `apply-baselines` depend on **gitignored JSON sidecars** or markdown table parse — cannot be canonical “last committed” across clones. (all)
- **`cycle experiment` auto-patches** config/prompts with snapshot/restore — scope creep + crash/concurrency corruption risk. (all)
- **No guardrails** for hand-edited baselines or retro-edited reports. (Composer, Gemini)
- Promotion accepts sidecar / last-eval without full / `--no-local` / comparable-run gates — can weaken floors. (GPT)
- Comparison lacks run-shape guards (`golden_hash`, profile, k, local, buckets, retrieval-only). (GPT)
- Optional `--check-baselines` / configurable `--fail-on` can report success without the authoritative gate. (GPT)
- Same **embedder rebuild / prepare-before-index** dependency bug as Claude’s auto-index risk. (GPT)
- Explicit permission to strip load-bearing YAML comments. (GPT, Composer)

### Non-blocking
- Docs-before-code risks drift. (Composer)
- Parallel `.cycle_fingerprint` vs extending `index_manifest.json`. (Composer)
- Narrow fingerprint (no chunks hash / retrieval-citation eval staleness). (Composer, GPT)
- Auto one-knob / prompt swap expands past measure-and-gate. (GPT, Gemini)

### Nits
- Unresolved command naming / `eval.reference_report`. (Composer, GPT)
- Duplicate surface: `eval-compare` + `cycle measure`. (Composer)
- Optional finetune profile unrelated. (GPT)

---

## Cross-cutting risks

- **Copyright boundary on any committed eval artifact** — schema must stay aggregates-only; every new field is a license review.
- **Auto-deps / auto-index can retain stale embeddings** unless rebuild + prepare ordering is explicit.
- **Baseline ratchet** — 90%-of-best promotion without anti-regression vs prior reference can lock in lucky or degraded runs.
- **Staleness false negatives** on mtime-only prepare detection.
- Neither plan should auto-apply live ask knobs (`min_score`, `min_coverage`, etc.).

---

## Steal list — fold into winner before execute

| Steal | Consensus | Notes |
|-------|-----------|-------|
| Persist KEEP/REVERT + checked floors into `*.summary.json` and markdown | 3/3 | Grok Step 2; closes PR5 nit |
| `--dry-run` (or print-diff) before `--promote-baselines` writes | 3/3 | Grok dry-run default pattern |
| `scripts/check_env.py` preflight at start of `lds iterate` | 3/3 | warn-only / `--allow-cpu` |
| Optional `eval.reference_report` in `rag.yaml` as default compare target | 1/3 (Composer) | complement “newest committed summary” |

### Split opinion
| Steal | Notes |
|-------|-------|
| Prefer `lds cycle` naming over `lds iterate` | Gemini only — optional rename; not required |
| Drop or heavily gate auto-knob experiment | Consensus reject of Grok’s full experiment mode — do **not** steal wholesale |

---

## Pre-execute checklist

- [ ] Resolve baseline-integrity bootstrap (backfill `2026-07-21-r2.summary.json` and/or legacy provenance marker) in the same PR as the checker
- [ ] Fix `--auto-index` semantics: prepare-before-index for chunking; `--rebuild` for embedder; default `--auto-index` off (already) and document
- [ ] Extend prepare stats (or equivalent) so `lds status` prepare checks are real, not aspirational
- [ ] Narrow report-immutability guard so manual quality 1–5 edits are allowed; block metric/table tampering
- [ ] Harden `--promote-baselines`: full run, `--no-local`, KEEP, clean tree, comparable to reference, no regression vs reference
- [ ] Fold steal list: persist verdicts, promote dry-run, check_env preflight
- [ ] Explicitly defer Grok-style auto config/prompt experiment mode (out of scope for this slice)

---

## Recommended next step

1. Treat the **Claude** plan as the execution baseline.
2. Incorporate steal-list + winner’s blocking feedback (revise plan in place via Claude Code).
3. Then implement in a normal agent session (PR6a first).

---

## Evaluator session links

- [Composer](08e1783a-c1c8-4ff6-a524-552380038516)
- [GPT](bc036b20-5e97-45de-ae6a-59891f446eab)
- [Gemini](5533e79e-f3f2-43b6-9560-e2e7734660e0)
