"""Verify an ``ObsHandle`` against the reader contract invariants.

A reader is only trustworthy if the handle it returns behaves. This gate makes
that testable: it validates *deterministic* readers (catches decoding/length
bugs) and is the precondition for trusting an *improvised* reader before using
its output.

Style mirrors atlas-reporter's ``report_checker``: a pure checker returning a
list of problem strings (empty == pass), plus a raising wrapper.
"""

from __future__ import annotations

from cxg_author_probe.models import ColumnDescriptor, ColumnKind

from .errors import ObsHandleVerificationError
from .h5ad import _PSEUDO_COLUMNS  # type: ignore[attr-defined]

# JSON-serialisable primitives that a decoded obs value may be. Notably excludes
# ``bytes`` (the classic "reader forgot to decode" bug).
_PRIMITIVES = (bool, int, float, str, type(None))


def _bad_values(values: list, ctx: str) -> list[str]:
    problems: list[str] = []
    for v in values:
        if isinstance(v, bytes):
            problems.append(f"{ctx}: undecoded bytes value {v!r} (expected a primitive)")
            break
        if not isinstance(v, _PRIMITIVES):
            problems.append(
                f"{ctx}: non-primitive value {v!r} of type {type(v).__name__} "
                "(expected int/float/str/bool/None)"
            )
            break
    return problems


def check_obs_handle(handle, *, sample_n: int = 20, deep: bool = False) -> list[str]:
    """Return a list of contract violations for ``handle`` (empty == pass).

    Default checks are bounded-cost (``n_cells``, ``joinids``, and one
    ``describe`` + ``head_sample`` per column). ``deep=True`` additionally
    materialises every column (``pull_full`` + ``iter_chunks``) to check lengths
    — costly, for tests / small stores / an improviser's trust gate.
    """
    problems: list[str] = []

    # 1. n_cells
    try:
        n_cells = handle.n_cells()
    except Exception as e:  # noqa: BLE001 — surface as a problem, don't crash the gate
        return [f"n_cells() raised {type(e).__name__}: {e}"]
    if not isinstance(n_cells, int) or isinstance(n_cells, bool) or n_cells < 0:
        problems.append(f"n_cells() returned {n_cells!r}; expected a non-negative int")
        n_cells = max(0, n_cells) if isinstance(n_cells, int) else 0

    # 2. joinids
    try:
        joinids = handle.joinids()
        jlist = list(joinids)
        if len(jlist) != n_cells:
            problems.append(f"joinids() length {len(jlist)} != n_cells {n_cells}")
        problems += _bad_values(jlist[:sample_n], "joinids()")
    except Exception as e:  # noqa: BLE001
        problems.append(f"joinids() raised {type(e).__name__}: {e}")

    # 3. list_columns
    try:
        cols = handle.list_columns()
    except Exception as e:  # noqa: BLE001
        return problems + [f"list_columns() raised {type(e).__name__}: {e}"]
    if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
        return problems + [f"list_columns() returned {cols!r}; expected list[str]"]
    leaked = sorted(set(cols) & _PSEUDO_COLUMNS)
    if leaked:
        problems.append(f"list_columns() leaks pseudo-columns: {leaked}")

    # 4. per-column describe + head_sample
    expected_head = min(sample_n, n_cells)
    for col in cols:
        try:
            desc = handle.describe(col)
        except Exception as e:  # noqa: BLE001
            problems.append(f"describe({col!r}) raised {type(e).__name__}: {e}")
        else:
            if not isinstance(desc, ColumnDescriptor):
                problems.append(
                    f"describe({col!r}) returned {type(desc).__name__}; expected ColumnDescriptor"
                )
            elif not isinstance(desc.kind, ColumnKind):
                problems.append(f"describe({col!r}).kind is {desc.kind!r}; not a ColumnKind")

        try:
            head = handle.head_sample(col, sample_n)
        except Exception as e:  # noqa: BLE001
            problems.append(f"head_sample({col!r}) raised {type(e).__name__}: {e}")
            continue
        if not isinstance(head, list):
            problems.append(f"head_sample({col!r}) returned {type(head).__name__}; expected list")
            continue
        if len(head) != expected_head:
            problems.append(f"head_sample({col!r}) length {len(head)} != expected {expected_head}")
        problems += _bad_values(head, f"head_sample({col!r})")

    # 5. deep: full-column length consistency
    if deep:
        for col in cols:
            try:
                full = handle.pull_full(col)
                if len(full) != n_cells:
                    problems.append(f"pull_full({col!r}) length {len(full)} != n_cells {n_cells}")
                streamed = sum(len(chunk) for chunk in handle.iter_chunks(col))
                if streamed != n_cells:
                    problems.append(f"iter_chunks({col!r}) total {streamed} != n_cells {n_cells}")
            except Exception as e:  # noqa: BLE001
                problems.append(f"deep check on {col!r} raised {type(e).__name__}: {e}")

    return problems


def verify_obs_handle(handle, *, sample_n: int = 20, deep: bool = False) -> None:
    """Raise :class:`ObsHandleVerificationError` if ``handle`` violates the contract."""
    problems = check_obs_handle(handle, sample_n=sample_n, deep=deep)
    if problems:
        raise ObsHandleVerificationError(problems)
