# Legal notes

This is not legal advice. It documents how **this repo** treats sources so
contributors do not accidentally redistribute restricted material.

## Text vs edition

It is incorrect to say “the standard works are public domain” as a blanket claim.

- **Underlying 19th-century texts** of the Book of Mormon, KJV Bible, Doctrine and
  Covenants, and Pearl of Great Price are generally out of copyright in many
  jurisdictions.
- **Modern published editions** add copyrightable apparatus: versification choices,
  chapter headings, footnotes, cross-references, section introductions, Topical Guide,
  Bible Dictionary, and post-1920 additions (e.g. Official Declaration 2, 1978).

**Policy in this project:**

1. License status is decided **per entry** in `configs/sources.yaml`
   (`license`, `license_url`, `verified_on`, `notes`).
2. Entries with `license: unverified` **cannot be ingested**.
3. Normalization **strips** headings, footnotes, and study aids before indexing.
4. Mirror provenance is only as good as the mirror’s claims — treat as a residual risk.

## Chosen public-domain mirror (PR2)

| Field | Value |
|---|---|
| Mirror | [scriptures.nephi.org](https://scriptures.nephi.org/) / `beandog/lds-scriptures` |
| Tag / dump | `2020.12.08` |
| Artifact | `json/lds-scriptures-json.txt` (verse-only JSON array) |
| SHA-256 | `8797555ccdf4a4d3f5846211aa6ff2b5bb74e97c3264ce48e2ec0933b13bd7e8` |
| Verified on | 2026-07-20 |
| License claim | Project states scriptures, original works, and documentation are **public domain** in the USA |
| Apparatus | Dump **omits** chapter headings, footnotes, Topical Guide, Bible Dictionary, indexes |
| Official Declarations | **None present** in this dump (avoids the post-1920 OD-2 question for v1) |

Expected per-volume verse counts for this dump are committed in
`configs/verse_counts.yaml` (`total: 41995`). `lds prepare --scripture-only` should
match those counts when the full artifact is present under `data/raw/public/`.

**Residual risk:** we trust the mirror’s provenance claims; we do not independently
re-derive the text from 19th-century printings. If a future dump adds modern apparatus
or Official Declarations, refuse or strip before indexing and bump `verified_on` only
after a human review.

## Church-copyrighted materials

General Conference talks and Come, Follow Me manuals are © Intellectual Reserve, Inc.

- **Bring-your-own-files only** under `data/raw/user/` (gitignored).
- Never commit, never publish embeddings/adapters/datasets derived from them.
- `redistributable: false` is enforced in code with **no override flag**.

## Scraping

No default scraper for churchofjesuschrist.org. Any future fetcher must be opt-in,
rate-limited, robots.txt-respecting, single-user, and labeled personal-use only.

## Code license vs content

The MIT license covers **repository code**. It does not license third-party scripture
editions or Church publications. See `NOTICE.md` and `DISCLAIMER.md`.
