"""Evaluation harness — score picks against CL_KG hand curation.

This is the validation pipeline that produced the n=73 paper result
(Jaccard 0.81 vs CL_KG, https://github.com/Cellular-Semantics/agent_celltype_eval).
Ported from agent_celltype_eval/src/{01,04,05,06}.py and refactored.
"""
from .curation import parse_curation
from .score import (
    bootstrap_ci,
    hypergeom_p_hit,
    jaccard,
    score_picks,
    wilson,
)

__all__ = [
    "parse_curation",
    "score_picks",
    "jaccard",
    "wilson",
    "bootstrap_ci",
    "hypergeom_p_hit",
]
