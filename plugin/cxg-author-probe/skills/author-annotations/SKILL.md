---
name: author-annotations
description: Retrieve author-provided cell-type annotations from CELLxGENE source datasets via cheap HTTPS range-reads, then emit a long-format Parquet table and/or augment a Census-derived h5ad. Use when a query has produced dataset_ids and the user wants author labels beyond the CELLxGENE-standardised cell_type field.
user-invocable: true
---

# Author annotations

CELLxGENE Census strips dataset-specific author cell-type fields (e.g. `BICCN_subclass_label`, `celltype`, `cell_type_fine`, `Cell.class`) during ingest — they survive only in the per-dataset **source datasets**. This skill recovers them on demand with no manual curation: a cheap HTTPS range-read probes each source's obs schema + a 20-row sample of every column, the `author-category-picker` sub-agent picks the author cell-type columns from that probe, then full values are pulled for the picked columns and assembled into a long-format table (and optionally written back into an existing h5ad's `obs`).

Benchmark on n=73 datasets vs CL_KG hand curation: **Jaccard 0.81, recall 0.97, hit-rate 99 %** — see [paper.md](https://github.com/Cellular-Semantics/cxg-author-probe/blob/main/paper.md).

The skill delegates all data-fetching, schema, and assembly work to the `cxg-author` CLI (from the `cxg-author-probe` PyPI package). The host environment must have it installed.

---

## Prerequisites

```bash
pip install cxg-author-probe>=0.1
```

`cxg-author --help` should work. If it doesn't, the skill cannot run.

## When to invoke

- After a `cxg-query` (or any) execution that produced `dataset_id`s and the user asks for author labels, cell-type granularity beyond CL, marker-encoded cluster names, or "the original annotations".
- Standalone, when the user names dataset_ids directly.

If the user only wants the standardised CELLxGENE `cell_type` field, this skill is not needed.

## Modes

1. **Augment an existing query output** — pass a path to a previously-produced `*.h5ad` or `*.parquet`. The skill reads `dataset_id`s from it, fetches author columns, writes a sibling `*_author.parquet` table, and (for h5ad inputs) writes the augmented `obs` back in place.
2. **Fresh dataset list** — pass one or more `dataset_id`s. The skill probes them and emits `outputs/{slug}_{timestamp}_author.parquet`.

## Pipeline

### Step 1 — Collect dataset_ids
Parse the user's literal list, or read `obs['dataset_id'].unique()` from the supplied file. Deduplicate.

### Step 2 — Probe via the CLI
```bash
cxg-author probe <dsid>... --out probes/
```
- One JSON per dataset under `probes/<dsid>.json`, conforming to `probe-v1`.
- Cached: re-runs skip already-probed datasets unless `--force`.
- Independent per dataset — run in parallel where useful.

### Step 3 — Render prompts
```bash
cxg-author render probes/ --out prompts/
```

### Step 4 — Pick (sub-agent dispatch)
For each prompt file, dispatch the `author-category-picker` sub-agent in parallel via the **`Task` tool** with `subagent_type=author-category-picker`. Pass two arguments to each agent:

- the prompt file path (read-only input)
- the output JSON path where the agent must write its `{"picks": [...], "reasoning": "..."}`

Recommended target path: `picks/<dsid>.json`. After the sub-agent writes, wrap the result into a `picks-v1` envelope:

```json
{
  "schema_version": "picks-v1",
  "dataset_id": "<dsid>",
  "probe_ref": "probes/<dsid>.json",
  "picks": [...],
  "reasoning": "...",
  "picker": {"kind": "claude-code-subagent", "model": "sonnet"},
  "picked_at": "..."
}
```

### Step 5 — Pull picked-column values
```bash
cxg-author pull picks/ --probes probes/ --out pulled/
```
Writes `pulled/<dsid>.json` (sidecar) + `pulled/<dsid>.parquet` (data).

### Step 6 — Assemble or augment

For breakdown deliverable (d) — **long-format table**:
```bash
cxg-author assemble pulled/ --out outputs/<slug>_<ts>_author.parquet
```

For breakdown deliverable (e) — **augment h5ad in place**:
```bash
cxg-author augment outputs/<file>.h5ad --pulled pulled/
```

### Step 7 — Report

Always summarise to the user:
- Datasets probed (N successful / N attempted)
- Picks per dataset
- Output paths
- Any datasets with empty picks (note: potential curation gap)

## Important notes

- The CELLxGENE datasets CDN (`https://datasets.cellxgene.cziscience.com/{dsid}.h5ad`) is used directly, not the Census S3 mirror — Census `dataset_id`s drift across releases but the CDN URL is stable for any dataset_id that has been ingested.
- This skill does **not** download the expression matrix. Bandwidth scales with obs size, not file size.
- The `author-category-picker` sub-agent is a fresh context per dataset — no cross-dataset leakage.
- For deployment with no AWS credentials (e.g. an external user), the HTTPS approach works as-is. In-region access drops latency ~5–10× but is not required.

## References

- [`references/templates.md`](references/templates.md) — copy-paste code recipes for each mode.
- [Paper](https://github.com/Cellular-Semantics/cxg-author-probe/blob/main/paper.md) — benchmark methodology and limitations.
- [JSON schemas](https://github.com/Cellular-Semantics/cxg-author-probe/tree/main/schemas) — `probe-v1`, `picks-v1`, `pulled-v1`.
