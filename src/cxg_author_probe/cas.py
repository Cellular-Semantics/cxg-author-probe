"""Assemble the STRUCTURAL cas-v1 skeleton from pulled author cell-type columns.

Pure, deterministic transform — no LLM, no judgment beyond cross-tab arithmetic.
Given the picked cell-type columns for one dataset (per-cell label arrays), it
emits the cas-v1 structural fields:

  * one **labelset** per picked column, ``rank`` inferred by cardinality
    (more categories = finer = lower rank);
  * one **annotation** per ``(labelset, label)`` with ``n_cells`` and a
    deterministic ``cell_set_accession``;
  * ``parent_cell_set_accession`` via the dominant coarser label (fine × coarse
    cross-tab) — the skeleton hierarchy; a strict subsumption check is a follow-up.

Map/report fields (ontology ids, rationale, atlas-paper ``source``) and
``composition``/``transferred_annotations`` are left for downstream enrichment.
``validate_cas`` is the single enforcement point (the generated ``CasV1`` model).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import CasV1


def _accession(dataset_id: str, labelset: str, label: str) -> str:
    return f"{dataset_id}:{labelset}:{label}"


def build_cas(
    labelset_columns: Mapping[str, Sequence[Any]],
    *,
    dataset_id: str,
    matrix_file_id: str | None = None,
    source_url: str | None = None,
    source_type: str = "cellxgene",
) -> dict[str, Any]:
    """Build a cas-v1 structural skeleton for one dataset.

    Parameters
    ----------
    labelset_columns:
        Mapping of picked cell-type column name -> per-cell label values
        (all the same length = n_cells). Nulls are ignored (unlabelled cells).
    dataset_id, matrix_file_id, source_url, source_type:
        Provenance for ``data_provenance`` + ``matrix_file_id``.
    """
    import pandas as pd

    names = list(labelset_columns)
    if not names:
        raise ValueError("build_cas: no labelset columns provided")

    df = pd.DataFrame({n: pd.Series(list(v), dtype="object") for n, v in labelset_columns.items()})
    n_total = len(df)

    # Rank by cardinality: most distinct labels = finest = rank 0.
    cardinality = {n: int(df[n].nunique(dropna=True)) for n in names}
    ordered = sorted(names, key=lambda n: (-cardinality[n], names.index(n)))
    ranks = {n: i for i, n in enumerate(ordered)}

    labelsets = [{"name": n, "rank": ranks[n], "role": "author_cell_type"} for n in ordered]

    annotations: list[dict[str, Any]] = []
    for i, name in enumerate(ordered):
        parent_name = ordered[i + 1] if i + 1 < len(ordered) else None
        # Dominant coarser label per fine label (skeleton hierarchy).
        parent_of: dict[Any, Any] = {}
        if parent_name is not None:
            crosstab = pd.crosstab(df[name], df[parent_name])
            if not crosstab.empty:
                parent_of = crosstab.idxmax(axis=1).to_dict()

        for label, count in df[name].value_counts(dropna=True).items():
            ann: dict[str, Any] = {
                "labelset": name,
                "cell_label": str(label),
                "n_cells": int(count),
                "cell_set_accession": _accession(dataset_id, name, str(label)),
            }
            parent_label = parent_of.get(label)
            if parent_name is not None and parent_label is not None:
                ann["parent_cell_set_accession"] = _accession(
                    dataset_id, parent_name, str(parent_label)
                )
            annotations.append(ann)

    data_provenance: dict[str, Any] = {"source_type": source_type, "dataset_id": dataset_id}
    if source_url:
        data_provenance["source_url"] = source_url
    data_provenance["n_cells_total"] = int(n_total)

    doc: dict[str, Any] = {
        "schema_version": "cas-v1",
        "labelsets": labelsets,
        "annotations": annotations,
        "data_provenance": data_provenance,
    }
    if matrix_file_id:
        doc["matrix_file_id"] = matrix_file_id
    return doc


def validate_cas(doc: Mapping[str, Any]) -> list[str]:
    """Validate a cas-v1 doc via the generated model. Empty list == valid."""
    from pydantic import ValidationError

    try:
        CasV1.model_validate(doc)
    except ValidationError as e:
        return [
            f"{'/'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in e.errors()
        ]
    return []
