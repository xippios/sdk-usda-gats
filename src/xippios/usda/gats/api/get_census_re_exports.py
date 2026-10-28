"""``GET /api/gats/censusReExports/partnerCode/{partnerCode}/year/{year}/month/{month}``.

US re-exports to one partner in one month, as reported by the US Census Bureau.
Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCensusReExports``: three path parameters, ``partnerCode`` a string
(upstream's example: ``CH`` for China, codes from ``GATSData_GetCountries``), ``year`` and
``month`` ``int32``s; the response typed only as ``object``. Upstream: "Census reports
data on a monthly basis with corrections applied once a year." The record is
``models.CensusExport``: the recorded answer carries the exports' ten fields in their
order and nothing else, so the exports' model is reused rather than copied
(``tests/fixtures/GATSData_GetCensusReExports/IC_2026_8.json``, 12 records, about 2 KB of
JSON, for Iceland in August 2026). One answer is one partner-month across all products,
never paged. Error shapes are mapped once in ``xippios.usda.gats._client.classify``; the
probes recorded for ``GATSData_GetCensusExports`` were not repeated here.
"""

from urllib.parse import quote

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import CensusExport

__all__ = ["get_census_re_exports"]


async def get_census_re_exports(partner_code: str, year: int, month: int) -> list[CensusExport]:
    """Call ``GATSData_GetCensusReExports``.

    Args:
        partner_code: ``partnerCode``, a GATS country code, e.g. ``"IC"`` (Iceland).
        year: ``year``, e.g. ``2026``.
        month: ``month``, e.g. ``8`` (August).

    Returns:
        One ``CensusExport`` per HS10 code, in upstream order; ``[]`` when upstream has
        none.

    Raises:
        NotFoundError: Upstream answered HTTP 404.
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/gats/censusReExports/partnerCode/{quote(partner_code, safe='')}"
        f"/year/{year}/month/{month}"
    )
    raw = await client.get_json(path)
    return parse(list[CensusExport], raw, source=SOURCE, endpoint="GATSData_GetCensusReExports")
