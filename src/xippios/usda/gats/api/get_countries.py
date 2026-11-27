"""``GET /api/gats/countries``: every GATS country code with its region.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCountries``: no parameters, the response typed only as ``object``. Upstream:
"Returns a set of records with Countries and their corresponding Regions Codes the
Country belongs to." The record shape is the recorded one,
``tests/fixtures/get_countries/all.json`` (322 records), parsed into
``models.Country``; its ``countryCode`` is the ``partnerCode`` of the Census data
operations. Error shapes are mapped once in ``xippios.usda.gats._client.classify``.
"""

from xippios.core import Answer

from xippios.usda.gats._client import client
from xippios.usda.gats.models import Country

__all__ = ["get_countries"]


async def get_countries() -> Answer[list[Country]]:
    """Call ``GATSData_GetCountries``.

    Returns:
        Core's ``Answer``: as ``payload`` every GATS country code, current and discontinued, in
        upstream order, one ``Country`` per record, e.g.
            ``Country(country_code="CH", region_code="R40", country_parent_code="CH",
            country_name="China", description=None, iso3_code="CHN",
            discontinued_on=None, genc_code="CHN")``,
        and as ``retrieved_at`` the time the answer arrived, timezone-aware UTC.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    return await client.get_answer(
        "/api/gats/countries", parse=list[Country], endpoint="GATSData_GetCountries"
    )
