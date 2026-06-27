"""End-to-end CLI smoke tests against the synthetic fixture.

Exercises: probe → render → validate → (synthetic pick) → pull → assemble → augment.
"""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cxg_author_probe.cli import app
from cxg_author_probe.models import PicksV1, ProbeV1, PulledV1

runner = CliRunner()


def test_version():
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0, res.output
    assert res.output.strip()


def test_full_pipeline_end_to_end(synthetic_h5ad: Path, tmp_path: Path):
    url = f"file://{synthetic_h5ad}"

    # --- probe ---
    probes_dir = tmp_path / "probes"
    res = runner.invoke(app, ["probe", url, "--out", str(probes_dir)])
    assert res.exit_code == 0, res.output
    probe_files = list(probes_dir.glob("*.json"))
    assert len(probe_files) == 1
    dsid = probe_files[0].stem
    probe_model = ProbeV1.model_validate_json(probe_files[0].read_text())
    assert probe_model.n_cells == 10

    # --- render ---
    prompts_dir = tmp_path / "prompts"
    res = runner.invoke(app, ["render", str(probes_dir), "--out", str(prompts_dir)])
    assert res.exit_code == 0, res.output
    prompt_text = (prompts_dir / f"{dsid}.txt").read_text()
    assert "author_cell_type" in prompt_text

    # --- validate (the probe file) ---
    res = runner.invoke(app, ["validate", str(probe_files[0])])
    assert res.exit_code == 0, res.output
    assert "probe-v1" in res.output

    # --- synthesise a picks file (skipping LLM step in tests) ---
    picks_dir = tmp_path / "picks"
    picks_dir.mkdir()
    picks_model = PicksV1(
        schema_version="picks-v1",
        dataset_id=dsid,
        probe_ref=str(probe_files[0]),
        picks=["author_cell_type", "broad_celltype"],
        reasoning="test fixture",
        picker={"kind": "human", "model": "", "version": "test"},
        picked_at="2026-05-25T12:00:00Z",
    )
    (picks_dir / f"{dsid}.json").write_text(picks_model.model_dump_json(indent=2))

    res = runner.invoke(app, ["validate", str(picks_dir / f"{dsid}.json")])
    assert res.exit_code == 0, res.output

    # --- pull ---
    pulled_dir = tmp_path / "pulled"
    res = runner.invoke(
        app,
        ["pull", str(picks_dir), "--probes", str(probes_dir), "--out", str(pulled_dir)],
    )
    assert res.exit_code == 0, res.output
    sidecar_path = pulled_dir / f"{dsid}.json"
    assert sidecar_path.exists()
    sidecar = PulledV1.model_validate_json(sidecar_path.read_text())
    assert sidecar.n_cells == 10
    assert set(sidecar.picks) == {"author_cell_type", "broad_celltype"}
    assert (pulled_dir / f"{dsid}.parquet").exists()

    # --- assemble ---
    long_out = tmp_path / "long.parquet"
    res = runner.invoke(
        app, ["assemble", str(pulled_dir), "--out", str(long_out)]
    )
    assert res.exit_code == 0, res.output
    import pyarrow.parquet as pq

    df = pq.read_table(long_out).to_pandas()
    assert len(df) == 20  # 10 cells × 2 cols
    assert set(df.columns) == {"observation_joinid", "dataset_id", "author_column", "value"}

    # --- augment ---
    res = runner.invoke(
        app, ["augment", str(synthetic_h5ad), "--pulled", str(pulled_dir)]
    )
    assert res.exit_code == 0, res.output
    import anndata as ad

    after = ad.read_h5ad(synthetic_h5ad)
    assert "author_author_cell_type" in after.obs.columns
    assert "author_broad_celltype" in after.obs.columns
    assert after.n_obs == 10
