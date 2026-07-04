"""Cheap remote obs probe: schema + 20-sample/col, no expression-matrix touch.

Returns a `ProbeV1` Pydantic model (schema source of truth in
`schemas/probe-v1.schema.json`).
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from ._version import __version__
from .models import ColumnDescriptor, ColumnKind, Format, ProbeMeta, ProbeV1, Source
from .readers.h5ad import _PSEUDO_COLUMNS, byte_counter  # type: ignore[attr-defined]
from .readers.registry import pick_reader


def _exact_unique(values: np.ndarray) -> int | None:
    """Count exact uniques in an ndarray. None if dtype unhelpful."""
    try:
        # Treat NaN/None as a single sentinel — Pydantic doesn't care about
        # exact NaN semantics here.
        return int(len({v for v in values.tolist() if v is not None and v == v}))
    except Exception:
        return None


def _estimate_unique(handle, col: str, sample_n: int = 1000) -> tuple[int | None, bool]:
    """Sample ~sample_n values, return (n_unique, estimated_flag).

    Estimated == True when the column is longer than the sample. For columns
    smaller than the sample, returns the exact count with estimated=False.
    """
    try:
        sample = handle.head_sample(col, n=sample_n)
        if not isinstance(sample, list):
            return None, False
        n = handle.n_cells()
        unique_in_sample = len({v for v in sample if v is not None and v == v})
        return unique_in_sample, n > len(sample)
    except Exception:
        return None, False


def _compute_n_unique(
    handle, col: str, desc: ColumnDescriptor, *, exact: bool
) -> ColumnDescriptor:
    """Populate `n_unique` / `n_unique_estimated` per the strategy:

    - categorical: already set to n_categories (exact).
    - small dtypes (int8, int16, bool, uint8): streamed exact set scan.
    - string / object: head sample → estimate (or exact if --exact-unique).
    - float / large numeric: leave as None.
    """
    if desc.kind == ColumnKind.categorical:
        return desc  # already exact

    dtype_str = (desc.dtype or "").lower()
    # Float dtypes: skip — cardinality is rarely useful and rarely bounded.
    is_float = any(t in dtype_str for t in ("float", "f4", "f8", "<f", ">f"))
    is_complex = "complex" in dtype_str
    # Strings get sampled. Everything else integer/bool gets streamed exact scan.
    string_like = any(t in dtype_str for t in ("object", "str", "<u", "<s", "|s", "|u"))
    integer_like = (not is_float and not is_complex and not string_like)

    if integer_like or exact:
        try:
            seen: set = set()
            for chunk in handle.iter_chunks(col):
                # cast to python-level objects so set() works across dtypes
                for v in chunk.tolist():
                    if v is None:
                        continue
                    if isinstance(v, float) and v != v:  # NaN
                        continue
                    seen.add(v)
                # Bail out if cardinality is exploding and we're past a sane cap.
                if not exact and len(seen) > 10_000:
                    return desc.model_copy(update={"n_unique": None})
            return desc.model_copy(
                update={"n_unique": len(seen), "n_unique_estimated": False}
            )
        except Exception:
            return desc

    if string_like:
        n_unique, estimated = _estimate_unique(handle, col)
        return desc.model_copy(
            update={"n_unique": n_unique, "n_unique_estimated": estimated}
        )

    # Floats / large numerics: skip.
    return desc


def probe(
    url: str,
    *,
    dataset_id: str | None = None,
    sample_n: int = 20,
    exact_unique: bool = False,
) -> ProbeV1:
    """Probe a remote dataset's obs schema + sample.

    Parameters
    ----------
    url : str
        Fully-qualified URL or path. Reader is auto-selected (h5ad implemented;
        zarr / tiledbsoma stubbed).
    dataset_id : str, optional
        Stable identifier. If omitted, derived from the URL stem.
    sample_n : int
        Head-sample size per column. Default 20 (used by the picker prompt).
    exact_unique : bool
        Force a full streamed scan for n_unique on every column, not just
        categoricals. Default False (sampled estimate for strings, skipped
        for floats).
    """
    if dataset_id is None:
        # Derive from URL stem: last path segment, suffix stripped.
        from urllib.parse import urlparse

        path = urlparse(url).path or url
        dataset_id = path.rsplit("/", 1)[-1].split(".")[0]

    stats: dict[str, int] = {}
    with byte_counter(stats):
        t0 = datetime.now(timezone.utc)
        reader_cls = pick_reader(url)
        handle = reader_cls().open(url)
        try:
            n_cells = handle.n_cells()
            columns: dict[str, ColumnDescriptor] = {}
            for col in handle.list_columns():
                if col in _PSEUDO_COLUMNS:
                    continue
                try:
                    desc = handle.describe(col)
                    desc = _compute_n_unique(handle, col, desc, exact=exact_unique)
                    sample = handle.head_sample(col, n=sample_n)
                    if isinstance(sample, list):
                        desc = desc.model_copy(update={"sample": sample[:sample_n]})
                    columns[col] = desc
                except Exception as e:
                    columns[col] = ColumnDescriptor(
                        kind=ColumnKind.unknown,
                        dtype="?",
                        n_unique=None,
                        encoding=f"ERR: {e}",
                    )

            reader_module = reader_cls.__module__
            fmt = _format_from_reader(reader_cls)

            elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
            probe_meta = ProbeMeta(
                probe_bytes=stats["n"],
                probe_gets=stats["calls"],
                probe_time_s=round(elapsed, 3),
                reader=reader_module,
                package_version=__version__,
                probed_at=datetime.now(timezone.utc),
            )
        finally:
            handle.close()

    return ProbeV1(
        schema_version="probe-v1",
        dataset_id=dataset_id,
        source=Source(url=url, format=fmt),
        n_cells=n_cells,
        columns=columns,
        probe_meta=probe_meta,
    )


def _format_from_reader(reader_cls: type) -> Format:
    """Map a reader's ``FORMAT`` attribute onto the ``Format`` enum.

    Reader ``FORMAT`` strings are contracted to match ``Format`` values
    (see ``readers.base.ObsReader``). An unknown / missing value falls back to
    ``h5ad`` rather than failing the probe.
    """
    try:
        return Format(reader_cls.FORMAT)
    except (ValueError, TypeError):
        return Format.h5ad
