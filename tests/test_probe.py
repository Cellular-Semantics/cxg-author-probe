"""Probe + prompt + pull + assemble + augment against the synthetic fixture."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cxg_author_probe import (
    augment_h5ad,
    build_prompt,
    probe,
    pull_full_column,
    to_long_table,
)
from cxg_author_probe.cache import is_fresh, schema_hash
from cxg_author_probe.models import ColumnKind, Format, ProbeV1


def test_probe_returns_validated_model(synthetic_h5ad: Path):
    url = f"file://{synthetic_h5ad}"
    p = probe(url, dataset_id="synthetic-001")

    assert isinstance(p, ProbeV1)
    assert p.schema_version == "probe-v1"
    assert p.dataset_id == "synthetic-001"
    assert p.source.format == Format.h5ad
    assert p.source.url == url
    assert p.n_cells == 10
    assert p.probe_meta.reader.endswith(".h5ad")
    assert p.probe_meta.package_version

    cols = p.columns
    assert "_index" not in cols  # pseudo-column filtered
    assert set(cols).issuperset(
        {"observation_joinid", "cell_type", "author_cell_type",
         "broad_celltype", "donor_id", "n_counts"}
    )

    ac = cols["author_cell_type"]
    assert ac.kind == ColumnKind.categorical
    assert ac.n_categories == 9       # 10 cells, B-mem appears twice
    assert ac.n_unique == 9
    assert ac.n_unique_estimated is False
    assert ac.sample is not None
    assert ac.sample[0] == "CD4-naive"
    assert ac.sample[1] == "B-mem"

    nc = cols["n_counts"]
    assert nc.kind == ColumnKind.array
    # Small int dtype -> exact streamed scan should populate n_unique
    assert nc.n_unique == 10
    assert nc.n_unique_estimated is False


def test_probe_dumps_to_valid_json(synthetic_h5ad: Path):
    p = probe(f"file://{synthetic_h5ad}", dataset_id="dsid-a")
    s = p.model_dump_json()
    # Round-trips through validation
    p2 = ProbeV1.model_validate_json(s)
    assert p2.dataset_id == p.dataset_id
    assert p2.n_cells == p.n_cells
    assert set(p2.columns.keys()) == set(p.columns.keys())


def test_build_prompt_uses_n_unique_and_excludes_index(synthetic_h5ad: Path):
    p = probe(f"file://{synthetic_h5ad}", dataset_id="dsid-b")
    text = build_prompt(p)

    assert "dsid-b" in text
    assert "AUTHOR-PROVIDED" in text
    assert "_index" not in text  # not in obs columns
    for col in ("author_cell_type", "broad_celltype", "donor_id", "n_counts"):
        assert col in text
    # n_unique appears in the obs-column block
    assert "n_unique" in text
    # 9 is the count for author_cell_type
    assert "  author_cell_type  |  categorical[9 cats]  |  9  |" in text


def test_pull_full_column(synthetic_h5ad: Path):
    url = f"file://{synthetic_h5ad}"
    joinids, cols = pull_full_column(url, ["author_cell_type", "broad_celltype", "missing"])
    assert joinids.shape == (10,)
    assert str(joinids[0]) == "J000"
    assert cols["author_cell_type"][0] == "CD4-naive"
    assert cols["broad_celltype"][0] == "T"
    assert cols["missing"] is None


def test_to_long_table_canonical_shape():
    per_dataset = {
        "ds1": {
            "joinids": np.array(["A", "B", "C"], dtype=object),
            "columns": {
                "celltype": np.array(["T", "B", "NK"], dtype=object),
                "cluster": np.array(["c1", "c2", "c1"], dtype=object),
            },
        },
        "ds2": {
            "joinids": np.array(["X", "Y"], dtype=object),
            "columns": {"celltype": np.array(["mono", "mac"], dtype=object)},
        },
    }
    df = to_long_table(per_dataset)
    assert list(df.columns) == ["observation_joinid", "dataset_id", "author_column", "value"]
    assert len(df) == 8
    row = df[(df.dataset_id == "ds1") & (df.observation_joinid == "B")]
    assert set(row.author_column) == {"celltype", "cluster"}


def test_to_long_drops_nones():
    per = {
        "ds1": {
            "joinids": np.array(["A", "B", "C"], dtype=object),
            "columns": {"ct": np.array(["T", None, "NK"], dtype=object)},
        }
    }
    df = to_long_table(per)
    assert len(df) == 2
    assert "B" not in df.observation_joinid.values


def test_augment_h5ad_adds_columns_in_place(synthetic_h5ad: Path):
    import anndata as ad
    url = f"file://{synthetic_h5ad}"
    joinids, cols = pull_full_column(url, ["author_cell_type"])
    per = {
        "synthetic": {
            "joinids": joinids,
            "columns": {"author_cell_type": cols["author_cell_type"]},
        }
    }
    augment_h5ad(synthetic_h5ad, per)
    after = ad.read_h5ad(synthetic_h5ad)
    assert after.n_obs == 10
    assert "author_author_cell_type" in after.obs.columns
    after.obs["observation_joinid"] = after.obs["observation_joinid"].astype(str)
    paired = dict(zip(after.obs["observation_joinid"], after.obs["author_author_cell_type"]))
    assert paired["J000"] == "CD4-naive"


def test_augment_tolerates_partial_coverage(synthetic_h5ad: Path, tmp_path: Path):
    import shutil
    import anndata as ad

    copy = tmp_path / "to_augment.h5ad"
    shutil.copy(synthetic_h5ad, copy)
    per = {
        "dsX": {
            "joinids": np.array(["J000", "J001"], dtype=object),
            "columns": {"author_cell_type": np.array(["alpha", "beta"], dtype=object)},
        }
    }
    augment_h5ad(copy, per)
    after = ad.read_h5ad(copy)
    assert after.n_obs == 10
    obs = after.obs.copy()
    obs["observation_joinid"] = obs["observation_joinid"].astype(str)
    obs = obs.set_index("observation_joinid")
    assert obs.loc["J000", "author_author_cell_type"] == "alpha"
    assert pd.isna(obs.loc["J005", "author_author_cell_type"])


# ---------------------------------------------------------------------------
# cache helpers
# ---------------------------------------------------------------------------

def test_schema_hash_is_order_independent():
    assert schema_hash(["b", "a"]) == schema_hash(["a", "b"])
    assert schema_hash(["a", "b"]) != schema_hash(["a", "b", "c"])


def test_is_fresh():
    h = schema_hash(["a", "b"])
    assert is_fresh(h, ["b", "a"], None, None)
    assert not is_fresh(h, ["a", "b", "c"], None, None)
    assert is_fresh(h, ["a", "b"], "2026-05-25", "2026-05-25")
    assert not is_fresh(h, ["a", "b"], "2026-05-25", "2026-06-01")
