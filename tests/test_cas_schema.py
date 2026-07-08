"""Regression tests for the CAS-shaped annotation schema (cas-v1).

Ports the atlas-reporter golden fixtures (HDCA_neurons integrated + fetal_skin
non-integrated), adapted for the upstream schema where the report-side `source`
(AtlasPaper) is OPTIONAL and a `schema_version` const is required. Validation is
via the generated `CasV1` pydantic model — the module's own validation path.

  * labelsets carry rank (0 = most granular) + role;
  * annotations are CLOSED (extra=forbid) — arbitrary obs -> author_annotation_fields,
    descriptor distributions -> composition;
  * integration provenance reuses transferred_annotations (+ cell_count/cell_ratio);
  * composition is the cell-set-level form of CxG cell-level fields.
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from cxg_author_probe.models import CasV1

# --- integrated atlas: real HDCA_neurons AMACRINE_CELL --------------------------
VALID_HDCA_INTEGRATED: dict = {
    "schema_version": "cas-v1",
    "title": "HDCA v2 — neurons",
    "matrix_file_id": "https://cellatlas.io/hdca_v2_20260311_f2.zarr",
    "cellannotation_schema_version": "0.1.0",
    "data_provenance": {
        "source_type": "published_zarr",
        "source_url": "https://cellatlas.io/hdca_v2_20260311_f2.zarr",
        "obs_column": "refined_celltype",
        "n_cells_total": 4679782,
    },
    "source": {
        "doi": "10.64898/2026.03.30.714220",
        "title": "Human Developmental Cell Atlas (HDCA) v2",
        "subatlas_papers": [
            {
                "label": "Sridhar_et_al_2020_CellPress",
                "first_author": "Sridhar",
                "year": 2020,
                "doi": "10.1016/j.celrep.2020.108023",
                "status": "asta",
            }
        ],
    },
    "labelsets": [
        {
            "name": "refined_celltype",
            "annotation_method": "manual",
            "rank": 0,
            "role": "author_cell_type",
        },
        {
            "name": "broad_celltype",
            "annotation_method": "manual",
            "rank": 1,
            "role": "author_cell_type",
        },
    ],
    "annotations": [
        {
            "labelset": "refined_celltype",
            "cell_label": "AMACRINE_CELL",
            "cell_fullname": "amacrine cell",
            "cell_ontology_term_id": "CL:0000561",
            "cell_ontology_term": "amacrine cell",
            "cell_set_accession": "HDCA:refined_celltype:AMACRINE_CELL",
            "parent_cell_set_accession": "HDCA:broad_celltype:AUDIOVISUAL_NEURONAL",
            "n_cells": 78,
            "rationale": "Retinal interneuron (Sridhar et al., 2020).",
            "rationale_dois": ["10.1016/j.celrep.2020.108023"],
            "marker_gene_evidence": ["TFAP2A", "GAD1"],
            "transferred_annotations": [
                {
                    "transferred_cell_label": "AC",
                    "source_taxonomy": "DOI:10.1016/j.celrep.2020.108023",
                    "cell_count": 77,
                    "cell_ratio": 0.987,
                    "comment": "Integration provenance (not algorithmic transfer).",
                },
            ],
            "composition": {
                "tissue": {
                    "author_field_name": "organ",
                    "values": [
                        {
                            "author_value": "Retina",
                            "value": "retina",
                            "ontology_term_id": "UBERON:0000966",
                            "cell_count": 78,
                            "cell_ratio": 1.0,
                        }
                    ],
                },
                "development_stage": {
                    "author_field_name": "development_stage",
                    "values": [
                        {"author_value": "unknown", "cell_ratio": 0.808},
                        {
                            "author_value": "HsapDv:0000048",
                            "ontology_term_id": "HsapDv:0000048",
                            "cell_ratio": 0.103,
                        },
                    ],
                },
            },
            "author_annotation_fields": {"scope": "fetal"},
        }
    ],
}

# --- non-integrated atlas: fetal_skin (the over-fit guard) ----------------------
VALID_FETAL_SKIN_NON_INTEGRATED: dict = {
    "schema_version": "cas-v1",
    "title": "A prenatal skin atlas",
    "source": {"doi": "10.1038/s41586-024-08002-x", "title": "A prenatal skin atlas"},
    "labelsets": [
        {"name": "cell_type", "annotation_method": "manual", "rank": 0, "role": "author_cell_type"}
    ],
    "annotations": [
        {
            "labelset": "cell_type",
            "cell_label": "C_Melanocyte",
            "cell_fullname": "melanocyte",
            "cell_ontology_term_id": "CL:0000148",
        }
    ],
}


def _validate(doc: dict) -> CasV1:
    return CasV1.model_validate(doc)


@pytest.mark.parametrize("doc", [VALID_HDCA_INTEGRATED, VALID_FETAL_SKIN_NON_INTEGRATED])
def test_valid_documents_pass(doc):
    _validate(doc)  # no raise


def test_source_optional_with_data_provenance():
    """Upstream: the module emits no atlas-paper `source`; a data_provenance-only
    (source-less) doc must still validate."""
    doc = copy.deepcopy(VALID_FETAL_SKIN_NON_INTEGRATED)
    del doc["source"]
    doc["data_provenance"] = {"source_type": "local_h5ad", "obs_column": "cell_type"}
    _validate(doc)


def test_non_integrated_has_no_transferred_annotations():
    for ann in VALID_FETAL_SKIN_NON_INTEGRATED["annotations"]:
        assert "transferred_annotations" not in ann


# --- closed Annotation: reject drift --------------------------------------------
def test_annotation_rejects_unknown_field():
    doc = copy.deepcopy(VALID_FETAL_SKIN_NON_INTEGRATED)
    doc["annotations"][0]["organ"] = "skin"  # inline covariate is the OLD shape
    with pytest.raises(ValidationError):
        _validate(doc)


def test_annotation_requires_cell_label():
    doc = copy.deepcopy(VALID_FETAL_SKIN_NON_INTEGRATED)
    del doc["annotations"][0]["cell_label"]
    with pytest.raises(ValidationError):
        _validate(doc)


# --- composition (Variant B) shape ----------------------------------------------
def test_composition_value_requires_author_value():
    doc = copy.deepcopy(VALID_HDCA_INTEGRATED)
    doc["annotations"][0]["composition"]["tissue"]["values"][0] = {"value": "retina"}
    with pytest.raises(ValidationError):
        _validate(doc)


def test_composition_value_rejects_unknown_key():
    doc = copy.deepcopy(VALID_HDCA_INTEGRATED)
    doc["annotations"][0]["composition"]["tissue"]["values"][0]["nonsense"] = 1
    with pytest.raises(ValidationError):
        _validate(doc)


def test_composition_cell_ratio_out_of_range_fails():
    doc = copy.deepcopy(VALID_HDCA_INTEGRATED)
    doc["annotations"][0]["composition"]["tissue"]["values"][0]["cell_ratio"] = 1.5
    with pytest.raises(ValidationError):
        _validate(doc)


# --- transferred_annotations extension ------------------------------------------
def test_transferred_requires_label():
    doc = copy.deepcopy(VALID_HDCA_INTEGRATED)
    del doc["annotations"][0]["transferred_annotations"][0]["transferred_cell_label"]
    with pytest.raises(ValidationError):
        _validate(doc)


def test_transferred_cell_ratio_out_of_range_fails():
    doc = copy.deepcopy(VALID_HDCA_INTEGRATED)
    doc["annotations"][0]["transferred_annotations"][0]["cell_ratio"] = 2.0
    with pytest.raises(ValidationError):
        _validate(doc)


# --- top-level ------------------------------------------------------------------
def test_missing_schema_version_fails():
    doc = copy.deepcopy(VALID_FETAL_SKIN_NON_INTEGRATED)
    del doc["schema_version"]
    with pytest.raises(ValidationError):
        _validate(doc)


def test_labelset_rank_must_be_non_negative():
    doc = copy.deepcopy(VALID_FETAL_SKIN_NON_INTEGRATED)
    doc["labelsets"][0]["rank"] = -1
    with pytest.raises(ValidationError):
        _validate(doc)
