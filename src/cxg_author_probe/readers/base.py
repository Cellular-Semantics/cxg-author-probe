"""Behavioural Protocols for source-format readers.

A reader is the only place format-specific code lives. Everything downstream
talks to obs columns through `ObsHandle` and never imports h5py / zarr / soma
directly. Data structures returned by readers (column descriptors) come from
the schema-generated Pydantic models in `cxg_author_probe.models`.

Adding a new format is therefore: implement one `ObsReader` + register it.
"""
from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

import numpy as np

from cxg_author_probe.models import ColumnDescriptor


@runtime_checkable
class ObsHandle(Protocol):
    """Lazy view into a source dataset's obs."""

    def n_cells(self) -> int:
        ...

    def list_columns(self) -> list[str]:
        """Names of obs columns. Excludes source-internal pseudo-columns
        (e.g. h5ad `_index`)."""
        ...

    def describe(self, col: str) -> ColumnDescriptor:
        """Schema-level metadata for one column. No data read beyond
        what's needed (e.g. category table for categoricals)."""
        ...

    def head_sample(self, col: str, n: int = 20) -> list:
        """First-n column values, decoded to JSON-serialisable Python
        primitives. Categoricals are decoded to category labels."""
        ...

    def iter_chunks(self, col: str) -> Iterator[np.ndarray]:
        """Stream column values chunk-by-chunk. Peak memory is bounded
        by one chunk, regardless of n_cells. Used by full pulls and
        exact n_unique computation."""
        ...

    def pull_full(self, col: str) -> np.ndarray:
        """Convenience: materialise a whole column. Default impl
        concatenates `iter_chunks`; readers may override for efficiency."""
        ...

    def joinids(self) -> np.ndarray:
        """observation_joinid as a 1-D ndarray of strings (decoded)."""
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class ObsReader(Protocol):
    """A factory for `ObsHandle` instances bound to a URL."""

    SUPPORTED_SCHEMES: tuple[str, ...]
    SUPPORTED_SUFFIXES: tuple[str, ...]
    FORMAT: str  # matches cxg_author_probe.models.Format values

    def open(self, url: str) -> ObsHandle:
        ...
