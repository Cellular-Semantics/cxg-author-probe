"""AnnData-zarr ObsReader: builds a real zarr store and drives probe/open_obs.

Offline — a tmp local store written with ``anndata`` (matching production
categorical encoding). ``zarr`` + ``anndata`` are dev/optional deps.
"""
from __future__ import annotations

import warnings

import pytest

zarr = pytest.importorskip("zarr")
ad = pytest.importorskip("anndata")
np = pytest.importorskip("numpy")

import pandas as pd  # noqa: E402

from cxg_author_probe.readers.zarr import ZarrReader  # noqa: E402


@pytest.fixture(scope="module")
def zarr_store(tmp_path_factory):
    """A small AnnData-zarr store mirroring HDCA obs shape."""
    n = 50
    obs = pd.DataFrame(
        {
            # author cell-type column (categorical) — two levels, uneven split
            "refined_celltype": pd.Categorical(["AMACRINE_CELL"] * 30 + ["BIPOLARS"] * 20),
            # descriptor covariate (categorical, homogeneous)
            "organ": pd.Categorical(["Retina"] * 50),
            # numeric (array) column
            "n_genes": np.arange(n, dtype="int32"),
        },
        index=[f"cell{i}" for i in range(n)],
    )
    adata = ad.AnnData(X=np.zeros((n, 3), dtype="float32"), obs=obs)
    path = str(tmp_path_factory.mktemp("z") / "atlas.zarr")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adata.write_zarr(path)
    return path


def test_reader_matches_zarr_suffix():
    assert ".zarr" in ZarrReader.SUPPORTED_SUFFIXES
    assert ZarrReader.FORMAT == "anndata-zarr"


def test_probe_end_to_end(zarr_store):
    from cxg_author_probe import probe

    p = probe(zarr_store, sample_n=20)

    assert p.schema_version == "probe-v1"
    assert p.n_cells == 50
    # format derived from the reader's FORMAT attr — not defaulted to h5ad
    assert p.source.format.value == "anndata-zarr"

    cols = p.columns
    assert set(cols) >= {"refined_celltype", "organ", "n_genes"}

    ct = cols["refined_celltype"]
    assert ct.kind.value == "categorical"
    assert ct.n_categories == 2
    assert ct.n_unique == 2
    # head_sample is the FIRST n rows (first 30 are AMACRINE_CELL), decoded to labels
    assert len(ct.sample) == 20
    assert ct.sample == ["AMACRINE_CELL"] * 20
    assert set(ct.sample) <= {"AMACRINE_CELL", "BIPOLARS"}

    ng = cols["n_genes"]
    assert ng.kind.value == "array"
    assert ng.n_unique == 50  # streamed exact scan over the int column


def test_obs_handle_primitives(zarr_store):
    from cxg_author_probe.readers import open_obs

    h = open_obs(zarr_store)
    try:
        assert h.n_cells() == 50
        assert set(h.list_columns()) == {"refined_celltype", "organ", "n_genes"}

        # head_sample decodes categoricals to labels
        head = h.head_sample("refined_celltype", n=5)
        assert head == ["AMACRINE_CELL"] * 5

        # pull_full round-trips the whole categorical column
        full = h.pull_full("refined_celltype")
        assert len(full) == 50
        assert list(full).count("AMACRINE_CELL") == 30
        assert list(full).count("BIPOLARS") == 20

        # numeric column pulls as-is
        assert h.pull_full("n_genes").tolist() == list(range(50))

        # joinids are the obs index
        assert h.joinids().tolist()[:3] == ["cell0", "cell1", "cell2"]
    finally:
        h.close()


def test_reader_selected_for_zarr_suffix(zarr_store):
    """The built-in zarr reader is dispatched for a .zarr store."""
    from cxg_author_probe.readers.registry import pick_reader

    assert pick_reader(zarr_store) is ZarrReader
