"""cxg-author-probe — identify and retrieve author cell-type annotations
from CELLxGENE source datasets.

Public API:

    from cxg_author_probe import probe, build_prompt, pull_full_column, \
        to_long_table, augment_h5ad
    from cxg_author_probe.models import ProbeV1, PicksV1, PulledV1, \
        ColumnDescriptor

See PROPOSAL.md in the repository for architecture.
"""
from ._version import __version__
from .assemble import augment_h5ad, to_long_table
from .cache import cache_path, is_fresh, load_cache, save_cache, schema_hash
from .probe import probe
from .prompt import build_prompt
from .pull import pull_full_column

__all__ = [
    "__version__",
    "probe",
    "build_prompt",
    "pull_full_column",
    "to_long_table",
    "augment_h5ad",
    "cache_path",
    "load_cache",
    "save_cache",
    "schema_hash",
    "is_fresh",
]
