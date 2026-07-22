#!/usr/bin/env python3
"""Plugin PostToolUse hook: validate cxg-author-probe JSON artifacts on write.

Fires on every ``Write``/``Edit`` in the host session (that is how plugin hooks
are matched), so it must be a cheap no-op for anything that is not one of *our*
artifacts. It:

1. Reads the just-written file from disk (PostToolUse runs *after* the write, so
   ``file_path`` is materialised — this handles Write and Edit uniformly).
2. Exits 0 immediately unless the file is JSON carrying a top-level
   ``schema_version`` this package recognises (``picks-v1`` is the LLM-written
   one; ``probe-v1``/``pulled-v1``/``cas-v1`` are covered for free).
3. Delegates the actual check to the installed CLI — ``cxg-author validate`` —
   so the hook always matches the user's installed schema/model version and
   stays a thin wrapper (no duplicated validation logic).

Exit codes:
    0 — valid, or not one of our artifacts, or the CLI is unavailable
    2 — recognised artifact that failed validation (stderr → model self-corrects)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

# schema_version values that `cxg-author validate` knows how to check.
KNOWN_SCHEMAS = {"probe-v1", "picks-v1", "pulled-v1", "cas-v1"}


def main() -> int:
    # Hook contract: a JSON object on stdin. Malformed → do nothing.
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return 0

    file_path = hook_input.get("tool_input", {}).get("file_path", "")
    if not file_path or not file_path.endswith(".json"):
        return 0

    # Read from disk: the write already happened, and this covers Edit (which
    # carries no full `content` in tool_input) as well as Write.
    try:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        # Not readable JSON → not one of ours; stay silent.
        return 0

    if not isinstance(data, dict) or data.get("schema_version") not in KNOWN_SCHEMAS:
        return 0

    cli = shutil.which("cxg-author")
    if cli is None:
        # The CLI is a precondition for the plugin at all; if it is missing the
        # skill would already have failed. Don't block unrelated work over an
        # environment gap — warn quietly and pass.
        print(
            f"cxg-author-probe: cannot validate {file_path} — `cxg-author` CLI not on PATH.",
            file=sys.stderr,
        )
        return 0

    proc = subprocess.run(
        [cli, "validate", file_path],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sv = data.get("schema_version")
        print(
            f"cxg-author-probe: {sv} artifact failed validation: {file_path}",
            file=sys.stderr,
        )
        detail = (proc.stderr or proc.stdout).strip()
        if detail:
            print(detail, file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
