"""Full-column pulls for picked obs columns."""
from __future__ import annotations

import sys
from typing import Iterable

import numpy as np

from .readers import open_obs
from .readers.h5ad import byte_counter


def pull_full_column(
    url: str,
    column_names: Iterable[str],
    *,
    stats: dict[str, int] | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray | None]]:
    """Pull observation_joinid and one-or-more full obs columns.

    Returns
    -------
    (joinids, columns) — joinids is ndarray of decoded strings;
    columns is a dict mapping each requested column to its full ndarray
    (or None if the column is missing or unreadable).
    """
    if stats is None:
        stats = {}

    cols: dict[str, np.ndarray | None] = {}
    with byte_counter(stats):
        handle = open_obs(url)
        try:
            joinids = handle.joinids()
            for col in column_names:
                try:
                    if col not in handle.list_columns():
                        cols[col] = None
                        continue
                    cols[col] = handle.pull_full(col)
                except Exception as e:
                    sys.stderr.write(f"[pull] {col}: {e}\n")
                    cols[col] = None
        finally:
            handle.close()

    return joinids, cols
