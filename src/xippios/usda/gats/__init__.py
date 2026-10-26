"""Typed client, MCP tools and HTTP routes for USDA FAS Global Agricultural Trade System.

Distribution ``xippios-usda-gats``. Public API: ``__version__`` and the task
functions re-exported here. Endpoint wrappers under ``api/`` and the configured client
in ``_client`` are internal. ``tasks`` also exposes the Census series ceiling
(``SERIES_MAX_MONTHS``, ``MCP_SERIES_MAX_MONTHS``, ``series_ceiling``,
``set_series_ceiling``) and the MCP server's option hooks (``mcp_add_options``,
``mcp_apply_options``), which are not tasks: they are not in ``tasks.__all__``, so no
adapter registers them, and not re-exported here.
"""

from xippios.usda.gats._version import __version__
from xippios.usda.gats.tasks import (
    get_census_export_series,
    get_census_exports,
    get_census_import_series,
    get_census_imports,
    get_census_reexport_series,
    get_census_reexports,
    get_census_release_dates,
    get_customs_district_exports,
    get_customs_district_imports,
    get_customs_district_reexports,
    get_un_exports,
    get_un_imports,
    get_un_reexports,
    get_un_release_dates,
    list_commodities,
    list_countries,
    list_customs_districts,
    list_hs6_commodities,
    list_regions,
    list_units_of_measure,
)

__all__ = [
    "__version__",
    "get_census_export_series",
    "get_census_exports",
    "get_census_import_series",
    "get_census_imports",
    "get_census_reexport_series",
    "get_census_reexports",
    "get_census_release_dates",
    "get_customs_district_exports",
    "get_customs_district_imports",
    "get_customs_district_reexports",
    "get_un_exports",
    "get_un_imports",
    "get_un_reexports",
    "get_un_release_dates",
    "list_commodities",
    "list_countries",
    "list_customs_districts",
    "list_hs6_commodities",
    "list_regions",
    "list_units_of_measure",
]
