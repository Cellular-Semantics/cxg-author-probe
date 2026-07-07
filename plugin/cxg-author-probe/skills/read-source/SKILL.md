---
name: read-source
description: Turn an arbitrary single-cell data source — a file/URL, a GEO accession, an atlas web page, a portal link — into a VERIFIED structured obs view the annotation pipeline can consume. Recognises shapes the built-in readers already handle (cheap path) and, when they don't, works freely to construct obs (retrieve, combine files, parse tables), accepting only a result that passes verification. Use before probe/pull when a source isn't a plain CELLxGENE h5ad.
user-invocable: true
---

# Read a source into a verified obs

The built-in readers (`h5ad`, `anndata-zarr`) cover the common containers. Real
sources are messier — an atlas web page that hides a zarr URL, a GEO series of
gzipped TSVs, a portal export where cell metadata lives in a separate file from
the matrix. This skill reaches the goal — **a structured `obs` that passes
verification** — by working freely, while staying cheap when the shape is
already one we have code for.

The one hard rule: **only an obs view that passes `cxg-author verify` is
trusted.** Everything else is best-effort means to that end.

## Prerequisites

```bash
cxg-author --help   # cxg-author-probe installed in the host env
```

## Input

Whatever the user gives: a file path or data URL, a GEO accession (`GSE…`), an
atlas/portal page URL, or a study id. Your job is to get from that to a verified
obs.

## Procedure

### 1. Resolve the source to concrete data (retrieve)
- A **direct file/URL** (`.h5ad`, `.zarr`, …) → use as-is.
- An **atlas/portal page** → find the underlying data URL (inspect the page /
  its network requests; a zarr store shows up as range-reads of
  `.../store.zarr/...`).
- A **GEO accession** → list its supplementary files
  (`https://ftp.ncbi.nlm.nih.gov/geo/series/GSEnnnNNN/<acc>/suppl/`); identify
  the matrix and any separate cell-metadata file.
- Note when obs and matrix are **separate files** that must be combined.

### 2. Try the cheap path first — is it a shape we already read?
```bash
cxg-author verify "<url-or-path>"
```
- **Exit 0** → done. A built-in reader handled it and the obs view is valid.
  Hand the URL to `cxg-author probe` and the rest of the pipeline.
- **Exit 1** (no reader, or verification problems) → go to step 3.

### 3. Improvise — construct obs by any means (only when step 2 fails)
Work freely to produce a structured obs, then normalise it into a shape a
built-in reader accepts:
- Inspect the file(s) with whatever fits (zarr/h5py listing, reading a TSV/CSV
  header, decompressing a `.gz`).
- If cell metadata is a **delimited table** (common for GEO/portal exports),
  parse it; combine with matrix cell order if needed.
- Write a **minimal standard artifact** — a small `.h5ad`/`.zarr` containing
  **only `obs`** (never the expression matrix) — to a temp path.
- Verify it:
  ```bash
  cxg-author verify "<temp-obs-artifact>"
  ```
  On exit 1, read the printed problems and fix your normalisation. Retry a few
  times, then stop.

This improvisation is **ephemeral, for this run**. It is fine to write and run
temporary code here.

### 4. Report
- Success: the verified source/artifact, `n_cells`, and the obs columns — hand
  it downstream (probe → pick → pull → …).
- No annotations: some sources (e.g. a bare GEO counts/TPM matrix) carry **no
  per-cell author annotation** at all. Say so plainly rather than inventing one.

## Rules

- **Never edit the installed `cxg_author_probe` package.** Improvising within a
  run is fine; making a reader permanent is a separate, human-reviewed step —
  if a source shape recurs and is worth a built-in reader, flag it for a PR.
- **Obs only.** Never download or normalise the expression matrix (`X`) / `var`.
- Prefer the cheap built-in path (step 2); improvise (step 3) only when it fails.
