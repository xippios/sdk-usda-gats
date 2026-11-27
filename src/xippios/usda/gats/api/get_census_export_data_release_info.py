"""``GET /api/gats/census/data/exports/dataReleaseDates``: release time per export month.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCensusExportDataReleaseInfo``: no parameters, the response typed only as
``object``. Upstream: "Returns a set of records with the date of the last release of
Census Export Data. Use this information to query for only those Census Export data
records that have changed since last invocation of this API End point". The record shape
is the recorded one (``models.DataReleaseInfo``): one per statistical month, newest first,
716 records from ``"196701"`` to ``"202608"`` (about 81 KB of JSON). Error shapes are
mapped once in ``xippios.usda.gats._client.classify``.

The client caches this path for an hour (``_client.LIFETIMES``), so the wrapper reads it
with ``client.get_answer``, which parses it and stores only an answer that parsed, and whose
``retrieved_at`` a task reports as ``meta.retrieved_at``: on a cache hit the time the entry
was stored, else the time the answer arrived (conventions §4, sdk-core ADR-0037).
"""

from xippios.core import Answer

from xippios.usda.gats._client import client
from xippios.usda.gats.models import DataReleaseInfo

__all__ = ["get_census_export_data_release_info"]


async def get_census_export_data_release_info() -> Answer[list[DataReleaseInfo]]:
    """Call ``GATSData_GetCensusExportDataReleaseInfo``.

    Returns:
        Core's ``Answer``: as ``payload`` one ``DataReleaseInfo`` per statistical month, in
        upstream order (newest first), e.g.
            ``DataReleaseInfo(statistical_year_month="202608", product_type="X",
            reporter_code="US", release_time_stamp=datetime(2026, 10, 6, 8, 0))``,
        and as ``retrieved_at`` when it was retrieved, timezone-aware UTC: on a cache hit
        the time the entry was stored, else the time the answer arrived.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
        ValidationError: The answer is no JSON, or no list of these records; the cache
            keeps no such answer, so the next call asks again.
    """
    path = "/api/gats/census/data/exports/dataReleaseDates"
    return await client.get_answer(
        path, parse=list[DataReleaseInfo], endpoint="GATSData_GetCensusExportDataReleaseInfo"
    )
