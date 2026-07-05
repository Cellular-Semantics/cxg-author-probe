"""Entry-point reader discovery in ``readers.registry``.

Discovery is exercised with a fake ``entry_points`` so the test is
self-contained (no external distribution needs to be installed). Each test
restores the registry globals it mutates.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from cxg_author_probe.readers import registry
from cxg_author_probe.readers.h5ad import H5adReader


class _DummyReader:
    """Minimal ObsReader for a made-up ``.dummy`` format."""

    SUPPORTED_SCHEMES: tuple[str, ...] = ()
    SUPPORTED_SUFFIXES: tuple[str, ...] = (".dummy",)
    FORMAT: str = "dummy"

    def open(self, url: str):  # pragma: no cover - never opened in these tests
        raise NotImplementedError


class _FakeEntryPoint:
    def __init__(self, name: str, obj):
        self.name = name
        self.value = f"tests.fake:{name}"
        self._obj = obj

    def load(self):
        if isinstance(self._obj, Exception):
            raise self._obj
        return self._obj


@pytest.fixture
def restore_registry() -> Iterator[None]:
    """Snapshot and restore the module-global registry state."""
    saved_list = list(registry._REGISTRY)
    saved_registered = set(registry._registered)
    saved_discovered = registry._discovered
    try:
        yield
    finally:
        registry._REGISTRY[:] = saved_list
        registry._registered.clear()
        registry._registered.update(saved_registered)
        registry._discovered = saved_discovered


def _patch_entry_points(monkeypatch, eps):
    def fake_entry_points(*, group: str):
        assert group == registry.READER_ENTRY_POINT_GROUP
        return list(eps)

    monkeypatch.setattr(registry, "entry_points", fake_entry_points)


def test_discovered_reader_wins_dispatch(monkeypatch, restore_registry):
    _patch_entry_points(monkeypatch, [_FakeEntryPoint("dummy", _DummyReader)])

    registry.refresh_readers()

    assert registry.pick_reader("s3://bucket/x.dummy") is _DummyReader
    # Prepended: it precedes the built-in readers.
    assert registry._REGISTRY[0] is _DummyReader
    # Built-in dispatch is unaffected.
    assert registry.pick_reader("file:///data/x.h5ad") is H5adReader


def test_load_failure_is_skipped_with_warning(monkeypatch, restore_registry):
    _patch_entry_points(
        monkeypatch,
        [_FakeEntryPoint("broken", ImportError("no optional dep"))],
    )

    with pytest.warns(RuntimeWarning, match="broken"):
        registry.refresh_readers()

    # Registry still usable despite the bad plugin.
    assert registry.pick_reader("file:///data/x.h5ad") is H5adReader
    assert _DummyReader not in registry._REGISTRY


def test_discovery_is_idempotent(monkeypatch, restore_registry):
    _patch_entry_points(monkeypatch, [_FakeEntryPoint("dummy", _DummyReader)])

    registry.refresh_readers()
    registry.refresh_readers()

    assert registry._REGISTRY.count(_DummyReader) == 1
