"""anndata-zarr reader — stub.

Tracking: https://github.com/Cellular-Semantics/cxg-author-probe/issues (TBD)

The architecture is in place. Implementation requires `zarr`. Same
ObsHandle interface, same downstream code.
"""
from __future__ import annotations


class ZarrReader:
    SUPPORTED_SCHEMES: tuple[str, ...] = ("http", "https", "file", "s3")
    SUPPORTED_SUFFIXES: tuple[str, ...] = (".zarr", ".zarr/")
    FORMAT: str = "anndata-zarr"

    def open(self, url: str):
        raise NotImplementedError(
            "anndata-zarr support is planned but not yet implemented. "
            "Track at https://github.com/Cellular-Semantics/cxg-author-probe/issues."
        )
