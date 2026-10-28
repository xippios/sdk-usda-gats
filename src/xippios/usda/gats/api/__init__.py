"""Endpoint wrappers, layer 1: one async function per upstream operation (conventions §2).

``/add-endpoint`` adds them. A module and its function carry the snapshot's ``operationId``
in snake case, minus the ``GATSData_`` prefix every operation shares, e.g.
``get_countries`` for ``GATSData_GetCountries``; the verbatim id stays in the first line
of the wrapper's docstring and in the ``endpoint=`` it passes, so ``meta.endpoint`` keeps
upstream's name.
"""

from xippios.usda.gats.api.get_census_export_data_release_info import (
    get_census_export_data_release_info,
)
from xippios.usda.gats.api.get_census_exports import get_census_exports
from xippios.usda.gats.api.get_census_import import get_census_import
from xippios.usda.gats.api.get_census_import_data_release_info import (
    get_census_import_data_release_info,
)
from xippios.usda.gats.api.get_census_re_exports import get_census_re_exports
from xippios.usda.gats.api.get_commodities import get_commodities
from xippios.usda.gats.api.get_countries import get_countries
from xippios.usda.gats.api.get_customs_districts import get_customs_districts
from xippios.usda.gats.api.get_customs_districts_exports import get_customs_districts_exports
from xippios.usda.gats.api.get_customs_districts_imports import get_customs_districts_imports
from xippios.usda.gats.api.get_customs_districts_re_exports import get_customs_districts_re_exports
from xippios.usda.gats.api.get_hs6_commodities import get_hs6_commodities
from xippios.usda.gats.api.get_regions import get_regions
from xippios.usda.gats.api.get_un_trade_export_data_release_info import (
    get_un_trade_export_data_release_info,
)
from xippios.usda.gats.api.get_un_trade_exports import get_un_trade_exports
from xippios.usda.gats.api.get_un_trade_import_data_release_info import (
    get_un_trade_import_data_release_info,
)
from xippios.usda.gats.api.get_un_trade_imports import get_un_trade_imports
from xippios.usda.gats.api.get_un_trade_re_exports import get_un_trade_re_exports
from xippios.usda.gats.api.get_units_of_measure import get_units_of_measure

__all__ = [
    "get_census_export_data_release_info",
    "get_census_exports",
    "get_census_import",
    "get_census_import_data_release_info",
    "get_census_re_exports",
    "get_commodities",
    "get_countries",
    "get_customs_districts",
    "get_customs_districts_exports",
    "get_customs_districts_imports",
    "get_customs_districts_re_exports",
    "get_hs6_commodities",
    "get_regions",
    "get_un_trade_export_data_release_info",
    "get_un_trade_exports",
    "get_un_trade_import_data_release_info",
    "get_un_trade_imports",
    "get_un_trade_re_exports",
    "get_units_of_measure",
]
