"""AnnData-zarr ObsReader.

Reads only ``obs`` (never X/var), decoding the AnnData categorical encoding
(``categories`` + ``codes``, ``-1`` = NaN) for both zarr v2 and v3 stores.
``ZarrReader`` is a built-in reader (registered statically in
``readers.registry``); ``probe`` derives ``source.format`` from the reader's
``FORMAT`` attribute, so this module can live anywhere.

``zarr`` / ``numpy`` are imported lazily so importing this module never requires
the ``[zarr]`` extra until a store is actually opened.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse


def _open_zarr_group(url: str) -> Any:
    """Open the root AnnData-zarr group at ``url`` read-only (local or remote)."""
    import zarr

    parsed = urlparse(url)
    if parsed.scheme in ("", "file"):
        path = parsed.path if parsed.scheme == "file" else url
        return zarr.open_group(path, mode="r")
    # Remote (http/https/s3/gs) via fsspec.
    try:
        from zarr.storage import FsspecStore

        store: Any = FsspecStore.from_url(url, read_only=True)
    except Exception:
        import fsspec

        store = fsspec.get_mapper(url)
    return zarr.open_group(store=store, mode="r")


class _ZarrObsHandle:
    """Lazy view into an AnnData-zarr ``obs`` group (ObsHandle Protocol)."""

    def __init__(self, root: Any) -> None:
        import numpy as np

        self._np = np
        self._root = root
        self._obs = root["obs"]
        self._attrs = dict(self._obs.attrs)
        self._index = self._attrs.get("_index", "_index")

    # --- structure helpers ---------------------------------------------------
    def _is_group(self, node: Any) -> bool:
        import zarr

        return isinstance(node, zarr.Group)

    def _enc(self, node: Any) -> str | None:
        attrs = getattr(node, "attrs", None)
        return dict(attrs).get("encoding-type") if attrs is not None else None

    def _is_categorical(self, node: Any) -> bool:
        return self._is_group(node) and self._enc(node) == "categorical"

    def _is_nullable(self, node: Any) -> bool:
        # AnnData >=0.13 stores string/nullable columns (and the index) as a
        # group {values, mask} with encoding-type "nullable-*-array".
        return self._is_group(node) and str(self._enc(node) or "").startswith("nullable")

    def _decode(self, values: Any) -> list:
        """Decode a numpy array of obs values to JSON-serialisable primitives."""
        arr = self._np.asarray(values)
        return [v.decode() if isinstance(v, bytes) else v for v in arr.tolist()]

    def _read_nullable(self, node: Any, lo: int = 0, hi: int | None = None) -> list:
        """Decode a nullable-*-array group's [lo:hi] slice, applying its NA mask."""
        sl = slice(lo, hi)
        vals = self._decode(node["values"][sl])
        if "mask" in node:
            mask = self._np.asarray(node["mask"][sl]).tolist()
            vals = [None if m else v for v, m in zip(vals, mask, strict=False)]
        return vals

    def _node_len(self, node: Any) -> int:
        if self._is_categorical(node):
            return int(node["codes"].shape[0])
        if self._is_nullable(node):
            return int(node["values"].shape[0])
        return int(node.shape[0])

    # --- ObsHandle Protocol --------------------------------------------------
    def n_cells(self) -> int:
        return self._node_len(self._obs[self._index])

    def list_columns(self) -> list[str]:
        cols = list(self._attrs.get("column-order", []))
        return [c for c in cols if c != self._index]

    def describe(self, col: str) -> Any:
        from cxg_author_probe.models import ColumnDescriptor, ColumnKind

        node = self._obs[col]
        if self._is_categorical(node):
            cats = node["categories"]
            codes = node["codes"]
            n_cat = int(cats.shape[0])
            return ColumnDescriptor(
                kind=ColumnKind.categorical,
                dtype=str(cats.dtype),
                n_unique=n_cat,  # categorical n_unique == n_categories (probe expects it preset)
                n_categories=n_cat,
                shape=list(codes.shape),
                encoding="categorical",
            )
        if self._is_nullable(node):
            values = node["values"]
            return ColumnDescriptor(
                kind=ColumnKind.array,
                dtype=str(values.dtype),
                shape=list(values.shape),
                encoding=self._enc(node),
            )
        if self._is_group(node):
            return ColumnDescriptor(
                kind=ColumnKind.group,
                dtype="group",
                encoding=self._enc(node),
            )
        return ColumnDescriptor(
            kind=ColumnKind.array,
            dtype=str(node.dtype),
            shape=list(node.shape),
            encoding=self._enc(node) or "array",
        )

    def head_sample(self, col: str, n: int = 20) -> list:
        node = self._obs[col]
        if self._is_categorical(node):
            cats = self._decode(node["categories"][:])
            codes = self._np.asarray(node["codes"][:n])
            return [cats[c] if c >= 0 else None for c in codes.tolist()]
        if self._is_nullable(node):
            return self._read_nullable(node, 0, n)
        return self._decode(node[:n])

    def iter_chunks(self, col: str) -> Iterator[Any]:
        yield from self._iter_node(self._obs[col])

    def _iter_node(self, node: Any) -> Iterator[Any]:
        np = self._np
        if self._is_categorical(node):
            cats = np.asarray(self._decode(node["categories"][:]), dtype=object)
            codes = node["codes"]
            step = codes.chunks[0] if getattr(codes, "chunks", None) else codes.shape[0]
            for i in range(0, codes.shape[0], step or codes.shape[0]):
                block = np.asarray(codes[i : i + step])
                yield np.array([cats[c] if c >= 0 else None for c in block.tolist()], dtype=object)
        elif self._is_nullable(node):
            values = node["values"]
            step = values.chunks[0] if getattr(values, "chunks", None) else values.shape[0]
            for i in range(0, values.shape[0], step or values.shape[0]):
                yield np.array(self._read_nullable(node, i, i + step), dtype=object)
        else:
            step = node.chunks[0] if getattr(node, "chunks", None) else node.shape[0]
            for i in range(0, node.shape[0], step or node.shape[0]):
                yield np.asarray(node[i : i + step])

    def pull_full(self, col: str) -> Any:
        np = self._np
        chunks = [np.asarray(c) for c in self.iter_chunks(col)]
        if not chunks:
            return np.array([])
        return np.concatenate(chunks)

    def joinids(self) -> Any:
        node = self._obs[self._index]
        if self._is_nullable(node):
            return self._np.asarray(self._read_nullable(node), dtype=object)
        if self._is_categorical(node):
            return self._np.concatenate([c for c in self._iter_node(node)])
        return self._np.asarray(self._decode(node[:]), dtype=object)

    def close(self) -> None:  # nothing to release for read-only local/fsspec stores
        pass


class ZarrReader:
    """Factory binding a URL to a :class:`_ZarrObsHandle`."""

    SUPPORTED_SCHEMES: tuple[str, ...] = ("http", "https", "file", "s3", "gs")
    SUPPORTED_SUFFIXES: tuple[str, ...] = (".zarr", ".zarr/")
    FORMAT: str = "anndata-zarr"

    def open(self, url: str) -> _ZarrObsHandle:
        return _ZarrObsHandle(_open_zarr_group(url))
