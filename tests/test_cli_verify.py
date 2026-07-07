"""`cxg-author verify` — the read-a-source acceptance gate as a CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cxg_author_probe.cli import app

runner = CliRunner()


def test_verify_ok_on_real_h5ad(synthetic_h5ad: Path):
    res = runner.invoke(app, ["verify", f"file://{synthetic_h5ad}"])
    assert res.exit_code == 0, res.output
    assert "OK" in res.output
    assert "obs columns" in res.output


def test_verify_no_reader(tmp_path: Path):
    # A foreign scheme matches no reader → exit 1.
    res = runner.invoke(app, ["verify", "weird://host/thing"])
    assert res.exit_code == 1
    assert "NO READER" in res.output


def test_verify_open_failure(tmp_path: Path):
    # A .h5ad path that doesn't exist → open fails → exit 1 (not a crash).
    missing = tmp_path / "nope.h5ad"
    res = runner.invoke(app, ["verify", str(missing)])
    assert res.exit_code == 1
    assert "OPEN FAILED" in res.output or "FAILED" in res.output
