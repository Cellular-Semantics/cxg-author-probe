"""Shared fixtures."""
from __future__ import annotations

from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_h5ad(tmp_path: Path) -> Path:
    """A small h5ad with categorical + non-categorical obs columns.

    10 cells. Includes observation_joinid (required by the assemble/augment
    path), the CELLxGENE-standardised cell_type field, an author_cell_type
    categorical, a broad_celltype categorical, a donor_id categorical, and
    an n_counts integer column.
    """
    n = 10
    obs = pd.DataFrame(
        {
            "observation_joinid": [f"J{i:03d}" for i in range(n)],
            "cell_type": pd.Categorical(
                ["T cell", "B cell", "NK cell", "T cell", "B cell",
                 "T cell", "monocyte", "monocyte", "T cell", "B cell"]
            ),
            "author_cell_type": pd.Categorical(
                ["CD4-naive", "B-mem", "NK-bright", "CD4-EM", "B-naive",
                 "CD8-EM", "cMono", "ncMono", "CD8-CM", "B-mem"]
            ),
            "broad_celltype": pd.Categorical(
                ["T", "B", "NK", "T", "B", "T", "Mono", "Mono", "T", "B"]
            ),
            "donor_id": pd.Categorical([f"d{i % 3}" for i in range(n)]),
            "n_counts": np.arange(n, dtype=np.int32) * 100,
        },
        index=[f"cell_{i}" for i in range(n)],
    )
    var = pd.DataFrame(index=["g1", "g2", "g3"])
    X = np.zeros((n, 3), dtype=np.float32)
    adata = ad.AnnData(X=X, obs=obs, var=var)

    path = tmp_path / "synthetic.h5ad"
    adata.write_h5ad(path)
    return path
