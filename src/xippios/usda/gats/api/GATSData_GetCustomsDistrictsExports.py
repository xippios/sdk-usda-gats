"""``GET /api/gats/customsDistrictExports/partnerCode/{partnerCode}/year/{year}/month/{month}``.

US exports to one partner in one month by US customs district, as reported by the US
Census Bureau. Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCustomsDistrictsExports`` (``Districts``, as upstream spells the operation;
the path says ``customsDistrictExports``): three path parameters, ``partnerCode`` a
string (upstream's example: ``CH`` for China, codes from ``GATSData_GetCountries``),
``year`` and ``month`` ``int32``s; the response typed only as ``object``. Upstream:
"Census reports data on a monthly basis with corrections applied once a year." The record
shape is the recorded one (``models.CustomsDistrictExport``, the exports' record with
``customsDistrictId`` first): one answer is one partner-month across all districts and
products, never paged (107 records, about 23 KB of JSON, for Iceland in August 2026;
1,697 records, about 374 KB, for China). Error shapes are mapped once in
``xippios.usda.gats._client.classify``; the probes recorded for
``GATSData_GetCensusExports`` were not repeated here.
"""

from urllib.parse import quote

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import CustomsDistrictExport

__all__ = ["GATSData_GetCustomsDistrictsExports"]


async def GATSData_GetCustomsDistrictsExports(
    partner_code: str, year: int, month: int
) -> list[CustomsDistrictExport]:
    """Call ``GATSData_GetCustomsDistrictsExports``.

    Args:
        partner_code: ``partnerCode``, a GATS country code, e.g. ``"CH"`` (China).
        year: ``year``, e.g. ``2026``.
        month: ``month``, e.g. ``8`` (August).

    Returns:
        One ``CustomsDistrictExport`` per customs district and HS10 code, in upstream
        order; ``[]`` when upstream has none.

    Raises:
        NotFoundError: Upstream answered HTTP 404.
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/gats/customsDistrictExports/partnerCode/{quote(partner_code, safe='')}"
        f"/year/{year}/month/{month}"
    )
    raw = await client.get_json(path)
    return parse(
        list[CustomsDistrictExport],
        raw,
        source=SOURCE,
        endpoint="GATSData_GetCustomsDistrictsExports",
    )
