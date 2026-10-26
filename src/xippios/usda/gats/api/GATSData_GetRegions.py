"""``GET /api/gats/regions``: every GATS region code with its name.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetRegions``: no parameters, the response typed only as ``object``. Upstream:
"Returns a set of records with Region Codes and Region Names. Use it to associate Region
Name with Country records obtained by querying Country end point". The record shape is
the recorded one, ``tests/fixtures/GATSData_GetRegions/all.json`` (15 records, about
0.8 KB of JSON), parsed into ``models.Region``; its ``regionCode`` is the ``regionCode``
of ``GATSData_GetCountries``. Error shapes are mapped once in
``xippios.usda.gats._client.classify``.
"""

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import Region

__all__ = ["GATSData_GetRegions"]


async def GATSData_GetRegions() -> list[Region]:
    """Call ``GATSData_GetRegions``.

    Returns:
        Every GATS region, in upstream order, one ``Region`` per record, e.g.
            ``Region(region_code="R40", region_name="East Asia")``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/gats/regions")
    return parse(list[Region], raw, source=SOURCE, endpoint="GATSData_GetRegions")
