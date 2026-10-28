"""``GET /api/gats/customsDistrictReExports/partnerCode/{partnerCode}/year/{year}/month/{month}``.

US re-exports to one partner in one month by US customs district, as reported by the US
Census Bureau. Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCustomsDistrictsReExports`` (``Districts``, as upstream spells the
operation; the path says ``customsDistrictReExports``): three path parameters,
``partnerCode`` a string (upstream's example: ``CH`` for China, codes from
``GATSData_GetCountries``), ``year`` and ``month`` ``int32``s; the response typed only as
``object``. Upstream: "Re-Exports are all imported commodities from few countries into
USA, that are ultimately exported out to other countries from USA". The record is
``models.CustomsDistrictExport``: the recorded answer carries the customs-district
exports' eleven fields in their order and nothing else, so that model is reused rather
than copied (``tests/fixtures/get_customs_districts_re_exports/IC_2026_8.json``, 13
records, about 3 KB of JSON, for Iceland in August 2026). One answer is one partner-month
across all districts and products, never paged. Error shapes are mapped once in
``xippios.usda.gats._client.classify``; the probes recorded for
``GATSData_GetCensusExports`` were not repeated here.
"""

from urllib.parse import quote

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import CustomsDistrictExport

__all__ = ["get_customs_districts_re_exports"]


async def get_customs_districts_re_exports(
    partner_code: str, year: int, month: int
) -> list[CustomsDistrictExport]:
    """Call ``GATSData_GetCustomsDistrictsReExports``.

    Args:
        partner_code: ``partnerCode``, a GATS country code, e.g. ``"IC"`` (Iceland).
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
        f"/api/gats/customsDistrictReExports/partnerCode/{quote(partner_code, safe='')}"
        f"/year/{year}/month/{month}"
    )
    raw = await client.get_json(path)
    return parse(
        list[CustomsDistrictExport],
        raw,
        source=SOURCE,
        endpoint="GATSData_GetCustomsDistrictsReExports",
    )
