"""``GET /api/gats/censusExports/partnerCode/{partnerCode}/year/{year}/month/{month}``.

US exports to one partner in one month, as reported by the US Census Bureau. Reference:
``docs/upstream/openapi/portal-document.json``, operation ``GATSData_GetCensusExports``:
three path parameters, ``partnerCode`` a string (upstream's example: ``CH`` for China,
codes from ``GATSData_GetCountries``), ``year`` and ``month`` ``int32``s; the response
typed only as ``object``. Upstream: "Census reports data on a monthly basis with
corrections applied once a year." The record shape is the recorded one
(``models.CensusExport``): one answer is one partner-month across all products, never
paged or sliced (777 records, about 154 KB of JSON, for China in August 2026).

An unknown partner code, a month after the latest release and a listed partner without
trade all answer HTTP 200 with ``[]``, and month 0 and month 13 HTTP 404 with an empty
body, which core's status mapping raises as ``NotFoundError``: the notes "An unknown code
answers the empty list", "A period not released answers the empty list" and "Month 0, month
13 and a year that is no number answer HTTP 404 with an empty body" of
``docs/upstream/OBSERVED.md``, with their fixtures.
"""

from urllib.parse import quote

from xippios.core import Answer

from xippios.usda.gats._client import client
from xippios.usda.gats.models import CensusExport

__all__ = ["get_census_exports"]


async def get_census_exports(
    partner_code: str, year: int, month: int
) -> Answer[list[CensusExport]]:
    """Call ``GATSData_GetCensusExports``.

    Args:
        partner_code: ``partnerCode``, a GATS country code, e.g. ``"CH"`` (China).
        year: ``year``, e.g. ``2026``.
        month: ``month``, e.g. ``8`` (August).

    Returns:
        Core's ``Answer``: as ``payload`` one ``CensusExport`` per HS10 code, in upstream order;
        ``[]`` when upstream has none,
        and as ``retrieved_at`` the time the answer arrived, timezone-aware UTC.

    Raises:
        NotFoundError: Upstream answered HTTP 404 (recorded for month 0 and month 13).
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/gats/censusExports/partnerCode/{quote(partner_code, safe='')}"
        f"/year/{year}/month/{month}"
    )
    return await client.get_answer(
        path, parse=list[CensusExport], endpoint="GATSData_GetCensusExports"
    )
