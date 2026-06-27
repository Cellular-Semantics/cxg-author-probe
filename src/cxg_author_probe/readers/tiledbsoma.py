"""TileDB-SOMA reader — stub.

Tracking: https://github.com/Cellular-Semantics/cxg-author-probe/issues (TBD)
"""
from __future__ import annotations


class TileDBSomaReader:
    SUPPORTED_SCHEMES: tuple[str, ...] = ("tiledb", "s3", "file")
    SUPPORTED_SUFFIXES: tuple[str, ...] = (".tdb", ".soma")
    FORMAT: str = "tiledbsoma"

    def open(self, url: str):
        raise NotImplementedError(
            "TileDB-SOMA support is planned but not yet implemented. "
            "Track at https://github.com/Cellular-Semantics/cxg-author-probe/issues."
        )
