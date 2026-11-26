"""``GET /api/gats/regions``: every GATS region code with its name.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetRegions``: no parameters, the response typed only as ``object``. Upstream:
"Returns a set of records with Region Codes and Region Names. Use it to associate Region
Name with Country records obtained by querying Country end point". The record shape is
the recorded one, ``tests/fixtures/get_regions/all.json`` (15 records, about
0.8 KB of JSON), parsed into ``models.Region``; its ``regionCode`` is the ``regionCode``
of ``GATSData_GetCountries``. Error shapes are mapped once in
``xippios.usda.gats._client.classify``.
"""

from xippios.core import Answer

from xippios.usda.gats._client import client
from xippios.usda.gats.models import Region

__all__ = ["get_regions"]


async def get_regions() -> Answer[list[Region]]:
    """Call ``GATSData_GetRegions``.

    Returns:
        Core's ``Answer``: as ``payload`` every GATS region, in upstream order, one ``Region`` per
        record, e.g.
            ``Region(region_code="R40", region_name="East Asia")``,
        and as ``retrieved_at`` the time the answer arrived, timezone-aware UTC.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    return await client.get_answer(
        "/api/gats/regions", parse=list[Region], endpoint="GATSData_GetRegions"
    )
