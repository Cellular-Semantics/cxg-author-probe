"""The no-match seam: pick_reader raises a typed, back-compatible error."""

from __future__ import annotations

import pytest

from cxg_author_probe.readers import NoReaderError
from cxg_author_probe.readers.registry import pick_reader


def test_no_match_raises_no_reader_error():
    with pytest.raises(NoReaderError) as exc:
        pick_reader("weird://host/thing.unknownformat")
    # carries the URL and the readers it tried (for the improviser trigger)
    assert exc.value.url == "weird://host/thing.unknownformat"
    assert exc.value.tried  # non-empty


def test_no_reader_error_is_value_error():
    # Back-compat: existing `except ValueError` callers keep catching it.
    assert issubclass(NoReaderError, ValueError)
    with pytest.raises(ValueError):
        pick_reader("weird://host/thing.unknownformat")
