"""Optional Python-side picker — calls the Anthropic API directly.

Requires the `picker-anthropic` extra:
    pip install cxg-author-probe[picker-anthropic]

The package's default install does NOT pull in `anthropic`; this module
imports lazily and raises a clear message if it's missing.

Use when you want to batch-pick from a cluster with an outbound API key,
or from a non-Claude-Code orchestrator. For interactive Claude Code use,
the Claude plugin's sub-agent is the preferred path.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from ._version import __version__
from .models import Picker, PickerKind, PicksV1, ProbeV1
from .prompt import build_prompt


def _require_anthropic():
    try:
        import anthropic  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "anthropic is required for the Python-side picker. "
            "Install with: pip install cxg-author-probe[picker-anthropic]"
        ) from e


_PICKS_JSON_RE = re.compile(r"\{[^{}]*\"picks\"\s*:[^{}]*\}")


def _extract_picks_json(text: str) -> dict:
    """Tolerant JSON extraction — model may wrap in ```json``` or add prose."""
    # Direct parse first.
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Search for a JSON object containing "picks".
    m = _PICKS_JSON_RE.search(text)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"Could not extract picks JSON from model output:\n{text!r}")


def pick_via_api(
    probe: ProbeV1,
    *,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 1024,
    api_key: Optional[str] = None,
    probe_ref: Optional[str] = None,
) -> PicksV1:
    """Run one picker decision via the Anthropic API.

    Parameters
    ----------
    probe : ProbeV1
        The probe to pick from.
    model : str
        Anthropic model name. Default is the current Sonnet release.
    max_tokens : int
        Response token cap. The picker output is small (~50 tokens).
    api_key : str, optional
        Override the ANTHROPIC_API_KEY env var.
    probe_ref : str, optional
        Path or content hash of the probe artefact; populated into the
        resulting PicksV1.probe_ref for traceability.
    """
    _require_anthropic()
    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    prompt_text = build_prompt(probe)

    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt_text}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "text", None))

    parsed = _extract_picks_json(text)
    picks_list = list(parsed.get("picks") or [])
    reasoning = str(parsed.get("reasoning", "")).strip()

    return PicksV1(
        schema_version="picks-v1",
        dataset_id=probe.dataset_id,
        probe_ref=probe_ref,
        picks=picks_list,
        reasoning=reasoning,
        picker=Picker(kind=PickerKind.anthropic_api, model=model, version=__version__),
        picked_at=datetime.now(timezone.utc),
    )
