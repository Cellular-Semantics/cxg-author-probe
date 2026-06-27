"""URL → ObsReader dispatch.

The h5ad reader is the only one implemented today. Zarr and TileDB-SOMA
readers are registered but raise NotImplementedError when opened.
"""
from __future__ import annotations

from urllib.parse import urlparse

from .base import ObsHandle, ObsReader
from .h5ad import H5adReader
from .tiledbsoma import TileDBSomaReader
from .zarr import ZarrReader

# Order matters — first match wins. Suffix matches are checked before scheme,
# so a `.h5ad` URL is dispatched to H5adReader even when served over `s3://`.
_REGISTRY: list[type] = [H5adReader, ZarrReader, TileDBSomaReader]


def register_reader(reader_cls: type) -> None:
    """Add a custom reader to the front of the dispatch list."""
    _REGISTRY.insert(0, reader_cls)


def _matches(reader_cls: type, url: str) -> bool:
    suffixes: tuple[str, ...] = getattr(reader_cls, "SUPPORTED_SUFFIXES", ())
    schemes: tuple[str, ...] = getattr(reader_cls, "SUPPORTED_SCHEMES", ())

    # Suffix match wins (most specific)
    lower = url.lower()
    if any(lower.endswith(suf) or lower.rstrip("/").endswith(suf.rstrip("/")) for suf in suffixes):
        return True

    # Scheme-only fallback
    scheme = urlparse(url).scheme
    if scheme in schemes:
        return True

    return False


def pick_reader(url: str) -> type:
    for reader_cls in _REGISTRY:
        if _matches(reader_cls, url):
            return reader_cls
    raise ValueError(f"No registered reader can handle URL: {url!r}")


def open_obs(url: str) -> ObsHandle:
    """Open an obs view at `url`, auto-selecting the reader."""
    cls = pick_reader(url)
    reader: ObsReader = cls()
    return reader.open(url)
