#!/usr/bin/env python3
"""Regenerate Pydantic v2 models from schemas/*.schema.json.

Concatenates the three schemas into a single combined definition so the
generated module exports `ProbeV1`, `PicksV1`, `PulledV1`, and the shared
`ColumnDescriptor` as top-level classes.

Run via: `make models` (or `python scripts/generate_models.py`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"
OUT = ROOT / "src" / "cxg_author_probe" / "models" / "_generated.py"

SCHEMA_FILES = [
    ("ProbeV1", "probe-v1.schema.json"),
    ("PicksV1", "picks-v1.schema.json"),
    ("PulledV1", "pulled-v1.schema.json"),
    ("CasV1", "cas-v1.schema.json"),
]


def main() -> int:
    # Build a combined schema with each top-level schema referenced under
    # a stable name so datamodel-code-generator emits one class per schema.
    combined: dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "cxg-author-probe v1 wire format",
        "type": "object",
        "properties": {},
        "$defs": {},
    }

    for title, fname in SCHEMA_FILES:
        with (SCHEMAS_DIR / fname).open() as f:
            schema = json.load(f)
        # Strip the inner $id so datamodel-code-generator emits top-level
        # classes rather than nested ones.
        schema.pop("$id", None)
        schema["title"] = title
        # Merge $defs upstream (only ColumnDescriptor in practice, from probe).
        for k, v in (schema.pop("$defs", {}) or {}).items():
            combined["$defs"][k] = v
        combined["properties"][title] = schema

    with NamedTemporaryFile(
        "w", suffix=".json", delete=False, dir=str(ROOT)
    ) as tmp:
        json.dump(combined, tmp, indent=2)
        tmp_path = Path(tmp.name)

    OUT.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "datamodel_code_generator",
        "--input", str(tmp_path),
        "--input-file-type", "jsonschema",
        "--output", str(OUT),
        "--output-model-type", "pydantic_v2.BaseModel",
        "--target-python-version", "3.10",
        "--use-standard-collections",
        "--use-union-operator",
        "--field-constraints",
        "--use-schema-description",
        "--use-field-description",
        "--disable-timestamp",
        "--reuse-model",
        "--collapse-root-models",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        tmp_path.unlink(missing_ok=True)

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    text = OUT.read_text()

    # Post-process to clean codegen artefacts of wrapping three schemas
    # into one combined input:
    #   1. Drop the umbrella "CxgAuthorProbeV1WireFormat" class at the end.
    #   2. Rename `Kind` (used by Picker.kind) to PickerKind.
    #   3. Rename `Kind1` (used by ColumnDescriptor.kind) to ColumnKind.
    #   4. Strip the temp-filename comment (changes every run).
    import re

    text = re.sub(r"^#   filename:.*\n", "", text, flags=re.M)

    # Drop the umbrella class — everything from its `class …WireFormat` line on.
    text = re.sub(
        r"\n\nclass CxgAuthorProbeV1WireFormat\b.*?\Z",
        "\n",
        text,
        flags=re.S,
    )
    # Token renames (whole-word).
    text = re.sub(r"\bKind1\b", "ColumnKind", text)
    text = re.sub(r"\bKind\b", "PickerKind", text)

    banner = (
        '"""Generated Pydantic v2 models for cxg-author-probe.\n\n'
        "DO NOT EDIT — regenerate via 'make models' (scripts/generate_models.py).\n"
        'Source of truth: schemas/*.schema.json.\n"""\n'
    )
    OUT.write_text(banner + text)

    print(f"Regenerated {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
