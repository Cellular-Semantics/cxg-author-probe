"""Reader-layer exceptions.

Kept in their own module so both the registry (dispatch) and the verification
gate can raise them without importing each other.
"""

from __future__ import annotations


class NoReaderError(ValueError):
    """No registered reader can handle a URL.

    Subclasses ``ValueError`` for backward compatibility (callers that already
    ``except ValueError`` around ``open_obs``/``pick_reader`` keep working). It
    is the designated trigger point for the agentic reader-improviser: catch
    ``NoReaderError`` specifically to fall back to improvisation, while other
    ``ValueError``\\s stay hard failures.
    """

    def __init__(self, url: str, *, tried: tuple[str, ...] = ()) -> None:
        self.url = url
        self.tried = tried
        tried_str = f" (tried: {', '.join(tried)})" if tried else ""
        super().__init__(f"No registered reader can handle URL: {url!r}{tried_str}")


class ObsHandleVerificationError(ValueError):
    """An ``ObsHandle`` failed one or more contract invariants.

    Raised by :func:`cxg_author_probe.readers.verify.verify_obs_handle`. Carries
    the list of problem descriptions so a caller (e.g. the improviser's trust
    gate) can inspect or retry.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        joined = "\n  - ".join(problems)
        super().__init__(f"ObsHandle failed verification:\n  - {joined}")
