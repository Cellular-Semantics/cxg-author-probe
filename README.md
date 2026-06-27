# cxg-author-probe

Identify and retrieve author-provided cell-type annotations from CELLxGENE-format datasets, with the LLM-required step cleanly separable from the data-fetching half.

**Status:** scaffolding only. See [`PROPOSAL.md`](PROPOSAL.md) for the design under review.

## What this is

- A **Python package** (`cxg-author-probe` on PyPI) for cheap remote obs probing, full-column pulls, long-table assembly, and h5ad augmentation. Runs anywhere — no LLM dependency in the core install.
- A **CLI** (`cxg-author`) for cluster batch jobs and orchestrators.
- An optional **`picker-anthropic` extra** for Python-side LLM picking via the Anthropic API.
- A **Claude plugin** at `plugin/cxg-author-probe/` bundling a skill and a sub-agent for end-to-end agentic use, served by the marketplace declared at `.claude-plugin/marketplace.json`. Install:
  ```
  /plugin marketplace add Cellular-Semantics/cxg-author-probe
  /plugin install cxg-author-probe@cxg-author-probe
  ```

The data-fetching and assembly stages run with **no LLM and no internet to Anthropic**, so they can run on an HPC cluster. The LLM-required picker stage is a separate step that consumes JSON probe files and produces JSON picks files — anything that can satisfy that contract is welcome.

## What's here today

- [`PROPOSAL.md`](PROPOSAL.md) — full design proposal
- [`schemas/`](schemas/) — versioned JSON schemas defining the wire format between stages (`probe-v1`, `picks-v1`, `pulled-v1`)
- Empty folders for the package, plugin, tests, and eval artefacts

## What's coming

See `PROPOSAL.md`. In order:

1. Format-agnostic reader abstraction (h5ad first; Zarr / TileDB-SOMA via the same interface later)
2. Probe + render + pull + assemble + augment functions and CLI
3. Optional Anthropic-API picker
4. Claude plugin (skill + sub-agent)
5. Validation pipeline ported from [agent_celltype_eval](https://github.com/Cellular-Semantics/agent_celltype_eval) (n=73, Jaccard 0.81 vs CL_KG curation)

## License

MIT.
