# author-annotations templates

Copy-paste recipes for each mode of the skill. All steps shell out to the
`cxg-author` CLI from the `cxg-author-probe` package.

---

## Template A — fresh dataset list, emit long table

```bash
# Stage 1: probe every dataset (parallel-friendly, idempotent)
cxg-author probe DSID1 DSID2 DSID3 --out probes/

# Stage 2: render picker prompts
cxg-author render probes/ --out prompts/

# Stage 3: dispatch the picker sub-agent for each prompt
# (see SKILL.md — Task tool, subagent_type=author-category-picker)
# Sub-agent writes picks/<dsid>.json wrapped in the picks-v1 envelope.

# Stage 4: pull picked columns
cxg-author pull picks/ --probes probes/ --out pulled/

# Stage 5a: assemble long table
cxg-author assemble pulled/ --out outputs/myquery_$(date +%Y%m%d_%H%M%S)_author.parquet
```

---

## Template B — augment an existing h5ad in place

```bash
# Read dataset_ids from the h5ad's obs.dataset_id.unique()
python -c "import anndata; print(*anndata.read_h5ad('outputs/x.h5ad', backed='r').obs.dataset_id.unique())" > dsids.txt

cxg-author probe $(cat dsids.txt) --out probes/
cxg-author render probes/ --out prompts/
# ... dispatch picker sub-agents ...
cxg-author pull picks/ --probes probes/ --out pulled/

# Stage 5b: in-place augment
cxg-author augment outputs/x.h5ad --pulled pulled/
```

After augment, the h5ad's `obs` has new `author_<col>` columns for any cell
whose source dataset had an author cell-type column picked. Cells without
picks remain NaN in those columns.

---

## Template C — Python API (custom orchestrator)

```python
from cxg_author_probe import probe, build_prompt, pull_full_column, augment_h5ad
from cxg_author_probe.picker import pick_via_api   # optional extra

for dsid in dataset_ids:
    url = f"https://datasets.cellxgene.cziscience.com/{dsid}.h5ad"
    p = probe(url, dataset_id=dsid)
    picks = pick_via_api(p, model="claude-sonnet-4-6")   # or supply your own
    joinids, cols = pull_full_column(url, picks.picks)
    # ... assemble / augment ...
```

---

## Sub-agent dispatch (mirrors `ontology-term-lookup` pattern)

```
Task subagent_type=author-category-picker
     prompt="""Read /path/to/prompt.txt. Follow its instructions. Write your
     JSON answer to /path/to/picks/<dsid>.json (just the agent's part — the
     skill wraps it into the picks-v1 envelope). Output nothing else."""
```

Dispatch one Task per dataset, in parallel.

## Schema gates

Every artefact carries `"schema_version": "probe-v1"`, `"picks-v1"`, or
`"pulled-v1"`. Consumers should gate on these strings. To validate a file
manually:

```bash
cxg-author validate <path/to/file.json>
```
