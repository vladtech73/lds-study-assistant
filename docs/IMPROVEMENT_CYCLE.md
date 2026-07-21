# Improvement cycle — measure, change one thing, re-measure

Use this when answers feel weak and you want to improve the **RAG pipeline**
without guessing. Pipeline map: [ARCHITECTURE.md](ARCHITECTURE.md). Eval
details: [../eval/README.md](../eval/README.md).

## Goal

Improve retrieval, citations, or refusal behavior. Every change is judged by
`lds eval` against:

- the last committed report under `outputs/eval/` (today:
  [2026-07-21-r2.md](../outputs/eval/2026-07-21-r2.md)), and
- the floors in `configs/rag.yaml` → `eval.baselines`.

If metrics drop, revert the change. Do not hand-edit baseline numbers — paste
what `lds eval` prints under “Suggested regression baselines.”

## Steady state vs refresh

| Situation | What to run |
|---|---|
| Just asking questions | `lds ask` only (index already built) |
| New / changed sources under `data/raw/` | `lds prepare` → `lds index` |
| Config only (`rag.yaml`, prompts, model id) | Usually **no** re-index; re-run `lds eval` |
| Embedder / chunking change | `prepare` (if chunks change) → `index` → `eval` |

## One iteration

1. **Diagnose** — note the symptom (wrong verse, invented cite, answers junk, weak lesson).
2. **Change one knob** — see table below; avoid changing three things at once.
3. **Re-index if needed** — only when chunks or embeddings change.
4. **Measure** — run eval (full or a focused bucket).
5. **Compare** — recall / cite validity / adversarial refusal vs last report + baselines.
6. **Keep or revert** — keep only if floors hold (or improve without tanking another metric).

```text
diagnose → change one thing → (re-prepare/index?) → lds eval → keep or revert
```

## Symptom → knob

| Symptom | First knobs | Re-index? |
|---|---|---|
| Wrong or missed verses (low Recall@k) | `retrieval.*` in `configs/rag.yaml` (top_k, reranker); check index smoke; golden `gold_chunk_ids` | Often yes if embedder/chunking changed |
| Invented or invalid citations | `prompts/*.md`; `citation.min_coverage` / `max_regenerate` | No |
| Answers out-of-corpus / junk questions | `retrieval.min_score`; refusal wording in prompts | No |
| Lesson/talk outlines fail coverage gate | `--mode lesson` prompt; `citation.min_coverage` (raise only with evidence) | No |
| New Conference / CFM / scripture files | BYOF under `data/raw/user/` or sources manifest | Yes: `prepare` → `index` |
| Want better *phrasing* only | Optional QLoRA (PR5) — style adapter; keep only if eval meets floors | No for RAG; see [FINETUNE_WINDOWS.md](FINETUNE_WINDOWS.md) |

## Commands (PowerShell)

From the repo root, with `.venv` ready and an index profile built:

```powershell
# Full comparison (two generators; slow)
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default --models qwen2.5:14b,qwen3:14b --no-local

# Faster: retrieval-only (Recall@k + score histogram; no generation)
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default --retrieval-only --no-local --stem recall-smoke

# Focus one bucket while iterating
.\.venv\Scripts\python.exe -m lds_study.cli eval --profile default --buckets adversarial --models qwen2.5:14b --no-local --stem adv-iter

# After data changes
.\.venv\Scripts\python.exe -m lds_study.cli prepare --stats
.\.venv\Scripts\python.exe -m lds_study.cli index --profile default --verbose
```

Reports: `outputs/eval/{stem}.md` (committable) + `.json` sidecar (local / gitignored).

Offline unit tests (no GPU): `.\.venv\Scripts\python.exe -m pytest -q`

## Baselines

Current PR5 keep-or-revert floors live in `configs/rag.yaml`:

```yaml
eval:
  baselines:
    min_recall_at_k: …      # from harness
    min_citation_validity: …
    min_adversarial_refusal: …
```

After a clean eval you intend to ship as the new gate:

1. Copy the emitted `eval.baselines` block into `configs/rag.yaml` **verbatim**.
2. Commit the new `outputs/eval/*.md` report (not the JSON).
3. Update [MODEL_CARD.md](../MODEL_CARD.md) “Latest comparison” link if needed.

## Optional QLoRA

Adapters may change tone/format only. Facts still come from retrieval. Train only on
redistributable sources; never publish adapters trained on restricted BYOF text.
Keep an adapter **only if** `lds eval` meets or beats the floors above. Details:
[FINETUNE_WINDOWS.md](FINETUNE_WINDOWS.md) (when PR5 lands).

## What not to do

- Don’t commit `data/`, `indexes/`, or model weights.
- Don’t force-stage `eval/golden.local.yaml` (copyright gate denylist).
- Don’t raise `retrieval.min_score` (or other live ask knobs) without a full re-eval —
  it changes context size and refusal together.
- Don’t edit numbers inside an old eval report to “fix” baselines; re-run the harness.
