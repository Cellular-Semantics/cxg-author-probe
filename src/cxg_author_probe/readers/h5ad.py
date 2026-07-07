"""HDF5 / .h5ad obs reader.

Opens any HDF5 file accessible via fsspec (`https://`, `s3://`, `file://`),
reads only the `/obs` group, never touches `/X` or any other top-level group.
Class-level `_fetch_range` instrumentation on `HTTPFile` measures bytes-on-
wire across nested probes via a counter stack.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import fsspec
import h5py
import numpy as np
from fsspec.implementations.http import HTTPFile

from cxg_author_probe.models import ColumnDescriptor, ColumnKind

# ---------------------------------------------------------------------------
# Bytes-on-wire counter (class-level patch with a stack for nesting/concurrency).
# fsspec drives reads through an asyncio loop and looks up `_fetch_range`
# on the class — instance-level wrapping doesn't intercept the path that
# actually fetches bytes. Stack supports nested probes / concurrent pulls.
# ---------------------------------------------------------------------------

_PATCH_HOLDERS = 0
_PATCH_ORIG = None
_PATCH_STATS_STACK: list[dict[str, int]] = []


def _push_byte_counter(stats: dict[str, int]) -> None:
    global _PATCH_HOLDERS, _PATCH_ORIG
    _PATCH_STATS_STACK.append(stats)
    if _PATCH_HOLDERS == 0:
        _PATCH_ORIG = HTTPFile._fetch_range

        def counting(self, start, end, *args, **kwargs):
            data = _PATCH_ORIG(self, start, end, *args, **kwargs)
            for s in _PATCH_STATS_STACK:
                s["n"] += len(data)
                s["calls"] += 1
            return data

        HTTPFile._fetch_range = counting  # type: ignore[method-assign]
    _PATCH_HOLDERS += 1


def _pop_byte_counter(stats: dict[str, int]) -> None:
    global _PATCH_HOLDERS, _PATCH_ORIG
    if stats in _PATCH_STATS_STACK:
        _PATCH_STATS_STACK.remove(stats)
    _PATCH_HOLDERS -= 1
    if _PATCH_HOLDERS == 0 and _PATCH_ORIG is not None:
        HTTPFile._fetch_range = _PATCH_ORIG  # type: ignore[method-assign]
        _PATCH_ORIG = None


@contextmanager
def byte_counter(stats: dict[str, int]):
    """Wrap an arbitrary code region in a byte counter.

    Caller passes a writeable dict — keys "n" (bytes) and "calls" (GETs) are
    initialised to 0 and incremented inside the block.
    """
    stats["n"] = 0
    stats["calls"] = 0
    _push_byte_counter(stats)
    try:
        yield stats
    finally:
        _pop_byte_counter(stats)


# ---------------------------------------------------------------------------
# Helpers — independent of the ObsHandle so they can be unit-tested.
# ---------------------------------------------------------------------------

# Excluded by convention — these are HDF5-internal, not author obs.
_PSEUDO_COLUMNS = frozenset({"_index"})

# Default chunk for non-categorical columns when h5py doesn't expose chunks.
_DEFAULT_STREAM_CHUNK = 16_384


def _enc(node) -> str | None:
    e = node.attrs.get("encoding-type") if hasattr(node, "attrs") else None
    return e.decode() if isinstance(e, bytes) else e


def _is_nullable(node) -> bool:
    # AnnData >=0.13 stores string/nullable columns (and the index /
    # observation_joinid) as a group {values, mask} with a "nullable-*-array"
    # encoding rather than a plain dataset.
    return (
        isinstance(node, h5py.Group)
        and str(_enc(node) or "").startswith("nullable")
        and "values" in node
    )


def _decode_bytes_array(data) -> np.ndarray:
    out = np.empty(len(data), dtype=object)
    for i, v in enumerate(data):
        out[i] = v.decode(errors="replace") if isinstance(v, bytes) else v
    return out


def _read_nullable_full(group) -> np.ndarray:
    out = _decode_bytes_array(group["values"][:])
    if "mask" in group:
        out[np.asarray(group["mask"][:], dtype=bool)] = None
    return out


def _describe(node) -> ColumnDescriptor:
    if isinstance(node, h5py.Group):
        if "categories" in node and "codes" in node:
            try:
                n_cats = int(node["categories"].shape[0])
                return ColumnDescriptor(
                    kind=ColumnKind.categorical,
                    dtype=str(node["codes"].dtype),
                    n_unique=n_cats,
                    n_unique_estimated=False,
                    n_categories=n_cats,
                    shape=list(node["codes"].shape),
                    encoding="anndata-categorical",
                )
            except Exception:
                return ColumnDescriptor(
                    kind=ColumnKind.categorical,
                    dtype="?",
                    n_unique=None,
                    n_categories=None,
                )
        if _is_nullable(node):
            values = node["values"]
            return ColumnDescriptor(
                kind=ColumnKind.array,
                dtype=str(values.dtype),
                shape=list(values.shape),
                n_unique=None,
                encoding=_enc(node),
            )
        return ColumnDescriptor(kind=ColumnKind.group, dtype="?", n_unique=None)
    try:
        return ColumnDescriptor(
            kind=ColumnKind.array,
            dtype=str(node.dtype),
            shape=list(node.shape),
            n_unique=None,  # populated by the caller if requested
        )
    except Exception:
        return ColumnDescriptor(kind=ColumnKind.array, dtype="?", n_unique=None)


def _head_sample(node, n: int = 20):
    if isinstance(node, h5py.Group) and "categories" in node:
        try:
            codes = node["codes"][:n]
            cats = node["categories"][:]
            return [
                cats[c].decode() if isinstance(cats[c], bytes) else str(cats[c])
                for c in codes
                if 0 <= c < len(cats)
            ]
        except Exception as e:
            return f"ERR: {e}"
    if _is_nullable(node):
        try:
            vals = _decode_bytes_array(node["values"][:n]).tolist()
            if "mask" in node:
                mask = np.asarray(node["mask"][:n], dtype=bool).tolist()
                vals = [None if m else v for v, m in zip(vals, mask, strict=False)]
            return vals
        except Exception as e:
            return f"ERR: {e}"
    try:
        head = node[:n]
        out = []
        for v in head:
            if isinstance(v, bytes):
                out.append(v.decode(errors="replace"))
            else:
                try:
                    out.append(v.item())
                except Exception:
                    out.append(str(v))
        return out
    except Exception as e:
        return f"ERR: {e}"


def _decode_array_full(node: h5py.Dataset) -> np.ndarray:
    data = node[:]
    if data.dtype.kind in ("S", "O"):
        out = np.empty(len(data), dtype=object)
        for i, v in enumerate(data):
            out[i] = v.decode(errors="replace") if isinstance(v, bytes) else v
        return out
    return data


def _decode_categorical_full(group: h5py.Group) -> np.ndarray:
    codes = group["codes"][:]
    cats = group["categories"][:]
    decoded = np.array(
        [c.decode(errors="replace") if isinstance(c, bytes) else str(c) for c in cats],
        dtype=object,
    )
    out = np.empty(len(codes), dtype=object)
    valid = (codes >= 0) & (codes < len(decoded))
    out[valid] = decoded[codes[valid]]
    out[~valid] = None
    return out


def _iter_chunks(node, chunk_size: int = _DEFAULT_STREAM_CHUNK) -> Iterator[np.ndarray]:
    """Stream a column as decoded ndarrays.

    For categoricals, the categories table is decoded once and indexed per
    chunk so memory stays bounded.
    """
    if isinstance(node, h5py.Group) and "categories" in node:
        cats = node["categories"][:]
        decoded_cats = np.array(
            [c.decode(errors="replace") if isinstance(c, bytes) else str(c) for c in cats],
            dtype=object,
        )
        n = node["codes"].shape[0]
        for start in range(0, n, chunk_size):
            stop = min(start + chunk_size, n)
            codes = node["codes"][start:stop]
            out = np.empty(stop - start, dtype=object)
            valid = (codes >= 0) & (codes < len(decoded_cats))
            out[valid] = decoded_cats[codes[valid]]
            out[~valid] = None
            yield out
        return

    if _is_nullable(node):
        values = node["values"]
        mask = node["mask"] if "mask" in node else None
        n = values.shape[0]
        for start in range(0, n, chunk_size):
            stop = min(start + chunk_size, n)
            out = _decode_bytes_array(values[start:stop])
            if mask is not None:
                out[np.asarray(mask[start:stop], dtype=bool)] = None
            yield out
        return

    # Plain dataset.
    n = node.shape[0]
    is_bytes_like = node.dtype.kind in ("S", "O")
    for start in range(0, n, chunk_size):
        stop = min(start + chunk_size, n)
        chunk = node[start:stop]
        if is_bytes_like:
            out = np.empty(stop - start, dtype=object)
            for i, v in enumerate(chunk):
                out[i] = v.decode(errors="replace") if isinstance(v, bytes) else v
            yield out
        else:
            yield np.asarray(chunk)


# ---------------------------------------------------------------------------
# ObsHandle / ObsReader
# ---------------------------------------------------------------------------


class _H5adHandle:
    """ObsHandle for an open h5ad file."""

    def __init__(self, fs_file, h5: h5py.File) -> None:
        self._fs_file = fs_file
        self._h5 = h5
        if "obs" not in h5:
            raise ValueError("no /obs group in source")
        self._obs = h5["obs"]

    def _len(self, node) -> int:
        if isinstance(node, h5py.Group) and "codes" in node:
            return int(node["codes"].shape[0])
        if _is_nullable(node):
            return int(node["values"].shape[0])
        return int(node.shape[0])

    def n_cells(self) -> int:
        if "observation_joinid" in self._obs:
            return self._len(self._obs["observation_joinid"])
        # Fall back: first column's length.
        for k in self._obs.keys():
            try:
                return self._len(self._obs[k])
            except Exception:
                continue
        return 0

    def list_columns(self) -> list[str]:
        return [k for k in self._obs.keys() if k not in _PSEUDO_COLUMNS]

    def describe(self, col: str) -> ColumnDescriptor:
        return _describe(self._obs[col])

    def head_sample(self, col: str, n: int = 20):
        return _head_sample(self._obs[col], n=n)

    def iter_chunks(self, col: str):
        yield from _iter_chunks(self._obs[col])

    def pull_full(self, col: str) -> np.ndarray:
        node = self._obs[col]
        if isinstance(node, h5py.Group) and "categories" in node:
            return _decode_categorical_full(node)
        if _is_nullable(node):
            return _read_nullable_full(node)
        return _decode_array_full(node)

    def joinids(self) -> np.ndarray:
        node = self._obs["observation_joinid"]
        if _is_nullable(node):
            return _read_nullable_full(node)
        return _decode_array_full(node)

    def close(self) -> None:
        try:
            self._h5.close()
        finally:
            try:
                self._fs_file.close()
            except Exception:
                pass


class H5adReader:
    """Open an .h5ad file via fsspec and expose its obs."""

    SUPPORTED_SCHEMES: tuple[str, ...] = ("http", "https", "file", "s3", "")
    SUPPORTED_SUFFIXES: tuple[str, ...] = (".h5ad",)
    FORMAT: str = "h5ad"

    def open(self, url: str) -> _H5adHandle:
        fs, path = fsspec.core.url_to_fs(url)
        f = fs.open(path, "rb", block_size=64 * 1024)
        try:
            h = h5py.File(f, "r")
        except Exception:
            f.close()
            raise
        return _H5adHandle(f, h)
