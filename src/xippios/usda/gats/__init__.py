"""Typed client, MCP tools and HTTP routes for USDA FAS Global Agricultural Trade System.

Distribution ``xippios-usda-gats``. Public API: ``__version__`` and the task
functions re-exported here. Endpoint wrappers under ``api/`` and the configured client
in ``_client`` are internal.
"""

from xippios.usda.gats._version import __version__
from xippios.usda.gats.tasks import (
    get_census_exports,
    get_census_imports,
    get_census_release_dates,
)

__all__ = [
    "__version__",
    "get_census_exports",
    "get_census_imports",
    "get_census_release_dates",
]
