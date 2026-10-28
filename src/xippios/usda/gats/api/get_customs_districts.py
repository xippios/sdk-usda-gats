"""``GET /api/gats/customsDistricts``: every US customs district with its region.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCustomsDistricts``: no parameters, the response typed only as ``object``.
Upstream: "Returns a set of records with US Customs Districts, the point of Entry and Exit
for the Commodity Imports and Exports. For Ex, Total imports from China into USA could
come in from multiple US Customs Districts for a given year." The record shape is the
recorded one, ``tests/fixtures/get_customs_districts/all.json`` (53 records,
about 8 KB of JSON), parsed into ``models.CustomsDistrict``; its ``customsDistrictId`` is
the district of the customs-district data operations. Error shapes are mapped once in
``xippios.usda.gats._client.classify``.
"""

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import CustomsDistrict

__all__ = ["get_customs_districts"]


async def get_customs_districts() -> list[CustomsDistrict]:
    """Call ``GATSData_GetCustomsDistricts``.

    Returns:
        Every customs district, in upstream order (by id), one ``CustomsDistrict`` per
        record, e.g.
            ``CustomsDistrict(customs_district_id=10,
            customs_district_name="NEW YORK, N.Y.", customs_district_region_code="EC",
            customs_district_region_name="EAST COAST DISTRICTS")``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/gats/customsDistricts")
    return parse(list[CustomsDistrict], raw, source=SOURCE, endpoint="GATSData_GetCustomsDistricts")
