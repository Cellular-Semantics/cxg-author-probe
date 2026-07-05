"""ObsHandle verification gate: passes real readers, flags broken ones."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from cxg_author_probe.models import ColumnDescriptor, ColumnKind
from cxg_author_probe.readers import (
    ObsHandleVerificationError,
    check_obs_handle,
    open_obs,
    verify_obs_handle,
)


# --- positive: real readers pass ------------------------------------------------
def test_real_h5ad_handle_passes(synthetic_h5ad: Path):
    h = open_obs(f"file://{synthetic_h5ad}")
    try:
        assert check_obs_handle(h) == []
        assert check_obs_handle(h, deep=True) == []
        verify_obs_handle(h, deep=True)  # does not raise
    finally:
        h.close()


def test_real_zarr_handle_passes(tmp_path_factory):
    zarr = pytest.importorskip("zarr")  # noqa: F841
    ad = pytest.importorskip("anndata")
    np = pytest.importorskip("numpy")
    import pandas as pd

    n = 20
    obs = pd.DataFrame(
        {
            "refined_celltype": pd.Categorical(["A"] * 12 + ["B"] * 8),
            "n_genes": np.arange(n, dtype="int32"),
        },
        index=[f"cell{i}" for i in range(n)],
    )
    adata = ad.AnnData(X=np.zeros((n, 2), dtype="float32"), obs=obs)
    path = str(tmp_path_factory.mktemp("z") / "atlas.zarr")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adata.write_zarr(path)

    h = open_obs(f"file://{path}")
    try:
        assert check_obs_handle(h, deep=True) == []
    finally:
        h.close()


# --- negative: fake handles, one broken invariant each --------------------------
class _GoodFake:
    """A minimal well-behaved ObsHandle over 4 cells, one array column."""

    _n = 4
    _vals = [0, 1, 2, 3]

    def n_cells(self) -> int:
        return self._n

    def list_columns(self) -> list[str]:
        return ["a"]

    def describe(self, col: str) -> ColumnDescriptor:
        return ColumnDescriptor(kind=ColumnKind.array, dtype="int64", shape=[self._n])

    def head_sample(self, col: str, n: int = 20) -> list:
        return self._vals[:n]

    def pull_full(self, col: str):
        return list(self._vals)

    def iter_chunks(self, col: str):
        yield list(self._vals)

    def joinids(self):
        return [f"c{i}" for i in range(self._n)]

    def close(self) -> None:
        pass


def test_good_fake_passes():
    assert check_obs_handle(_GoodFake(), deep=True) == []


class _BadHeadLen(_GoodFake):
    def head_sample(self, col: str, n: int = 20):
        return self._vals[:2]  # too short


class _BytesHead(_GoodFake):
    def head_sample(self, col: str, n: int = 20):
        return [b"\x00", b"\x01", b"\x02", b"\x03"]  # undecoded


class _BadJoinLen(_GoodFake):
    def joinids(self):
        return ["c0", "c1"]  # length != n_cells


class _BadDescribe(_GoodFake):
    def describe(self, col: str):
        return {"kind": "array"}  # not a ColumnDescriptor


class _BadDeepPull(_GoodFake):
    def pull_full(self, col: str):
        return [0, 1]  # length != n_cells (only caught with deep=True)


@pytest.mark.parametrize(
    "handle, needle",
    [
        (_BadHeadLen(), "head_sample('a') length"),
        (_BytesHead(), "undecoded bytes"),
        (_BadJoinLen(), "joinids() length"),
        (_BadDescribe(), "expected ColumnDescriptor"),
    ],
)
def test_broken_handle_flagged(handle, needle):
    problems = check_obs_handle(handle)
    assert any(needle in p for p in problems), problems
    with pytest.raises(ObsHandleVerificationError):
        verify_obs_handle(handle)


def test_deep_only_catch():
    # pull_full length mismatch is invisible to the default (shallow) check…
    assert check_obs_handle(_BadDeepPull()) == []
    # …but caught under deep verification.
    problems = check_obs_handle(_BadDeepPull(), deep=True)
    assert any("pull_full('a') length" in p for p in problems), problems
