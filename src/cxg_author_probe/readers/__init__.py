"""Format-specific obs readers.

Each reader implements the `ObsReader` Protocol (from `.base`) and returns an
`ObsHandle` that exposes lazy column access. `registry.open_obs(url)`
dispatches to the right reader based on the URL.
"""
from .base import ObsHandle, ObsReader
from .registry import open_obs, register_reader

__all__ = ["ObsHandle", "ObsReader", "open_obs", "register_reader"]
