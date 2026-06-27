# cxg-author-probe — proposal

**Status:** draft for review. No implementation yet. Pause point for the user to confirm architecture before code lands.

## Why this exists

CELLxGENE Census strips dataset-specific author cell-type fields (`BICCN_subclass_label`, `celltype`, `cell_type_fine`, `Cell.class`, …) at ingest. They survive only in the per-dataset source h5ads. A previous validation ([agent_celltype_eval](https://github.com/Cellular-Semantics/agent_celltype_eval), n=73, Jaccard 0.81 vs CL_KG hand curation) showed that an LLM agent fed a cheap obs **schema + 20-row sample** probe of each source file picks the author cell-type column near-perfectly. A first production implementation was vendored into [ask-census](https://github.com/Cellular-Semantics/ask-census).

This repo consolidates both. It separates the work into a Python package (importable + CLI) and a Claude plugin, with a JSON-schema-defined wire format between every stage so the LLM-required step can be deferred to a different machine, a later session, or a different agent runtime.

## Goals

1. **Run programmatic stages on a cluster** with no LLM, no Claude Code, no outbound API. Probe N datasets, write JSON-on-disk per dataset, ship results back.
2. **Run agentic stages in a Claude Code session** (or any LLM driver) by consuming those JSON files, producing picks, and feeding them back into the programmatic pull/assemble pipeline.
3. **Run end-to-end** from a Claude Code session for interactive use, with the same code paths as the split-mode case.
4. **Extend to other source formats** (Zarr-AnnData, TileDB-SOMA, parquet, …) without changing the wire format or downstream code.
5. **Plug into a larger Claude project** that has its own orchestrator + other skills, without ceremony.

## Two distinct products, one repo

| Product | Path | Distribution | Audience |
|---|---|---|---|
| Python package | `src/cxg_author_probe/` | PyPI (`pip install cxg-author-probe`) | scripts, batch jobs, custom orchestrators, anything that wants the library or CLI |
| Claude plugin | `plugin/` | git URL or local-path plugin install | Claude Code / Claude Agent SDK projects that want a drop-in skill + sub-agent |

The plugin **depends on** the Python package (declared in `plugin.json`). Skill instructions tell the agent to shell out to the `cxg-author` CLI for every non-LLM step. Nothing is duplicated.

## Four-layer surface

```
Layer 0  Python functions          from cxg_author_probe import probe, pull, …
Layer 1  CLI subcommands           cxg-author probe|render|pick|pull|assemble|augment|eval …
Layer 2  Optional API picker       cxg-author-probe[picker-anthropic]
                                   cxg-author pick prompts/  --model claude-sonnet-4-6
Layer 3  Claude plugin             skill + sub-agent; orchestrates via Layer 1 CLI
```

Layers 0–1 are pure: no LLM, no Anthropic dep, no Claude Code dep. Layer 2 is an opt-in install for users who want batch picking with an API key. Layer 3 is the agentic UX.

## Repository layout

```
cxg-author-probe/
├── pyproject.toml
├── README.md
├── LICENSE                           MIT
├── PROPOSAL.md                       this file (frozen on merge)
├── CHANGELOG.md
│
├── schemas/                          # JSON Schema, versioned
│   ├── probe-v0.schema.json          # stage-1 output  (one per dataset)
│   ├── picks-v0.schema.json          # stage-3 output  (one per dataset)
│   └── pulled-v0.schema.json         # stage-4 output  (one per dataset)
│
├── src/cxg_author_probe/
│   ├── __init__.py                   # public API
│   ├── readers/                      # ← format adapters
│   │   ├── base.py                   # ObsReader / ObsHandle protocol
│   │   ├── h5ad.py                   # HDF5 / .h5ad (first impl)
│   │   ├── zarr.py                   # placeholder (raises NotImplemented)
│   │   ├── tiledbsoma.py             # placeholder
│   │   └── registry.py               # url → reader dispatch
│   ├── probe.py                      # describe_column, head_sample, probe()
│   ├── prompt.py                     # build_prompt()
│   ├── pull.py                       # pull_full_column()
│   ├── assemble.py                   # to_long_table, augment_h5ad
│   ├── cache.py
│   ├── picker.py                     # OPTIONAL: pick_via_api() (extra)
│   ├── cli.py                        # `cxg-author` entry point
│   └── eval/                         # validation pipeline
│       ├── curation.py
│       ├── score.py
│       ├── figures.py
│       └── paper.py
│
├── plugin/                           # Claude plugin (loaded separately)
│   ├── plugin.json                   # manifest
│   ├── skills/author-annotations/
│   │   ├── SKILL.md
│   │   └── references/templates.md
│   └── agents/author-category-picker.md
│
├── tests/                            # ported + extended from ask-census
├── data/curation/                    # CL_KG CSV snapshot (eval input)
├── results/n73/                      # frozen artefacts from the paper run
├── figures/                          # PNGs referenced by paper.md
└── paper.md                          # ported from agent_celltype_eval
```

## Reader abstraction

The current implementation talks directly to `h5py`/`fsspec`. To support other formats cleanly, all source-specific access goes through a small `Protocol`:

```python
# src/cxg_author_probe/readers/base.py
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass(frozen=True)
class ColumnDescriptor:
    kind: str                       # "categorical" | "array" | "group" | "unknown"
    dtype: str                      # normalised: "int8", "float32", "string", "bool", ...
    n_unique: int | None            # populated for categorical; estimated/None otherwise
    n_unique_estimated: bool        # True if computed by sampling, False if exact
    n_categories: int | None        # alias of n_unique for categorical; None for non-cat
    shape: tuple[int, ...] | None   # for arrays
    encoding: str | None            # source-specific hint, e.g. "anndata-categorical"

@runtime_checkable
class ObsHandle(Protocol):
    def n_cells(self) -> int: ...
    def list_columns(self) -> list[str]: ...
    def describe(self, col: str) -> ColumnDescriptor: ...
    def head_sample(self, col: str, n: int = 20) -> list: ...
    def pull_full(self, col: str): ...           # -> ndarray-like (1D, n_cells)
    def joinids(self): ...                       # -> ndarray-like of observation_joinid
    def close(self) -> None: ...

@runtime_checkable
class ObsReader(Protocol):
    SUPPORTED_SCHEMES: tuple[str, ...]            # e.g. ("https", "file", "s3")
    SUPPORTED_SUFFIXES: tuple[str, ...]           # e.g. (".h5ad",)
    def open(self, url: str) -> ObsHandle: ...
```

`readers/registry.py` dispatches:

```python
def open_obs(url: str) -> ObsHandle:
    reader = pick_reader(url)        # by scheme + suffix
    return reader().open(url)
```

First implementation: `readers/h5ad.py` (the current code, lightly refactored). `readers/zarr.py` and `readers/tiledbsoma.py` ship as stubs that raise `NotImplementedError("zarr support tracked in #N")` — the architecture is in place, support lands later.

`probe()`, `pull_full_column()`, `head_sample()`, and friends never import `h5py` or `fsspec` directly — they go through the reader. That isolates the format-specific code in one place.

## The wire format

Each stage's output is **a single JSON file per dataset** validated by a JSON schema in `schemas/`.

### `probe-v0.schema.json`

The single-source-of-truth for what a probe outputs. Sketch:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/Cellular-Semantics/cxg-author-probe/schemas/probe-v0",
  "title": "cxg-author-probe probe output (v0)",
  "type": "object",
  "required": ["schema_version", "dataset_id", "source", "n_cells", "columns", "probe_meta"],
  "properties": {
    "schema_version": {"const": "probe-v0"},
    "dataset_id":     {"type": "string"},
    "source": {
      "type": "object",
      "required": ["url", "format"],
      "properties": {
        "url":    {"type": "string"},
        "format": {"enum": ["h5ad", "anndata-zarr", "tiledbsoma", "parquet"]},
        "etag":   {"type": "string", "description": "Server-provided cache validator if available"}
      }
    },
    "n_cells": {"type": "integer", "minimum": 0},
    "columns": {
      "type": "object",
      "description": "Map: obs column name -> descriptor + sample",
      "additionalProperties": {
        "type": "object",
        "required": ["kind", "dtype"],
        "properties": {
          "kind":               {"enum": ["categorical", "array", "group", "unknown"]},
          "dtype":              {"type": "string"},
          "n_unique":           {"type": ["integer", "null"]},
          "n_unique_estimated": {"type": "boolean", "default": false},
          "n_categories":       {"type": ["integer", "null"]},
          "shape":              {"type": ["array", "null"], "items": {"type": "integer"}},
          "encoding":           {"type": ["string", "null"]},
          "sample": {
            "type": "array",
            "description": "JSON-serialisable head sample of column values",
            "maxItems": 20
          }
        }
      }
    },
    "probe_meta": {
      "type": "object",
      "properties": {
        "probe_bytes":              {"type": "integer"},
        "probe_gets":               {"type": "integer"},
        "probe_time_s":             {"type": "number"},
        "reader":                   {"type": "string"},
        "package_version":          {"type": "string"},
        "probed_at":                {"type": "string", "format": "date-time"}
      }
    }
  }
}
```

Key changes vs the existing eval `probes.json` layout:

| Field | New | Old (eval) | Why |
|---|---|---|---|
| `schema_version` | ✅ | — | Forward-compat. Consumers gate on `"probe-v0"`. |
| `source.format` | ✅ | (implicit URL suffix) | Format-agnostic — `"h5ad"`, `"anndata-zarr"`, … |
| `columns.<col>.n_unique` | ✅ | — | **New** per user request. For categoricals this == `n_categories`. For non-categorical strings/objects, computed lazily (may be `None` or `n_unique_estimated=true`) — see "n_unique strategy" below. |
| `columns.<col>.sample` | ✅ (inline) | top-level `samples` dict | Each column self-contained. No more parallel dicts to keep aligned. |
| `_index` filtered out | ✅ | — | The HDF5 row-index dataset is not an obs column semantically. Filtered at probe time. |
| `curated` per-dataset | — | ✅ | Eval-only field — removed from the prod schema. Eval ground truth lives in a separate file. |

### `picks-v0.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/Cellular-Semantics/cxg-author-probe/schemas/picks-v0",
  "title": "cxg-author-probe author cell-type picks (v0)",
  "type": "object",
  "required": ["schema_version", "dataset_id", "picks"],
  "properties": {
    "schema_version": {"const": "picks-v0"},
    "dataset_id":     {"type": "string"},
    "probe_ref":      {"type": "string", "description": "Path or content hash of the probe JSON this pick was derived from"},
    "picks":          {"type": "array", "items": {"type": "string"}},
    "reasoning":      {"type": "string"},
    "picker": {
      "type": "object",
      "properties": {
        "kind":  {"enum": ["claude-code-subagent", "anthropic-api", "human", "rule-based"]},
        "model": {"type": "string"},
        "version": {"type": "string"}
      }
    },
    "picked_at": {"type": "string", "format": "date-time"}
  }
}
```

### `pulled-v0.schema.json`

For the full-column pull output. Likely Parquet on disk (not JSON) but with a JSON sidecar describing dtypes / encoding. TBD: full sketch in the first PR.

## n_unique strategy

Per user request, every column gets a `n_unique` count. How we compute it depends on `kind`:

| kind | strategy | cost |
|---|---|---|
| `categorical` | read `len(categories)` directly | free (already done) |
| `array` of small dtype (int8 / categorical-as-array) | full scan + `np.unique` | one extra read of the column |
| `array` of string / object | sample-based estimate over 1000 rows; mark `n_unique_estimated=true` | one extra small read |
| `array` of float / large numeric | skip; `n_unique=None` | free |

The probe already pulls the full categories for every categorical, so the headline metric (`n_unique` for the obvious author cell-type candidates) is essentially free. The estimate path for non-categorical strings keeps probe cost bounded.

A `--exact-unique` CLI flag forces full scans where the user wants ground truth.

## CLI surface

```
cxg-author probe       <dataset_id>... [--url-template <tpl>] [--out probes/] [--workers N]
                       Run stage 1. Emits probes/<dsid>.json (probe-v0).
                       --url-template default: "https://datasets.cellxgene.cziscience.com/{}.h5ad"

cxg-author render      <probe.json|probes-dir> [--out prompts/]
                       Stage 2: render prompt files. Pure local.

cxg-author pick        <prompts-dir> [--out picks/] [--model NAME]
                       Stage 3 — OPTIONAL (picker-anthropic extra).
                       Runs the picker via Anthropic API. Idempotent; skips existing picks.

cxg-author pull        <picks-dir> [--probes <dir>] [--out pulled/] [--workers N]
                       Stage 4: pull full picked columns. Range-read again.

cxg-author assemble    <pulled-dir> --format long|wide [--out <path.parquet>]
                       Stage 5a: long-format table.

cxg-author augment     <input.h5ad> --pulled <pulled-dir> [--out <output.h5ad>]
                       Stage 5b: in-place obs augment.

cxg-author eval        --probes <dir> --picks <dir> --curation <csv-dir> [--out <scores.json>]
                       Stage 6: metrics + CIs + null comparison.

cxg-author validate    <json-file>      # validate any artefact against its schema
cxg-author version
```

Each subcommand can take either a single file or a directory; it operates per-dataset and is idempotent (re-runs are cheap, cached entries reused unless `--force`).

## Claude plugin

The plugin lives at `plugin/` and is a separately-installable artefact. Installation contract:

```
# git URL install
claude plugin add git+https://github.com/Cellular-Semantics/cxg-author-probe.git#subdirectory=plugin

# local-path install (dev)
claude plugin add ./cxg-author-probe/plugin
```

`plugin.json` manifest declares:
- the contributed skill (`author-annotations`)
- the contributed sub-agent (`author-category-picker`)
- a runtime dep on the PyPI package (`cxg-author-probe>=0.1`)
- minimum Claude Code version

The skill's `SKILL.md` instructs the agent to:
- accept either a list of `dataset_id`s or a path to a query-result file
- shell out to `cxg-author probe`, `cxg-author render`
- dispatch the picker sub-agent via the `Task` tool with `subagent_type=author-category-picker`, one per dataset, in parallel
- shell out to `cxg-author pull`, `cxg-author assemble` / `cxg-author augment`
- never touch HDF5, h5py, fsspec directly

This means the skill is light: ~150 lines of orchestration logic. All heavy lifting is in the package.

## How it composes in a larger Claude project

Concrete deployment pattern for a parent project that wires together multiple skills + an orchestrator:

```
parent-project/
├── .claude/
│   ├── plugins.json                              # lists installed plugins
│   ├── skills/
│   │   ├── orchestrator/SKILL.md                 # decides flow, calls sub-skills
│   │   ├── cxg-query/SKILL.md
│   │   └── …
│   ├── agents/
│   │   └── ontology-term-lookup.md
│   └── (skills + agents installed by plugins land here too)
└── pyproject.toml
    dependencies = ["cxg-author-probe>=0.1", "ask-census>=0.2", ...]
```

The orchestrator skill is the **only** thing that knows the overall flow. The `author-annotations` skill (delivered by our plugin) is a leaf node: invoked with dataset_ids or a path, returns outputs at a known location, and doesn't know about any other skill.

Programmatic side of the same project can `from cxg_author_probe import probe` directly — no plugin involvement needed.

## Migration plan

1. **Today** (this commit): create repo + PROPOSAL.md + JSON schemas + README + LICENSE + .gitignore. Skeleton folders only. Push to `Cellular-Semantics/cxg-author-probe`. **PAUSE for review.**
2. Absorb `agent_celltype_eval` history via `git subtree add` into `paper.md` + `data/curation/` + `results/n73/` + `figures/`. Then refactor `src/02_sample_and_probe.py` etc. into `src/cxg_author_probe/eval/`.
3. Land the production module: copy ask-census's `src/author_annotations/` into `src/cxg_author_probe/`, refactored to go through `readers/`. Port the 9 tests verbatim.
4. CLI: implement `cxg-author probe|render|pull|assemble|augment|eval|validate`. Add tests.
5. Picker extra: `cxg-author pick` + `picker.py` (`pick_via_api`). Optional `anthropic` dep.
6. Plugin: write `plugin.json` + move skill + sub-agent. Rewrite SKILL.md to call CLI.
7. PyPI 0.1.0 release. Plugin install instructions in README.
8. ask-census migration PR: drop vendored `src/author_annotations/`, depend on `cxg-author-probe>=0.1`. Replace local skill with plugin install pointer.
9. `agent_celltype_eval` becomes a frozen redirect (README only).

## Open questions for review

- **Repo location**: live under `Cellular-Semantics/cxg-author-probe` (matches the eval repo's org). Confirm?
- **Initial schema version**: tag as `v0` until first stable release? Or jump to `v1` if we're confident the shape is right? Recommend `v0` so consumers gate explicitly.
- **n_unique computation cost**: OK with the strategy above (free for categorical, sampled for object strings, skipped for floats)? Or always compute exactly when feasible?
- **`source.etag`**: include it from day 1? It enables cheap "is the source file unchanged?" checks across Census releases. Free to include via HTTP HEAD.
- **CLI framework**: Typer (recommended — good ergonomics, hard typing) or argparse (zero deps)? Typer adds ~1 transitive dep.
- **Plugin manifest format**: the Claude Code plugin format is still evolving — should we author a manifest now or land Layer 0–2 first and add the plugin as a follow-up? Recommend: stub `plugin/` now with skill + sub-agent + a placeholder `plugin.json`; finalise manifest once we have first integration into a parent project.

---

End of proposal. **Awaiting review before implementation.**
