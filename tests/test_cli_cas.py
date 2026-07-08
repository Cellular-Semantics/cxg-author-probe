"""End-to-end: probe -> picks -> pull -> `cxg-author cas` -> validated cas-v1."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cxg_author_probe.cli import app
from cxg_author_probe.models import CasV1

runner = CliRunner()


def test_cas_pipeline_end_to_end(synthetic_h5ad: Path, tmp_path: Path):
    url = f"file://{synthetic_h5ad}"

    probes = tmp_path / "probes"
    assert runner.invoke(app, ["probe", url, "--out", str(probes)]).exit_code == 0
    dsid = next(probes.glob("*.json")).stem

    # two author cell-type labelsets (fine + broad)
    picks_dir = tmp_path / "picks"
    picks_dir.mkdir()
    (picks_dir / f"{dsid}.json").write_text(
        json.dumps(
            {
                "schema_version": "picks-v1",
                "dataset_id": dsid,
                "probe_ref": str(probes / f"{dsid}.json"),
                "picks": ["author_cell_type", "broad_celltype"],
                "reasoning": "test",
            }
        )
    )

    pulled = tmp_path / "pulled"
    assert (
        runner.invoke(
            app, ["pull", str(picks_dir), "--probes", str(probes), "--out", str(pulled)]
        ).exit_code
        == 0
    )

    cas_dir = tmp_path / "cas"
    res = runner.invoke(app, ["cas", str(pulled), "--probes", str(probes), "--out", str(cas_dir)])
    assert res.exit_code == 0, res.output

    doc = json.loads((cas_dir / f"{dsid}.json").read_text())
    CasV1.model_validate(doc)  # structurally valid

    names = {ls["name"] for ls in doc["labelsets"]}
    assert names == {"author_cell_type", "broad_celltype"}
    # ranks are distinct and contiguous from 0
    assert sorted(ls["rank"] for ls in doc["labelsets"]) == [0, 1]
    # every annotation has a count; per-labelset counts sum to n_cells_total
    total = doc["data_provenance"]["n_cells_total"]
    for name in names:
        s = sum(a["n_cells"] for a in doc["annotations"] if a["labelset"] == name)
        assert s == total
    assert doc["data_provenance"]["source_type"] in {"local_h5ad", "local_zarr", "cellxgene"}

    # `validate` recognises cas-v1
    v = runner.invoke(app, ["validate", str(cas_dir / f"{dsid}.json")])
    assert v.exit_code == 0, v.output
    assert "cas-v1" in v.output
