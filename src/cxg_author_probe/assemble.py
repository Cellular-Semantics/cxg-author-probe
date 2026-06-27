"""Long-format table + in-place h5ad obs augment."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

# Per-dataset pull result shape:
#   {dataset_id: {"joinids": ndarray, "columns": {col: ndarray | None}}}
PerDataset = Mapping[str, Mapping[str, object]]


def to_long_table(per_dataset: PerDataset) -> pd.DataFrame:
    """Assemble (observation_joinid, dataset_id, author_column, value) rows."""
    frames: list[pd.DataFrame] = []
    for dsid, payload in per_dataset.items():
        joinids = payload.get("joinids")
        columns = payload.get("columns") or {}
        if joinids is None or len(joinids) == 0:
            continue
        for col_name, values in columns.items():  # type: ignore[union-attr]
            if values is None:
                continue
            df = pd.DataFrame(
                {
                    "observation_joinid": joinids,
                    "dataset_id": dsid,
                    "author_column": col_name,
                    "value": values,
                }
            )
            df = df[df["value"].notna()]
            frames.append(df)
    if not frames:
        return pd.DataFrame(
            columns=["observation_joinid", "dataset_id", "author_column", "value"]
        )
    out = pd.concat(frames, ignore_index=True)
    out["observation_joinid"] = out["observation_joinid"].astype(str)
    out["value"] = out["value"].astype(str)
    return out


def augment_h5ad(h5ad_path: str | Path, per_dataset: PerDataset) -> None:
    """Add picked author columns to an existing h5ad's obs in-place.

    Each picked column becomes ``author_<col_name>`` in ``adata.obs``,
    joined on ``observation_joinid``. Cells without picks remain NaN —
    cell count is unchanged.
    """
    import anndata  # heavy import deferred

    h5ad_path = Path(h5ad_path)
    adata = anndata.read_h5ad(h5ad_path)
    if "observation_joinid" not in adata.obs.columns:
        raise ValueError(
            f"{h5ad_path}: obs has no observation_joinid; cannot join author "
            "annotations."
        )

    long = to_long_table(per_dataset)
    if long.empty:
        return

    wide = long.pivot_table(
        index="observation_joinid",
        columns="author_column",
        values="value",
        aggfunc="first",
    )
    wide.columns = [f"author_{c}" for c in wide.columns]

    obs = adata.obs.copy()
    obs["observation_joinid"] = obs["observation_joinid"].astype(str)
    obs = obs.merge(wide, how="left", left_on="observation_joinid", right_index=True)
    adata.obs = obs
    adata.write_h5ad(h5ad_path)
