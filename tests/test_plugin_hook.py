"""Plugin PostToolUse write-hook + the `cxg-author validate` it wraps.

Two layers:
- The CLI (`validate`) emits clean field errors + exit 2 on a bad artifact
  (so the hook has a usable correction signal), OK + exit 0 on a good one.
- The hook script no-ops on anything that is not a recognised, schema-versioned
  artifact, and relays the CLI's verdict otherwise.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from cxg_author_probe.cli import app

runner = CliRunner()

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "plugin" / "cxg-author-probe" / "hooks" / "validate_artifact.py"

GOOD_PICKS = {
    "schema_version": "picks-v1",
    "dataset_id": "ds1",
    "picks": ["author_cell_type"],
}
BAD_PICKS = {  # `picks` must be an array
    "schema_version": "picks-v1",
    "dataset_id": "ds1",
    "picks": "author_cell_type",
}


# --- CLI: cxg-author validate -------------------------------------------------


def test_validate_ok(tmp_path: Path):
    p = tmp_path / "picks.json"
    p.write_text(json.dumps(GOOD_PICKS))
    res = runner.invoke(app, ["validate", str(p)])
    assert res.exit_code == 0, res.output
    assert "OK" in res.output


def test_validate_reports_clean_errors(tmp_path: Path):
    p = tmp_path / "picks.json"
    p.write_text(json.dumps(BAD_PICKS))
    res = runner.invoke(app, ["validate", str(p)])
    assert res.exit_code == 2
    # Concise field message, not a traceback.
    assert "picks" in res.output
    assert "Traceback" not in res.output


def test_validate_unknown_schema_version(tmp_path: Path):
    p = tmp_path / "thing.json"
    p.write_text(json.dumps({"schema_version": "made-up-v9"}))
    res = runner.invoke(app, ["validate", str(p)])
    assert res.exit_code == 2
    assert "unknown schema_version" in res.output


# --- The plugin hook script ---------------------------------------------------


def _run_hook(file_path: str) -> subprocess.CompletedProcess[str]:
    """Invoke the hook as Claude Code would: JSON on stdin, cxg-author on PATH."""
    env = {
        **os.environ,
        # Ensure the `cxg-author` console script (installed alongside this
        # interpreter) resolves inside the hook's subprocess.
        "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""),
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {"file_path": file_path}}),
        capture_output=True,
        text=True,
        env=env,
    )


def test_hook_passes_valid_artifact(tmp_path: Path):
    p = tmp_path / "picks.json"
    p.write_text(json.dumps(GOOD_PICKS))
    res = _run_hook(str(p))
    assert res.returncode == 0, res.stderr


def test_hook_blocks_invalid_artifact(tmp_path: Path):
    p = tmp_path / "picks.json"
    p.write_text(json.dumps(BAD_PICKS))
    res = _run_hook(str(p))
    assert res.returncode == 2
    assert "picks-v1 artifact failed validation" in res.stderr
    assert "picks" in res.stderr


def test_hook_noops_on_json_without_schema_version(tmp_path: Path):
    p = tmp_path / "other.json"
    p.write_text(json.dumps({"foo": "bar"}))
    res = _run_hook(str(p))
    assert res.returncode == 0
    assert res.stderr == ""


def test_hook_noops_on_non_json_file(tmp_path: Path):
    p = tmp_path / "notes.txt"
    p.write_text("just some notes")
    res = _run_hook(str(p))
    assert res.returncode == 0


def test_hook_noops_on_missing_file(tmp_path: Path):
    res = _run_hook(str(tmp_path / "does_not_exist.json"))
    assert res.returncode == 0
