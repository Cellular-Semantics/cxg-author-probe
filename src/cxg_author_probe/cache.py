"""On-disk cache for probes / picks / pulled artefacts.

Default layout under `.cache/cxg-author-probe/`:
    probes/<dataset_id>.json   — ProbeV1
    picks/<dataset_id>.json    — PicksV1
    pulled/<dataset_id>.json   — PulledV1 sidecar (data in <dataset_id>.parquet)
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

_DEFAULT_ROOT = Path(".cache") / "cxg-author-probe"


def root() -> Path:
    override = os.environ.get("CXG_AUTHOR_PROBE_CACHE")
    return Path(override) if override else _DEFAULT_ROOT


def cache_path(stage: str, dataset_id: str, suffix: str = ".json") -> Path:
    """Stage is 'probes', 'picks', or 'pulled'."""
    p = root() / stage
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{dataset_id}{suffix}"


def load_cache(stage: str, dataset_id: str) -> str | None:
    """Return file contents as a string, or None if absent."""
    p = cache_path(stage, dataset_id)
    if not p.exists():
        return None
    try:
        return p.read_text()
    except Exception:
        return None


def save_cache(stage: str, dataset_id: str, text: str) -> Path:
    p = cache_path(stage, dataset_id)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(p)  # atomic on POSIX
    return p


def schema_hash(schema_keys: Iterable[str]) -> str:
    """Stable hash of an obs column-name set — used to detect schema drift."""
    joined = "\n".join(sorted(schema_keys))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def is_fresh(
    cached_probe_hash: str,
    current_keys: Iterable[str],
    cached_census_version: str | None = None,
    current_census_version: str | None = None,
) -> bool:
    if cached_probe_hash != schema_hash(current_keys):
        return False
    if current_census_version is not None and cached_census_version != current_census_version:
        return False
    return True
