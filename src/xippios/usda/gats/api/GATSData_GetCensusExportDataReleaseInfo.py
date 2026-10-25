"""``GET /api/gats/census/data/exports/dataReleaseDates``: release time per export month.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCensusExportDataReleaseInfo``: no parameters, the response typed only as
``object``. Upstream: "Returns a set of records with the date of the last release of
Census Export Data. Use this information to query for only those Census Export data
records that have changed since last invocation of this API End point". The record shape
is the recorded one (``models.DataReleaseInfo``): one per statistical month, newest first,
716 records from ``"196701"`` to ``"202608"`` (about 81 KB of JSON). Error shapes are
mapped once in ``xippios.usda.gats._client.classify``.
"""

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import DataReleaseInfo

__all__ = ["GATSData_GetCensusExportDataReleaseInfo"]


async def GATSData_GetCensusExportDataReleaseInfo() -> list[DataReleaseInfo]:
    """Call ``GATSData_GetCensusExportDataReleaseInfo``.

    Returns:
        One ``DataReleaseInfo`` per statistical month, in upstream order (newest first),
        e.g.
            ``DataReleaseInfo(statistical_year_month="202608", product_type="X",
            reporter_code="US", release_time_stamp=datetime(2026, 10, 6, 8, 0))``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/gats/census/data/exports/dataReleaseDates")
    return parse(
        list[DataReleaseInfo],
        raw,
        source=SOURCE,
        endpoint="GATSData_GetCensusExportDataReleaseInfo",
    )
