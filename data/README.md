# Data directory

Local corpora and processed artifacts live here. **Almost everything is gitignored.**

## Layout

```text
data/
  raw/public/     # license-verified downloads + MANIFEST.json (sha256 + URL + time)
  raw/user/       # BYOF Conference / Come Follow Me — never commit
  processed/      # chunks.jsonl, prepare_stats.json, sft.jsonl (gitignored)
```

`lds prepare` reads `configs/sources.yaml`, refuses `license: unverified`, and writes
verse-atomic scripture chunks plus heading-aware prose chunks. Sources marked
`redistributable: false` stay under gitignored `data/` and are excluded from any export
and from `lds finetune-dataset` (no override flag).
## Allowlisted tracked files only

- `data/**/.gitkeep`
- `data/README.md` (this file)
- `data/raw/user/EXAMPLE.meta.json`

CI / `scripts/check_staged_data.py` rejects any other staged path under `data/`,
`indexes/`, or `models/`.

## User file sidecars

For a talk PDF/ePub without good embedded metadata, add `MyTalk.meta.json` next to it:

See `raw/user/EXAMPLE.meta.json`.
