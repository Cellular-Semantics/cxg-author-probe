"""``probe._format_from_reader``: reader FORMAT attr → Format enum, with fallback."""
from __future__ import annotations

from cxg_author_probe.models import Format
from cxg_author_probe.probe import _format_from_reader


class _NoFormat:
    pass


class _UnknownFormat:
    FORMAT = "totally-unknown-format"


class _KnownFormat:
    FORMAT = "anndata-zarr"


def test_known_format_maps_to_enum():
    assert _format_from_reader(_KnownFormat) is Format.anndata_zarr


def test_missing_format_falls_back_to_h5ad():
    # A reader without a FORMAT attribute must not crash the probe.
    assert _format_from_reader(_NoFormat) is Format.h5ad


def test_unknown_format_falls_back_to_h5ad():
    assert _format_from_reader(_UnknownFormat) is Format.h5ad
