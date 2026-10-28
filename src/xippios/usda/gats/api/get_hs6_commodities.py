"""``GET /api/gats/HS6Commodities``: the HS6 commodity codes with their units of measure.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetHS6Commodities``: no parameters, the response typed only as ``object``.
Upstream: "Returns a list of Commodities classified at a broader level of classification,
at the HS6 Level, as opposed to HS10 Level. Use this to correlate the Import, Export and
Re-export data records obtained by querying UN Trade Data." The record shape is the
recorded one, ``tests/fixtures/get_hs6_commodities/all.json`` (2,909 records,
about 661 KB of JSON, never paged), parsed into ``models.HS6Commodity``. Error shapes are
mapped once in ``xippios.usda.gats._client.classify``.
"""

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import HS6Commodity

__all__ = ["get_hs6_commodities"]


async def get_hs6_commodities() -> list[HS6Commodity]:
    """Call ``GATSData_GetHS6Commodities``.

    Returns:
        Every HS6 commodity, in upstream order (by code), one ``HS6Commodity`` per
        record, e.g.
            ``HS6Commodity(hs6_code="010110", commodity_name="Purebred Breeding Animal",
            commodity_description="Purebred Breeding Animal", census_uom_id1=78,
            census_uom_id2=78, fas_converted_uom_id=78, fas_non_converted_uom_id=78)``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/gats/HS6Commodities")
    return parse(list[HS6Commodity], raw, source=SOURCE, endpoint="GATSData_GetHS6Commodities")
