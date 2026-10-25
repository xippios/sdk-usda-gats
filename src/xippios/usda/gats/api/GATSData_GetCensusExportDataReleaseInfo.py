"""``GET /api/gats/census/data/exports/dataReleaseDates``: release time per export month.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCensusExportDataReleaseInfo``: no parameters, the response typed only as
``object``. Upstream: "Returns a set of records with the date of the last release of
Census Export Data. Use this information to query for only those Census Export data
records that have changed since last invocation of this API End point". The record shape
is the recorded one (``models.DataReleaseInfo``): one per statistical month, newest first,
716 records from ``"196701"`` to ``"202608"`` (about 81 KB of JSON). Error shapes are
mapped once in ``xippios.usda.gats._client.classify``.

The client caches this path for an hour (``_client.CACHED_PATHS``), so the wrapper reads
the response, not only its JSON: on a cache hit it also returns when the entry was
stored, which a task reports as ``meta.retrieved_at`` (conventions §4, ADR-0015).
"""

from datetime import datetime

from xippios.core import parse
from xippios.core.client import decode_json

from xippios.usda.gats._client import SOURCE, client, stored_at
from xippios.usda.gats.models import DataReleaseInfo

__all__ = ["GATSData_GetCensusExportDataReleaseInfo"]


async def GATSData_GetCensusExportDataReleaseInfo() -> tuple[
    list[DataReleaseInfo], datetime | None
]:
    """Call ``GATSData_GetCensusExportDataReleaseInfo``.

    Returns:
        One ``DataReleaseInfo`` per statistical month, in upstream order (newest first),
        e.g.
            ``DataReleaseInfo(statistical_year_month="202608", product_type="X",
            reporter_code="US", release_time_stamp=datetime(2026, 10, 6, 8, 0))``,
        and when the client's cache answered, the time the entry was stored (UTC);
        ``None`` for an answer from the wire.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = "/api/gats/census/data/exports/dataReleaseDates"
    response = await client.get(path)
    records = parse(
        list[DataReleaseInfo],
        decode_json(response, source=SOURCE, path=path),
        source=SOURCE,
        endpoint="GATSData_GetCensusExportDataReleaseInfo",
    )
    return records, stored_at(response)
