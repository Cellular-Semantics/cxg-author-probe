"""Figure generators for the eval paper. Matplotlib-only (optional `eval` extra)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def render_figures(scores: dict, out_dir: str | Path) -> list[Path]:
    """Write the five paper figures into out_dir; return their paths.

    Requires matplotlib (install with `cxg-author-probe[eval]`).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = scores["per_dataset"]
    overall = scores["overall"]
    paths: list[Path] = []

    # Fig 1 — Jaccard histogram.
    fig, ax = plt.subplots(figsize=(6, 4))
    j_vals = [r["jaccard"] for r in rows]
    ax.hist(j_vals, bins=np.linspace(0, 1, 21), color="#3a7", edgecolor="black", alpha=0.85)
    ax.axvline(overall["jaccard"]["mean"], color="black", linestyle="--",
               label=f"mean = {overall['jaccard']['mean']:.2f}")
    ax.set_xlabel("Jaccard(agent picks, curated cell-type cols)")
    ax.set_ylabel("Datasets")
    ax.set_title(f"Agent vs CL_KG — Jaccard (n={overall['n']})")
    ax.legend(fontsize=9)
    fig.tight_layout()
    p1 = out_dir / "fig1_jaccard_histogram.png"
    fig.savefig(p1, dpi=160)
    plt.close(fig)
    paths.append(p1)

    # Fig 2 — Per-dataset bars (sorted by Jaccard).
    rs = sorted(rows, key=lambda r: r["jaccard"])
    x = np.arange(len(rs))
    fig, ax = plt.subplots(figsize=(10, max(4, len(rs) * 0.18)))
    w = 0.27
    ax.barh(x - w, [r["jaccard"] for r in rs], w, label="Jaccard", color="#3a7")
    ax.barh(x, [r["precision"] for r in rs], w, label="Precision", color="#37a")
    ax.barh(x + w, [r["recall"] for r in rs], w, label="Recall", color="#a73")
    ax.set_yticks(x)
    ax.set_yticklabels([r["dsid"][:8] for r in rs], fontsize=7)
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Score")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title("Per-dataset metrics (sorted by Jaccard)")
    fig.tight_layout()
    p2 = out_dir / "fig2_per_dataset_bars.png"
    fig.savefig(p2, dpi=160)
    plt.close(fig)
    paths.append(p2)

    return paths
