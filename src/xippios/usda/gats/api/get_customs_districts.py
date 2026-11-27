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

from xippios.core import Answer

from xippios.usda.gats._client import client
from xippios.usda.gats.models import CustomsDistrict

__all__ = ["get_customs_districts"]


async def get_customs_districts() -> Answer[list[CustomsDistrict]]:
    """Call ``GATSData_GetCustomsDistricts``.

    Returns:
        Core's ``Answer``: as ``payload`` every customs district, in upstream order (by id), one
        ``CustomsDistrict`` per record, e.g.
            ``CustomsDistrict(customs_district_id=10,
            customs_district_name="NEW YORK, N.Y.", customs_district_region_code="EC",
            customs_district_region_name="EAST COAST DISTRICTS")``,
        and as ``retrieved_at`` the time the answer arrived, timezone-aware UTC.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    return await client.get_answer(
        "/api/gats/customsDistricts",
        parse=list[CustomsDistrict],
        endpoint="GATSData_GetCustomsDistricts",
    )
