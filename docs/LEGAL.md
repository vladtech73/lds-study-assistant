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

PR2 fills concrete `license_url` / `verified_on` values when a mirror is chosen.
Until then, `configs/sources.yaml` stays empty / unverified.

## Church-copyrighted materials

General Conference talks and Come, Follow Me manuals are © Intellectual Reserve, Inc.

- **Bring-your-own-files only** under `data/raw/user/` (gitignored).
- Never commit, never publish embeddings/adapters/datasets derived from them.
- `redistributable: false` is enforced in code (PR2+) with **no override flag**.

## Scraping

No default scraper for churchofjesuschrist.org. Any future fetcher must be opt-in,
rate-limited, robots.txt-respecting, single-user, and labeled personal-use only.

## Code license vs content

The MIT license covers **repository code**. It does not license third-party scripture
editions or Church publications. See `NOTICE.md` and `DISCLAIMER.md`.
