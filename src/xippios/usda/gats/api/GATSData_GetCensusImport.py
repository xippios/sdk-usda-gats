"""``GET /api/gats/censusImports/partnerCode/{partnerCode}/year/{year}/month/{month}``.

US imports from one partner in one month, as reported by the US Census Bureau.
Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCensusImport`` (singular, as upstream spells it): three path parameters,
``partnerCode`` a string (upstream's example: ``CH`` for China, codes from
``GATSData_GetCountries``), ``year`` and ``month`` ``int32``s; the response typed only as
``object``. The record shape is the recorded one (``models.CensusImport``): one answer is
one partner-month across all products, never paged or sliced (3,294 records, about
1.1 MB of JSON, for China in August 2026). Error shapes are mapped once in
``xippios.usda.gats._client.classify``; the probes recorded for ``GATSData_GetCensusExports``
were not repeated here.
"""

from urllib.parse import quote

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import CensusImport

__all__ = ["GATSData_GetCensusImport"]


async def GATSData_GetCensusImport(partner_code: str, year: int, month: int) -> list[CensusImport]:
    """Call ``GATSData_GetCensusImport``.

    Args:
        partner_code: ``partnerCode``, a GATS country code, e.g. ``"CH"`` (China).
        year: ``year``, e.g. ``2026``.
        month: ``month``, e.g. ``8`` (August).

    Returns:
        One ``CensusImport`` per HS10 code, in upstream order; ``[]`` when upstream has
        none.

    Raises:
        NotFoundError: Upstream answered HTTP 404.
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/gats/censusImports/partnerCode/{quote(partner_code, safe='')}"
        f"/year/{year}/month/{month}"
    )
    raw = await client.get_json(path)
    return parse(list[CensusImport], raw, source=SOURCE, endpoint="GATSData_GetCensusImport")
