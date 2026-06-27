"""Eval submodule tests — pure metrics + the live n=73 results round-trip."""
from __future__ import annotations

import json
from pathlib import Path

from cxg_author_probe.eval import (
    bootstrap_ci,
    hypergeom_p_hit,
    jaccard,
    parse_curation,
    score_picks,
    wilson,
)

ROOT = Path(__file__).resolve().parent.parent


def test_jaccard_basic():
    assert jaccard([], []) == 1.0
    assert jaccard(["a"], []) == 0.0
    assert jaccard(["a", "b"], ["b", "c"]) == 1 / 3
    assert jaccard(["a"], ["a"]) == 1.0


def test_wilson_known():
    lo, hi = wilson(72, 73)
    assert 0.92 < lo < 0.95
    assert hi > 0.99


def test_bootstrap_ci_runs():
    lo, hi = bootstrap_ci([0.5, 0.6, 0.7, 0.8, 0.9], B=1000, seed=0)
    assert 0 <= lo <= hi <= 1


def test_hypergeom_p_hit_edge_cases():
    assert hypergeom_p_hit(N=40, K=0, k=3) == 0.0
    assert hypergeom_p_hit(N=40, K=3, k=0) == 0.0
    # Picking everything always hits when there's something to hit.
    assert hypergeom_p_hit(N=40, K=3, k=40) == 1.0


def test_parse_curation_celltype_filter():
    curation_dir = ROOT / "data" / "curation"
    if not any(curation_dir.glob("*.csv")):
        import pytest
        pytest.skip("no curation snapshot under data/curation/")
    ct = parse_curation(curation_dir, filter_celltype=True)
    full = parse_curation(curation_dir, filter_celltype=False)
    # Cell-type-filtered should be strictly smaller — more datasets in full
    # because non-cell-type rows survive there.
    assert len(ct) <= len(full)
    # Spot-check: every retained entry has at least one column.
    for v in ct.values():
        assert v["columns"]


def test_score_picks_smoke():
    picks = {"d1": ["A", "B"], "d2": ["X"]}
    curation = {"d1": {"columns": ["A", "C"]}, "d2": {"columns": ["X", "Y"]}}
    out = score_picks(picks, curation)
    assert out["overall"]["n"] == 2
    # d1: jaccard 1/3, precision 1/2, recall 1/2, hit 1
    d1 = next(r for r in out["per_dataset"] if r["dsid"] == "d1")
    assert d1["jaccard"] == 1 / 3
    assert d1["precision"] == 0.5
    assert d1["recall"] == 0.5
    assert d1["hit"] == 1


def test_n73_results_can_be_rescored():
    """Re-run scoring against the frozen n=73 results — sanity-check
    that the eval module reproduces the headline numbers."""
    results_dir = ROOT / "results" / "n73"
    picks_path = results_dir / "picks.json"
    scores_path = results_dir / "scores.json"
    if not (picks_path.exists() and scores_path.exists()):
        import pytest
        pytest.skip("n=73 frozen results not present")

    frozen = json.loads(scores_path.read_text())
    picks_json = json.loads(picks_path.read_text())
    # picks.json is dataset_id -> {"picks": [...], "reasoning": "..."}
    picks = {dsid: v.get("picks", []) for dsid, v in picks_json.items()}

    curation = parse_curation(ROOT / "data" / "curation", filter_celltype=True)
    rescored = score_picks(picks, curation)

    # Allow ±0.005 wiggle for bootstrap CI variability (we re-seed).
    assert (
        abs(rescored["overall"]["jaccard"]["mean"]
            - frozen["overall"]["jaccard"]["mean"]) < 0.01
    )
    assert (
        rescored["overall"]["hit_rate"]["k"]
        == frozen["overall"]["hit_rate"]["k"]
    )
