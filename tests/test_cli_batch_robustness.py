"""Batch stage commands must not abort on one malformed file.

A single invalid artifact in a globbed input dir should be skipped with a
concise warning (not a raw traceback); valid files still process; the command
exits non-zero so the failure is noticed.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cxg_author_probe.cli import app
from cxg_author_probe.models import PicksV1

runner = CliRunner()


def _make_probe_and_picks(synthetic_h5ad: Path, tmp_path: Path) -> tuple[Path, Path, str]:
    """probe the fixture and write one valid picks file; return (probes, picks, dsid)."""
    probes_dir = tmp_path / "probes"
    res = runner.invoke(app, ["probe", f"file://{synthetic_h5ad}", "--out", str(probes_dir)])
    assert res.exit_code == 0, res.output
    dsid = next(probes_dir.glob("*.json")).stem

    picks_dir = tmp_path / "picks"
    picks_dir.mkdir()
    good = PicksV1(
        schema_version="picks-v1",
        dataset_id=dsid,
        probe_ref=str(probes_dir / f"{dsid}.json"),
        picks=["author_cell_type"],
        reasoning="test fixture",
        picker={"kind": "human", "model": "", "version": "test"},
        picked_at="2026-05-25T12:00:00Z",
    )
    (picks_dir / f"{dsid}.json").write_text(good.model_dump_json(indent=2))
    return probes_dir, picks_dir, dsid


def test_pull_skips_malformed_and_processes_the_rest(synthetic_h5ad: Path, tmp_path: Path):
    probes_dir, picks_dir, dsid = _make_probe_and_picks(synthetic_h5ad, tmp_path)
    # A malformed picks file in the same dir pull globs (`picks` must be an array).
    (picks_dir / "bad.json").write_text(
        '{"schema_version":"picks-v1","dataset_id":"x","picks":"oops"}'
    )

    pulled_dir = tmp_path / "pulled"
    res = runner.invoke(
        app, ["pull", str(picks_dir), "--probes", str(probes_dir), "--out", str(pulled_dir)]
    )

    # Non-zero (a file was bad) but NOT a crash.
    assert res.exit_code == 1, res.output
    assert "Traceback" not in res.output
    assert "SKIP bad.json" in res.output
    # The valid dataset was still pulled.
    assert (pulled_dir / f"{dsid}.json").exists()
    assert (pulled_dir / f"{dsid}.parquet").exists()


def test_pull_all_valid_exits_zero(synthetic_h5ad: Path, tmp_path: Path):
    probes_dir, picks_dir, dsid = _make_probe_and_picks(synthetic_h5ad, tmp_path)
    pulled_dir = tmp_path / "pulled"
    res = runner.invoke(
        app, ["pull", str(picks_dir), "--probes", str(probes_dir), "--out", str(pulled_dir)]
    )
    assert res.exit_code == 0, res.output


def test_pull_skips_non_json_content(synthetic_h5ad: Path, tmp_path: Path):
    probes_dir, picks_dir, dsid = _make_probe_and_picks(synthetic_h5ad, tmp_path)
    (picks_dir / "garbage.json").write_text("not json at all {")
    pulled_dir = tmp_path / "pulled"
    res = runner.invoke(
        app, ["pull", str(picks_dir), "--probes", str(probes_dir), "--out", str(pulled_dir)]
    )
    assert res.exit_code == 1, res.output
    assert "Traceback" not in res.output
    assert "SKIP garbage.json" in res.output
    assert (pulled_dir / f"{dsid}.json").exists()
