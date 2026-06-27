"""Render the self-contained picker prompt for one dataset.

Input: a `ProbeV1` model. Output: a plain-text prompt string the picker
sub-agent (or any LLM) can consume directly.
"""
from __future__ import annotations

from .models import ColumnKind, ProbeV1


def build_prompt(probe: ProbeV1) -> str:
    lines: list[str] = []
    lines.append("You are evaluating an obs schema from a CELLxGENE dataset.")
    lines.append(
        "Your task: pick the obs column(s) that contain AUTHOR-PROVIDED "
        "cell-type-like annotations."
    )
    lines.append("")
    lines.append(f"Dataset id: {probe.dataset_id}")
    lines.append(f"Source format: {probe.source.format.value}")
    lines.append(f"Dataset has {len(probe.columns)} obs columns, {probe.n_cells} cells.")
    lines.append("")
    lines.append("RULES:")
    lines.append(
        "- Pick columns whose VALUES are cell-type / cell-class / cell-state labels "
        "(free-text, named clusters, marker-encoded names, hierarchies)."
    )
    lines.append(
        "- Multiple picks are fine if the dataset has labels at several "
        "granularities (e.g. broad + fine + cluster)."
    )
    lines.append(
        "- DO NOT pick CELLxGENE-standardised fields: cell_type, "
        "cell_type_ontology_term_id, etc. (already in Census)."
    )
    lines.append(
        "- DO NOT pick fields that are sample/donor/tissue/assay/QC/embedding/"
        "numeric metadata."
    )
    lines.append(
        "- If you genuinely cannot identify any author cell-type column, "
        "return an empty list."
    )
    lines.append("")
    lines.append("OBS COLUMNS (name | kind | n_unique | sample values):")
    lines.append("")
    for name in sorted(probe.columns.keys()):
        desc = probe.columns[name]
        if desc.kind == ColumnKind.categorical:
            meta = f"categorical[{desc.n_categories} cats]"
        elif desc.kind == ColumnKind.array:
            meta = f"array {desc.dtype}"
        else:
            meta = desc.kind.value if hasattr(desc.kind, "value") else str(desc.kind)
        nu = "?" if desc.n_unique is None else (
            f"~{desc.n_unique}" if desc.n_unique_estimated else str(desc.n_unique)
        )
        sample = desc.sample or []
        preview = ", ".join(repr(x) for x in sample[:10])
        if len(sample) > 10:
            preview += ", ..."
        lines.append(f"  {name}  |  {meta}  |  {nu}  |  {preview}")
    lines.append("")
    lines.append(
        "OUTPUT FORMAT: return ONLY a JSON object on a single line, no prose, "
        "no markdown:"
    )
    lines.append(
        '  {"picks": ["col1", "col2"], "reasoning": "one-sentence justification"}'
    )
    lines.append("If no valid columns, picks should be [].")
    return "\n".join(lines)
