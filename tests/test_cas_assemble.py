"""build_cas / validate_cas — the structural CAS assembler (pure transform)."""

from __future__ import annotations

import pytest

pytest.importorskip("pandas")

from cxg_author_probe.cas import build_cas, validate_cas  # noqa: E402


def test_two_labelsets_rank_and_hierarchy():
    fine = ["AMACRINE", "AMACRINE", "BIPOLAR", "BIPOLAR", "ROD", "ROD"]
    broad = ["NEURON", "NEURON", "NEURON", "NEURON", "PHOTO", "PHOTO"]
    doc = build_cas(
        {"refined_celltype": fine, "broad_celltype": broad},
        dataset_id="DS1",
        matrix_file_id="file:///x.zarr",
        source_url="file:///x.zarr",
        source_type="local_zarr",
    )
    assert validate_cas(doc) == []

    # finest (most categories) is rank 0
    ranks = {ls["name"]: ls["rank"] for ls in doc["labelsets"]}
    assert ranks == {"refined_celltype": 0, "broad_celltype": 1}

    by = {(a["labelset"], a["cell_label"]): a for a in doc["annotations"]}
    assert by[("refined_celltype", "AMACRINE")]["n_cells"] == 2
    assert (
        by[("refined_celltype", "AMACRINE")]["cell_set_accession"]
        == "DS1:refined_celltype:AMACRINE"
    )
    # hierarchy: fine sets nest under their dominant broad set
    assert (
        by[("refined_celltype", "AMACRINE")]["parent_cell_set_accession"]
        == "DS1:broad_celltype:NEURON"
    )
    assert (
        by[("refined_celltype", "ROD")]["parent_cell_set_accession"] == "DS1:broad_celltype:PHOTO"
    )
    # coarsest has no parent
    assert "parent_cell_set_accession" not in by[("broad_celltype", "NEURON")]
    assert doc["data_provenance"]["n_cells_total"] == 6


def test_single_labelset_no_parent():
    doc = build_cas({"cell_type": ["A", "A", "B"]}, dataset_id="DS2", source_type="local_h5ad")
    assert validate_cas(doc) == []
    assert [ls["rank"] for ls in doc["labelsets"]] == [0]
    assert all("parent_cell_set_accession" not in a for a in doc["annotations"])
    assert {a["cell_label"]: a["n_cells"] for a in doc["annotations"]} == {"A": 2, "B": 1}


def test_empty_columns_raises():
    with pytest.raises(ValueError):
        build_cas({}, dataset_id="DS3")


def test_validate_cas_reports_problems():
    bad = {"schema_version": "cas-v1", "labelsets": [], "annotations": [{"labelset": "x"}]}
    problems = validate_cas(bad)  # annotation missing required cell_label
    assert problems and any("cell_label" in p for p in problems)
