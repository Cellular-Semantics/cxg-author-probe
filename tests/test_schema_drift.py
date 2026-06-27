"""Guard against schema/model drift.

Re-runs scripts/generate_models.py into a tempdir and diffs against the
committed _generated.py. Fails if they disagree — forces every schema edit
to come with a `make models` regen.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_generated_models_are_in_sync(tmp_path: Path):
    committed = ROOT / "src" / "cxg_author_probe" / "models" / "_generated.py"
    # Stage a parallel layout under tmp_path
    work = tmp_path / "work"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
        ".venv", ".git", "__pycache__", "*.egg-info", ".pytest_cache", "dist", "build",
    ))
    target = work / "src" / "cxg_author_probe" / "models" / "_generated.py"

    res = subprocess.run(
        [sys.executable, str(work / "scripts" / "generate_models.py")],
        capture_output=True, text=True, cwd=work,
    )
    if res.returncode != 0:
        raise AssertionError(
            "Codegen failed:\nSTDOUT:\n" + res.stdout + "\nSTDERR:\n" + res.stderr
        )

    assert target.exists(), "codegen did not produce _generated.py"
    a = committed.read_text()
    b = target.read_text()
    assert a == b, (
        "Committed src/cxg_author_probe/models/_generated.py is out of sync "
        "with schemas/. Run `make models` and commit the regenerated file."
    )
