# Curation disagreements (n=42)

Detailed analysis of where the new architecture's picks diverge from
CL_KG hand curation. Companion to [`REPORT.md`](REPORT.md).

## Summary

| Category | Count | % |
|---|---:|---:|
| Exact match (Jaccard = 1) | 22 | 52 % |
| Agent **extras** only (recall = 1, picks ⊇ curation) | 16 | 38 % |
| Agent **misses** only (precision = 1, picks ⊆ curation) | 2 | 5 % |
| Both extras and misses | 1 | 2 % |
| Both empty (trivial agreement) | 1 | 2 % |
| **Disjoint** | **0** | 0 % |

**Every disagreement is either an extra or a near-miss. Never disjoint.** The
agent always finds something in the curated set.

## Extras only (16 datasets)

### Bucket A — generic cluster IDs (9 cases)

Curators chose not to count `seurat_clusters` / `leiden` / `louvain`
etc. as author cell-type fields when their values were bare integers or
cluster IDs. The agent picked them where their values *looked* like cell
labels.

| dataset | curated | agent extras |
|---|---|---|
| `0054013c` | `free_annotation` | `+[leiden, louvain]` |
| `3310476e` | `free_annotation` | `+[leiden, louvain]` |
| `01bc7039` | `author_cell_type` | `+[seurat_clusters]` |
| `36141ff7` | `author_cell_type` | `+[seurat_clusters]` |
| `47de6fa9` | `author_cell_type` | `+[seurat_clusters]` |
| `9fd987e8` | `cell.type.coarse, cell.type.fine, singler` | `+[seurat_clusters]` |
| `1cbe52c1` | `class, subclass.l1, subclass.l2` | `+[cluster_id]` |
| `5d338c19` | `cell_type_fine, cell_type_intermediate, cell_type_main` | `+[initial_clustering]` |
| `18fb432a` | `author_cell_type, broad_lineage, precisest_label, subtype` | `+[dev_state, orig_cluster, orig_sub_cluster]` |

### Bucket B — extra granularity in an already-curated hierarchy (5 cases)

The author offered multiple granularities (broad / fine / cluster).
Curators chose a subset. The agent picked one or more additional layers.

| dataset | curated | agent extras |
|---|---|---|
| `43b216d8` | `_MajorType, _SubType` | `+[_CellClass]` |
| `5668bd32` | `Cell.class, Cell.group` | `+[Lineage]` |
| `839cae6e` | `CrossArea_cluster, CrossArea_subclass, WithinArea_cluster, WithinArea_subclass` | `+[Class]` |
| `60b76da3` | `celltype.final` | `+[celltype.broad_clustering_annot]` |
| `77a91ab6` | `cell_type_alias, cell_type_alt_alias, class, cluster, subclass` | `+[cell_type_designation]` |

### Bucket C — cross-naming convention (1 case)

| dataset | curated | agent extras |
|---|---|---|
| `24c44ebe` | `sub_cluster` | `+[Cell.class, Cell.group]` |

This is the same author-naming convention as `5668bd32`. The agent
recognised it; curation didn't. **Plausibly a curation gap.**

### Bucket D — imaging / RNA-class author categories (1 case)

| dataset | curated | agent extras |
|---|---|---|
| `460d368c` | `BICCN_cluster_label, BICCN_subclass_label` | `+[ALMVISp top-3, RNA family, RNA type top-3]` |

These are morphology / RNA-class annotations — defensible as
"author cell-type-like" picks but outside the curators' scope.

## Misses only (2 datasets)

| dataset | picked | missed | comment |
|---|---|---|---|
| `1af9835f` | `BICCN_cluster_label, BICCN_subclass_label` | `label_for_heatmap` | Display-purpose variant of the picked label; defensible omission. |
| `443f7fb8` | `celltype_level1/2/3/3_fullname` | `lineage_level1, lineage_level2` | Higher-level lineage taxon. Genuine judgement call; agent's reasoning string says "lineage_* are higher-level lineage/compartment rather than cell-type." |

## Both extras and misses (1 dataset)

| dataset | extra | miss |
|---|---|---|
| `5b8941a9` | `+[Main_cluster_name]` (singular) | `-[Main_cluster_names]` (plural) |

The probe schema for this source h5ad contains only the singular form —
**the curation has a typo**. The agent picked correctly; the
disagreement is curator-side error.

## Categorical summary

| Pattern | Count | Verdict |
|---|---:|---|
| Generic cluster IDs picked as labels | 9 | Definitional disagreement (pandasaurus would count these; CL_KG curators didn't) |
| Extra hierarchy tier picked | 5 | Defensible — same author convention, finer/broader granularity |
| Cross-naming convention extras | 1 | **Likely curation gap** |
| Imaging/RNA-class extras | 1 | Borderline (author-provided categorical, just not strictly cell-type) |
| Display-variant miss | 1 | Defensible omission |
| Higher-taxon miss | 1 | Judgement call |
| Spelling-variant disagreement | 1 | **Likely curation typo** (agent correct) |

**~88 % of disagreements** fall into the top two buckets, which are
**definitional choices** rather than agent errors. The remaining cases
are either defensible omissions, borderline picks, or — in at least
two of them — surface curation issues that the agent caught.
