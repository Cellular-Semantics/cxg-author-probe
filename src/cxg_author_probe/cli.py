"""`cxg-author` CLI — Typer entry point.

Subcommands are wrappers around the public Python API. Each one is per-dataset
and idempotent: re-runs are cheap, cached results are reused unless `--force`.

The picker stage 3 is NOT part of this CLI by default — that's the
LLM-required step and is delegated to a Claude Code sub-agent (or to
`cxg-author pick` if the `picker-anthropic` extra is installed).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from ._version import __version__
from .assemble import augment_h5ad as _augment_h5ad
from .assemble import to_long_table
from .models import PicksV1, ProbeV1, PulledV1
from .probe import probe as _probe
from .prompt import build_prompt as _build_prompt
from .pull import pull_full_column as _pull_full_column

app = typer.Typer(
    help="Identify and retrieve author cell-type annotations from CELLxGENE source datasets.",
    no_args_is_help=True,
)

DEFAULT_CDN = "https://datasets.cellxgene.cziscience.com/{dataset_id}.h5ad"


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


@app.command()
def probe(
    dataset_ids: list[str] = typer.Argument(..., help="Dataset IDs (UUIDs) or full URLs."),
    out: Path = typer.Option(Path("probes"), "--out", "-o", help="Output directory."),
    url_template: str = typer.Option(
        DEFAULT_CDN, "--url-template", help="URL template; {dataset_id} is substituted."
    ),
    exact_unique: bool = typer.Option(
        False, "--exact-unique", help="Compute exact n_unique on every column."
    ),
    force: bool = typer.Option(False, "--force", help="Re-probe even if a cached probe exists."),
) -> None:
    """Stage 1: probe obs schemas. Writes one probe-v1 JSON per dataset."""
    out.mkdir(parents=True, exist_ok=True)
    for raw in dataset_ids:
        dsid = raw if "://" not in raw else raw.rsplit("/", 1)[-1].split(".")[0]
        url = raw if "://" in raw else url_template.format(dataset_id=dsid)
        target = out / f"{dsid}.json"
        if target.exists() and not force:
            typer.echo(f"  {dsid}: cached")
            continue
        try:
            model = _probe(url, dataset_id=dsid, exact_unique=exact_unique)
            target.write_text(model.model_dump_json(indent=2))
            typer.echo(
                f"  {dsid}: {model.n_cells:,} cells, "
                f"{model.probe_meta.probe_bytes / 1e6:.2f} MB, "
                f"{model.probe_meta.probe_time_s:.1f}s, "
                f"{len(model.columns)} cols"
            )
        except Exception as e:
            typer.echo(f"  {dsid}: ERR {e}", err=True)


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


@app.command()
def render(
    inp: Path = typer.Argument(..., help="A single probe JSON or a directory of them."),
    out: Path = typer.Option(Path("prompts"), "--out", "-o", help="Output directory."),
) -> None:
    """Stage 2: render picker prompts from probe-v1 files. Pure local, no network."""
    out.mkdir(parents=True, exist_ok=True)
    probes = _iter_probes(inp)
    for probe_path in probes:
        model = ProbeV1.model_validate_json(probe_path.read_text())
        text = _build_prompt(model)
        target = out / f"{model.dataset_id}.txt"
        target.write_text(text)
        typer.echo(f"  {model.dataset_id}: {len(text)} chars")


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


@app.command()
def pull(
    picks_dir: Path = typer.Argument(
        ..., help="Directory of picks-v1 JSON files (one per dataset)."
    ),
    probes_dir: Path = typer.Option(
        Path("probes"), "--probes", help="Where to find probes-v1 JSON files (for URLs)."
    ),
    out: Path = typer.Option(Path("pulled"), "--out", "-o"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Stage 4: pull full picked columns. Reuses the source URL from each probe."""
    out.mkdir(parents=True, exist_ok=True)
    for pick_path in sorted(picks_dir.glob("*.json")):
        picks = PicksV1.model_validate_json(pick_path.read_text())
        probe_path = probes_dir / f"{picks.dataset_id}.json"
        if not probe_path.exists():
            typer.echo(f"  {picks.dataset_id}: probe not found at {probe_path}", err=True)
            continue
        probe = ProbeV1.model_validate_json(probe_path.read_text())
        sidecar = out / f"{picks.dataset_id}.json"
        if sidecar.exists() and not force:
            typer.echo(f"  {picks.dataset_id}: cached")
            continue

        stats: dict[str, int] = {}
        joinids, cols = _pull_full_column(probe.source.url, picks.picks, stats=stats)

        # Write data sidecar as Parquet (one column per pick + observation_joinid).
        import pyarrow as pa
        import pyarrow.parquet as pq

        arrs: dict[str, list] = {"observation_joinid": [str(x) for x in joinids]}
        present_picks: list[str] = []
        missing: list[str] = []
        for c in picks.picks:
            v = cols.get(c)
            if v is None:
                missing.append(c)
                continue
            arrs[c] = [None if x is None else str(x) for x in v]
            present_picks.append(c)
        parquet_path = out / f"{picks.dataset_id}.parquet"
        pq.write_table(pa.table(arrs), parquet_path)

        sidecar_model = PulledV1(
            schema_version="pulled-v1",
            dataset_id=picks.dataset_id,
            probe_ref=str(probe_path),
            picks_ref=str(pick_path),
            picks=present_picks,
            missing=missing,
            data_path=str(parquet_path),
            n_cells=len(joinids),
            pull_meta={
                "pull_bytes": stats.get("n", 0),
                "pull_gets": stats.get("calls", 0),
                "pull_time_s": None,  # not measured at this granularity
                "package_version": __version__,
                "pulled_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        sidecar.write_text(sidecar_model.model_dump_json(indent=2))
        typer.echo(
            f"  {picks.dataset_id}: {len(present_picks)} cols pulled "
            f"({stats.get('n', 0) / 1e6:.2f} MB), missing={missing or '[]'}"
        )


# ---------------------------------------------------------------------------
# assemble
# ---------------------------------------------------------------------------


@app.command()
def assemble(
    pulled_dir: Path = typer.Argument(..., help="Directory of pulled-v1 sidecars + Parquet data."),
    out: Path = typer.Option(Path("author_long.parquet"), "--out", "-o"),
) -> None:
    """Stage 5a: assemble the long-format author-annotation table."""
    import pyarrow.parquet as pq

    per_dataset: dict = {}
    for sidecar_path in sorted(pulled_dir.glob("*.json")):
        sidecar = PulledV1.model_validate_json(sidecar_path.read_text())
        data_path = Path(sidecar.data_path)
        if not data_path.is_absolute():
            data_path = sidecar_path.parent / data_path.name
        table = pq.read_table(data_path)
        df = table.to_pandas()
        joinids = df["observation_joinid"].to_numpy()
        columns = {c: df[c].to_numpy() for c in sidecar.picks if c in df.columns}
        per_dataset[sidecar.dataset_id] = {"joinids": joinids, "columns": columns}

    long = to_long_table(per_dataset)
    long.to_parquet(out, index=False)
    typer.echo(f"  wrote {len(long):,} rows to {out}")


# ---------------------------------------------------------------------------
# augment
# ---------------------------------------------------------------------------


@app.command()
def augment(
    h5ad: Path = typer.Argument(..., help="Input h5ad to augment (modified in place)."),
    pulled_dir: Path = typer.Option(
        ..., "--pulled", help="Directory of pulled-v1 sidecars + Parquet data."
    ),
) -> None:
    """Stage 5b: augment an existing h5ad's obs with picked author columns."""
    import pyarrow.parquet as pq

    per_dataset: dict = {}
    for sidecar_path in sorted(pulled_dir.glob("*.json")):
        sidecar = PulledV1.model_validate_json(sidecar_path.read_text())
        data_path = Path(sidecar.data_path)
        if not data_path.is_absolute():
            data_path = sidecar_path.parent / data_path.name
        table = pq.read_table(data_path)
        df = table.to_pandas()
        joinids = df["observation_joinid"].to_numpy()
        columns = {c: df[c].to_numpy() for c in sidecar.picks if c in df.columns}
        per_dataset[sidecar.dataset_id] = {"joinids": joinids, "columns": columns}

    _augment_h5ad(h5ad, per_dataset)
    typer.echo(f"  augmented {h5ad}")


# ---------------------------------------------------------------------------
# pick (optional — requires picker-anthropic extra)
# ---------------------------------------------------------------------------


@app.command()
def pick(
    probes_dir: Path = typer.Argument(..., help="Directory of probe-v1 JSON files."),
    out: Path = typer.Option(Path("picks"), "--out", "-o"),
    model: str = typer.Option("claude-sonnet-4-6", "--model"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Stage 3 (optional): pick author cell-type cols via the Anthropic API.

    Requires: pip install cxg-author-probe[picker-anthropic]
    """
    try:
        from .picker import pick_via_api
    except RuntimeError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2)

    out.mkdir(parents=True, exist_ok=True)
    for probe_path in sorted(probes_dir.glob("*.json")):
        p = ProbeV1.model_validate_json(probe_path.read_text())
        target = out / f"{p.dataset_id}.json"
        if target.exists() and not force:
            typer.echo(f"  {p.dataset_id}: cached")
            continue
        try:
            picks = pick_via_api(p, model=model, probe_ref=str(probe_path))
            target.write_text(picks.model_dump_json(indent=2))
            typer.echo(f"  {p.dataset_id}: {picks.picks}")
        except Exception as e:
            typer.echo(f"  {p.dataset_id}: ERR {e}", err=True)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@app.command()
def validate(
    json_path: Path = typer.Argument(
        ..., help="A JSON artefact (probe / picks / pulled) to validate."
    ),
) -> None:
    """Validate a JSON artefact against its schema (via Pydantic)."""
    text = json_path.read_text()
    # Sniff schema_version.
    try:
        sniff = json.loads(text)
    except json.JSONDecodeError as e:
        typer.echo(f"invalid JSON: {e}", err=True)
        raise typer.Exit(2)
    sv = sniff.get("schema_version", "")
    if sv == "probe-v1":
        ProbeV1.model_validate_json(text)
    elif sv == "picks-v1":
        PicksV1.model_validate_json(text)
    elif sv == "pulled-v1":
        PulledV1.model_validate_json(text)
    else:
        typer.echo(f"unknown schema_version: {sv!r}", err=True)
        raise typer.Exit(2)
    typer.echo(f"OK  {json_path}  ({sv})")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


@app.command()
def verify(
    url: str = typer.Argument(..., help="URL or path to a store/container to read as obs."),
    shallow: bool = typer.Option(False, "--shallow", help="Skip deep (full-column) checks."),
) -> None:
    """Open a source with the built-in readers and verify its obs handle.

    The acceptance gate for reading a source: exit 0 means a reader handled the
    URL and the obs view satisfies the ObsHandle contract (n_cells / joinids /
    per-column decoding, and — unless --shallow — full-column lengths). Exit 1
    prints why it failed. An improviser normalises an unreadable source until
    this passes.
    """
    from .readers import NoReaderError, check_obs_handle, open_obs

    try:
        handle = open_obs(url)
    except NoReaderError as e:
        typer.echo(f"NO READER  {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"OPEN FAILED  {type(e).__name__}: {e}", err=True)
        raise typer.Exit(1)

    problems = check_obs_handle(handle, deep=not shallow)
    if problems:
        typer.echo(f"FAILED  {url}", err=True)
        for p in problems:
            typer.echo(f"  - {p}", err=True)
        handle.close()
        raise typer.Exit(1)
    typer.echo(
        f"OK  {url}  ->  {handle.n_cells():,} cells, {len(handle.list_columns())} obs columns"
    )
    handle.close()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print package version and exit."""
    typer.echo(__version__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _iter_probes(inp: Path) -> list[Path]:
    if inp.is_dir():
        return sorted(inp.glob("*.json"))
    if inp.is_file():
        return [inp]
    raise typer.BadParameter(f"not a file or directory: {inp}")


if __name__ == "__main__":
    app()
