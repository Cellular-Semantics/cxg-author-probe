"""Parse CL_KG curation CSVs into per-dataset ground truth.

The CL_KG curation CSVs contain rows of the form
    (dataset_id, content_kind, author_column, ...)
where `content_kind` (the "Content" column) distinguishes cell-type-relevant
rows from other author-category rows (BCR/TCR clonotypes, demographics, etc).
We filter on `Content` and return only the cell-type rows as ground truth.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")

CELL_TYPE_CONTENT = {
    "cell types",
    "cell type",
    "cell type and infection source",
}


def parse_curation(
    curation_dir: str | Path,
    *,
    filter_celltype: bool = True,
) -> dict[str, dict]:
    """Parse all curation CSVs into per-dataset ground truth.

    Parameters
    ----------
    curation_dir : path
        Directory of curation CSVs (the CL_KG snapshot under data/curation/).
    filter_celltype : bool
        When True (default), keep only rows whose `Content` field matches
        a cell-type tag. The unfiltered set inflates the curated column count
        with non-cell-type author categories and is not directly useful for
        picker evaluation.

    Returns
    -------
    {dataset_id: {"groups": sorted-list, "columns": sorted-list, "rows": int}}
    """
    curation_dir = Path(curation_dir)
    by_dataset: dict[str, dict] = defaultdict(
        lambda: {"groups": set(), "columns": set(), "rows": 0}
    )

    for path in sorted(curation_dir.glob("*.csv")):
        group = path.stem
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                row = {
                    (k.strip() if k else k): (v.strip() if isinstance(v, str) else v)
                    for k, v in row.items()
                }
                if filter_celltype:
                    content = (row.get("Content") or "").lower()
                    if content not in CELL_TYPE_CONTENT:
                        continue
                m = UUID_RE.search(row.get("h5ad link", ""))
                if not m:
                    continue
                col = row.get("Author Category Cell Type Field Name") or ""
                if not col or col.lower() in {"n/a", "na", "none", "-"}:
                    continue
                dsid = m.group(1)
                by_dataset[dsid]["groups"].add(group)
                by_dataset[dsid]["columns"].add(col)
                by_dataset[dsid]["rows"] += 1

    return {
        dsid: {
            "groups": sorted(v["groups"]),
            "columns": sorted(v["columns"]),
            "rows": v["rows"],
        }
        for dsid, v in by_dataset.items()
    }
