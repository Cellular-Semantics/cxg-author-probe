# TODO — known follow-ups

Items here will become GitHub issues once the repo is pushed.

## Picker / probe

- [ ] **Revisit `n_unique` strategy for non-categorical string columns.**
  Right now we sample the first ~1000 rows and set `n_unique_estimated=True`.
  The picker's constant-rejection rule (rule 4) only fires when
  `n_unique_estimated == False`, so an under-sampled string column whose head
  happens to be uniform won't be incorrectly rejected. But this is overly
  cautious: a properly streamed full scan would let us reject those too,
  and would also tighten the picker's confidence on borderline columns.
  - Trade-off: full streamed scan on every obs string column adds wire-time
    proportional to obs size — for a 1M-cell categorical-encoded dataset
    this is negligible, but for a dataset with many unencoded string
    columns it could double probe cost.
  - Possible mitigation: add a `--exact-string-unique` CLI flag that
    promotes string columns from sampled to streamed exact. Default stays
    sampled.
  - Touch points: `cxg_author_probe/probe.py:_compute_n_unique`, the picker
    rule 4 in `plugin/.../agents/author-category-picker.md`.
  - Surfaced by: results/n42-revalidation/disagreements analysis,
    2026-05-25.

## Curation

- [x] Fix typo `Main_cluster_names` → `Main_cluster_name` in CL_KG curation
  (2 rows in Mo Group CSV). 2026-05-25. Should be upstreamed to the
  Cellular-Semantics/CL_KG repo so the source-of-truth matches.

## Plugin / packaging

- [ ] First PyPI release (`0.1.0`) once a couple of integration users are
  ready. Blocks the ask-census migration.
- [ ] Wire CI: pytest + drift-guard + lint on every push.
