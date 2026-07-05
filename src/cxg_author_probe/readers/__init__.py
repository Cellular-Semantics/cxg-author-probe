"""Format-specific obs readers.

Each reader implements the `ObsReader` Protocol (from `.base`) and returns an
`ObsHandle` that exposes lazy column access. `registry.open_obs(url)`
dispatches to the right reader based on the URL.
"""
from .base import ObsHandle, ObsReader
from .errors import NoReaderError, ObsHandleVerificationError
from .registry import open_obs, refresh_readers, register_reader
from .verify import check_obs_handle, verify_obs_handle

__all__ = [
    "ObsHandle",
    "ObsReader",
    "NoReaderError",
    "ObsHandleVerificationError",
    "open_obs",
    "refresh_readers",
    "register_reader",
    "check_obs_handle",
    "verify_obs_handle",
]
