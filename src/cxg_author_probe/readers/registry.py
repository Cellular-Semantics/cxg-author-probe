"""URL → ObsReader dispatch.

Built-in readers (h5ad, and zarr/tiledb stubs) are registered statically.
Additional readers installed by other packages are discovered lazily via the
``cxg_author_probe.readers`` entry-point group, so the CLI and any plugin see
them without an explicit in-process ``register_reader`` call. A distribution
exposes a reader with, in its ``pyproject.toml``::

    [project.entry-points."cxg_author_probe.readers"]
    anndata_zarr = "my_pkg.readers.zarr:AnndataZarrReader"
"""
from __future__ import annotations

import warnings
from importlib.metadata import entry_points
from urllib.parse import urlparse

from .base import ObsHandle, ObsReader
from .errors import NoReaderError
from .h5ad import H5adReader
from .tiledbsoma import TileDBSomaReader
from .zarr import ZarrReader

#: Entry-point group other packages use to advertise an ``ObsReader``.
READER_ENTRY_POINT_GROUP = "cxg_author_probe.readers"

# Order matters — first match wins. Suffix matches are checked before scheme,
# so a `.h5ad` URL is dispatched to H5adReader even when served over `s3://`.
# Discovered (entry-point) readers are prepended, so an external real reader
# overrides a built-in stub of the same format.
_REGISTRY: list[type] = [H5adReader, ZarrReader, TileDBSomaReader]

# Guards against re-running discovery and against double-registering the same
# class (from repeated discovery or a manual register_reader of a discovered
# reader).
_discovered: bool = False
_registered: set[type] = set(_REGISTRY)


def register_reader(reader_cls: type) -> None:
    """Add a custom reader to the front of the dispatch list.

    Idempotent: registering an already-known class is a no-op (it keeps its
    existing position rather than being prepended again).
    """
    if reader_cls in _registered:
        return
    _REGISTRY.insert(0, reader_cls)
    _registered.add(reader_cls)


def _discover_entry_point_readers() -> None:
    """Register every reader advertised under ``READER_ENTRY_POINT_GROUP``.

    A reader whose entry point fails to import is skipped with a
    ``RuntimeWarning`` rather than breaking dispatch for all other readers.
    """
    for ep in entry_points(group=READER_ENTRY_POINT_GROUP):
        try:
            reader_cls = ep.load()
        except Exception as exc:  # noqa: BLE001 — one bad plugin must not break dispatch
            warnings.warn(
                f"reader entry point {ep.name!r} "
                f"({ep.value}) failed to load: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        register_reader(reader_cls)


def _ensure_discovered() -> None:
    global _discovered
    if _discovered:
        return
    _discovered = True  # set first: a failing plugin must not force re-discovery
    _discover_entry_point_readers()


def refresh_readers() -> None:
    """Force a re-scan of entry-point readers (for tests / dynamic installs)."""
    global _discovered
    _discovered = False
    _ensure_discovered()


def _suffix_match(reader_cls: type, url: str) -> bool:
    suffixes: tuple[str, ...] = getattr(reader_cls, "SUPPORTED_SUFFIXES", ())
    lower = url.lower()
    return any(
        lower.endswith(suf) or lower.rstrip("/").endswith(suf.rstrip("/")) for suf in suffixes
    )


def _scheme_match(reader_cls: type, url: str) -> bool:
    schemes: tuple[str, ...] = getattr(reader_cls, "SUPPORTED_SCHEMES", ())
    return urlparse(url).scheme in schemes


def pick_reader(url: str) -> type:
    """Select a reader for ``url``.

    A **suffix** match (most specific, e.g. ``.zarr``) beats a **scheme** match
    across all readers — so a reader with a catch-all scheme (e.g. h5ad's ``""``
    for bare local paths) never shadows a more specific reader later in the list.
    Within each pass, registration order wins (discovered/manual readers are
    prepended, so they take precedence over built-ins).
    """
    _ensure_discovered()
    for reader_cls in _REGISTRY:
        if _suffix_match(reader_cls, url):
            return reader_cls
    for reader_cls in _REGISTRY:
        if _scheme_match(reader_cls, url):
            return reader_cls
    raise NoReaderError(url, tried=tuple(r.__name__ for r in _REGISTRY))


def open_obs(url: str) -> ObsHandle:
    """Open an obs view at `url`, auto-selecting the reader."""
    cls = pick_reader(url)
    reader: ObsReader = cls()
    return reader.open(url)
