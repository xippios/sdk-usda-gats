"""Endpoint wrappers for USDA FAS Global Agricultural Trade System.

Layer 1 of ADR-0001: one module per upstream operation, named after it. A wrapper
takes the parameters as upstream names them (snake_cased), calls
``xippios.usda.gats._client.client`` and returns models from ``models.py`` that
mirror the payload. No composition and no defaults beyond upstream's own. The reference
is the snapshot in ``docs/upstream/``; modules and functions carry the snapshot's
``operationId`` verbatim, e.g. ``GATSData_GetCountries``.
"""

from xippios.usda.gats.api.GATSData_GetCensusExportDataReleaseInfo import (
    GATSData_GetCensusExportDataReleaseInfo,
)
from xippios.usda.gats.api.GATSData_GetCensusExports import GATSData_GetCensusExports
from xippios.usda.gats.api.GATSData_GetCensusImport import GATSData_GetCensusImport
from xippios.usda.gats.api.GATSData_GetCensusImportDataReleaseInfo import (
    GATSData_GetCensusImportDataReleaseInfo,
)
from xippios.usda.gats.api.GATSData_GetCountries import GATSData_GetCountries

__all__ = [
    "GATSData_GetCensusExportDataReleaseInfo",
    "GATSData_GetCensusExports",
    "GATSData_GetCensusImport",
    "GATSData_GetCensusImportDataReleaseInfo",
    "GATSData_GetCountries",
]
