# Architecture

End-to-end map for the local LDS study assistant (CLI-only v1).

```text
┌─────────────┐   chunks.jsonl    ┌─────────────┐   indexes/     ┌─────────────┐
│ lds prepare │ ───────────────► │  lds index  │ ────────────► │   lds ask   │
│  (PR2)      │                  │   (PR3)     │               │   (PR3)     │
└─────────────┘                  └─────────────┘               └─────────────┘
      │                                │                              │
      │ BYOF talks/CFM                 │ unload generator             │ retrieve
      │ + license-verified             │ embed → Chroma               │ hybrid
      │ scripture                      │ BM25 parallel                │ cite+validate
      ▼                                ▼                              ▼
 data/raw/{public,user}           indexes/{profile}            answer + citations
                                                               or refuse (exit 2/3)
```

## User flow

1. **`lds pull-models`** — download generator (Ollama) + embedding weights from `configs/models.yaml`.
2. **`lds prepare`** — ingest sources from `configs/sources.yaml` into `data/processed/chunks.jsonl`.
   - `redistributable: false` content stays local under gitignored `data/` only.
   - `license: unverified` sources refuse to load.
3. **`lds index`** — embed + BM25; persist Chroma under `indexes/`. Generator unloaded while embedding.
4. **`lds ask`** — hybrid retrieve → generate with citation markers → validate against retrieved set.
   - Bad citations: regenerate once → refuse (never silent strip).
5. **`lds eval`** (PR4) — golden questions; set regression baselines.
6. **Optional QLoRA** (PR5) — style adapter on redistributable-only data; keep only if eval does not regress.

## Where RAG and the optional adapter meet

```text
                    ┌──────────────────┐
 retrieved chunks ─►│  generator       │──► citation validator ──► stdout
                    │  (+ adapter?)    │
                    └──────────────────┘
```

Facts come from retrieval. An adapter (if set in `configs/models.yaml`) may change
tone/format only. Hybrid is off until PR5 and only kept if PR4 metrics hold.

## Package layout

| Path | Role |
|---|---|
| `src/lds_study/data/` | Loaders, normalize, chunk (PR2) |
| `src/lds_study/index/` | Retriever protocol + LlamaIndex/Chroma backend (PR3) |
| `src/lds_study/rag/` | Prompt, generate, citations (PR3) |
| `src/lds_study/eval/` | Golden harness (PR4) |
| `src/lds_study/finetune/` | Dataset + QLoRA (PR5) |

LlamaIndex is confined to `index/backend_llamaindex.py` behind `index/base.py`.

## Deferred (post-v1)

- FastAPI + SPA `serve`
- `music` / hymn mode (needs a legally clear corpus)
