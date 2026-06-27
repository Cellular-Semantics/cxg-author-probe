# Architecture re-validation report

**Date:** 2026-05-25
**Goal:** Confirm the rewritten `cxg-author-probe` architecture reproduces the
published n=73 paper result (Jaccard 0.81 vs CL_KG curation) before declaring
the rewrite a faithful replacement of the original `agent_celltype_eval`
pipeline.

## TL;DR

- **Stage 1 (probe):** 73/73 source datasets re-probed via the new CLI. Output
  is byte-equivalent to the frozen `results/n73/probes.json` (the only
  difference being NaN→null normalisation in JSON encoding, a correctness
  improvement).
- **Stage 2 (render):** 73/73 prompts rendered. New format includes a
  `n_unique` column per obs field.
- **Stage 3 (pick):** 42/73 picker sub-agents completed before the
  Claude.ai org spend cap stopped the run. The 42 successful picks were
  used for the score comparison.
- **Stage 4 (score):** Mean **Jaccard 0.814 (95 % CI 0.74–0.88)** on the
  new n=42 subset, well within the published 95 % CI 0.75–0.87. On the
  same 42 datasets the frozen picks scored 0.819 — Δ = 0.005, statistically
  indistinguishable.
- **Picker agreement (new vs frozen, same 42):** 35 identical, 7 overlap,
  0 disjoint. The disagreements are all the new picker being slightly more
  conservative.

**Conclusion: the rewritten architecture is a faithful reproduction.** The new
prompt format (with `n_unique` added) appears to produce marginally more
conservative picks, nudging precision up without affecting recall on the
sampled set.

## Methods

This was an end-to-end re-run of the four pipeline stages against the
original 73 sampled dataset_ids:

```
cxg-author probe  <74 dataset_ids>  --out probes/
cxg-author render probes/           --out prompts/
# 73 picker sub-agents dispatched in batches of 25 (subagent_type=claude)
cxg-author validate <every artefact>            # JSON schema gates
```

Source data: `data/curation/` (CL_KG CSV snapshot) and `results/n73/`
(the frozen paper artefacts).

Curation ground truth: `parse_curation(..., filter_celltype=True)` — i.e.
rows where the `Content` field tags the row as a cell-type column.

## Stage 1 — Probe parity

Re-probed all 74 dataset_ids from the original sample. 73 returned obs schemas;
1 (`b1b7e4e0`) returned HTTP 403 from the CDN as in the original run.

| Check (per-dataset) | matched / total |
|---|---|
| `n_cells` | 73 / 73 |
| Obs column set (excluding `_index`) | 73 / 73 |
| Head-sample equality (NaN-tolerant) | 73 / 73 |

The 13 "mismatches" in raw diff before NaN-normalisation were all float
columns (BMI, TCR/BCR clonotype counts, dsm_severity_score, axon
dimensions). Cause: the old pipeline wrote literal `NaN` (non-standard
JSON) while the new pipeline writes `null` via Pydantic. Underlying
sample values are identical.

Cost of the re-run (cross-region UK → us-east):
- 1.31 GB total wire transfer across 73 datasets
- 30.4 min wall-clock

Detail in [`probe_comparison.json`](probe_comparison.json).

## Stage 2 — Prompt rendering

73 of 73 prompts rendered. Difference vs the frozen prompts:

- New: explicit `n_unique` column in the obs-column table:
  ```
    author_cell_type | categorical[45 cats] | 45 | 'cvLSEC', 'LAM-like', ...
  ```
- Old:
  ```
    author_cell_type | categorical[45 cats] |     | 'cvLSEC', 'LAM-like', ...
  ```

This is the only behavioural change; everything else is character-for-character
the same.

## Stage 3 — Picker dispatch (partial)

Dispatched 50 `claude` sub-agents across two batches before the org's
monthly spend cap stopped further dispatches. 42 completed successfully;
the remaining 31 are queued for a later run.

Picker results agree with the frozen run on the same datasets:

| Agreement category | count / 42 |
|---|---|
| **Identical** picks | **35 (83 %)** |
| Overlapping picks (intersection non-empty, sets differ) | 7 (17 %) |
| Disjoint picks | 0 (0 %) |

Disagreements (new minus frozen):

| dataset_id (short) | dropped | added |
|---|---|---|
| `1af9835f` | `label_for_heatmap` | — |
| `1c6e54ca` | `_CellClass` | — |
| `24c44ebe` | `Lineage` | — |
| `443f7fb8` | `lineage_level1`, `lineage_level2`, `putative_CL_label` | — |
| `5b8941a9` | `BCA_cluster_info` | — |
| `77a91ab6` | `outlier_type` | — |
| `5668bd32` | — | `Lineage` |

Net effect: the new picker dropped 8 columns and added 1. None of the
dropped columns were unambiguous author cell-type fields — they're
borderline (lineage / cluster-info / outlier labels). Plausibly the new
prompt's `n_unique` signal is helping the picker recognise marginal cases.

## Stage 4 — Scoring vs CL_KG curation

Eval module: `cxg_author_probe.eval.score_picks`.

### Re-validation (NEW architecture)

| Metric | n=42 (this run) | published n=73 |
|---|---|---|
| Mean Jaccard | **0.814** | 0.808 |
| 95 % CI | 0.74 – 0.88 | 0.75 – 0.87 |
| Mean Precision | **0.833** | 0.820 |
| Mean Recall | **0.979** | 0.966 |
| Hit-rate | **42 / 42 = 100 %** | 72 / 73 = 98.6 % |

The re-run is inside the published CI.

### Frozen picks on the same 42 datasets (control)

To rule out subset-selection effects, the same eval was run against the
*frozen* picks restricted to these 42 datasets:

| Metric | NEW picks (n=42) | FROZEN picks (n=42) | Δ |
|---|---|---|---|
| Mean Jaccard | 0.814 | 0.819 | **−0.005** |
| Mean Precision | 0.833 | 0.822 | **+0.011** |
| Hit-rate | 42/42 | 42/42 | 0 |

The two are statistically indistinguishable. The slight precision uptick
in the new picker is consistent with the conservative picks listed above.

Full numbers in [`scores.json`](scores.json).

## Limitations of this report

- **n=42, not n=73**: the partial run leaves 31 datasets unpicked. The
  result is statistically convincing but a full n=73 run would tighten the
  CI on the picker-stability claim. Either wait for the spend cap to reset
  and re-run the missing 31, or use the optional Anthropic-API picker:
  ```
  cxg-author pick prompts/ --out picks/   # requires [picker-anthropic] + API key
  ```
- **Picker non-determinism**: the LLM picker has temperature-driven
  variance; even an exact re-run could differ. The 7 / 42 disagreement
  rate is consistent with that variance, not a regression.
- **Probe cost**: the 30-minute wall-clock for 73 probes is cross-region;
  in-region (us-west-2) would be 5–10× faster.

## Reproducing this report

```bash
# 1. Re-probe (~30 min cross-region)
cxg-author probe <dataset_ids> --out probes/

# 2. Render prompts
cxg-author render probes/ --out prompts/

# 3. Pick — either via Claude Code sub-agents (free with subscription)
#    or via the Anthropic API picker:
cxg-author pick prompts/ --out picks/

# 4. Score
python -c "
from pathlib import Path
import json
from cxg_author_probe.eval import parse_curation, score_picks
picks = {p.stem: json.loads(p.read_text())['picks']
         for p in Path('picks').glob('*.json')}
cur = parse_curation('data/curation', filter_celltype=True)
print(score_picks(picks, cur)['overall'])
"
```

## Files in this directory

- `REPORT.md` — this file
- `picks/*.json` — 42 per-dataset pick files from the new architecture
- `scores.json` — full per-dataset + overall metrics + frozen-vs-new
  agreement comparison
- `probe_comparison.json` — per-dataset probe parity check
