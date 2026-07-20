# Data directory

Local corpora and processed artifacts live here. **Almost everything is gitignored.**

## Layout

```text
data/
  raw/public/     # license-verified downloads (PR2)
  raw/user/       # BYOF Conference / Come Follow Me — never commit
  processed/      # chunks.jsonl, stats (gitignored)
```

## Allowlisted tracked files only

- `data/**/.gitkeep`
- `data/README.md` (this file)
- `data/raw/user/EXAMPLE.meta.json`

CI / `scripts/check_staged_data.py` rejects any other staged path under `data/`,
`indexes/`, or `models/`.

## User file sidecars

For a talk PDF/ePub without good embedded metadata, add `MyTalk.meta.json` next to it:

See `raw/user/EXAMPLE.meta.json`.
