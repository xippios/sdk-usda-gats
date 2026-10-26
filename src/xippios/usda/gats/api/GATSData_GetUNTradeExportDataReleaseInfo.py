"""``GET /api/gats/UNTrade/data/exports/dataReleaseDates``: release time per reporter-year.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetUNTradeExportDataReleaseInfo``: no parameters, the response typed only as
``object``. Upstream: "Returns a set of records with the date of the last release of UN
Trade Export Data. Use this information to query for only the UN Trade Export data that
has changed since last invocation of this API End point". The record shape is the
recorded one (``models.UNTradeDataReleaseInfo``): one per reporter and statistical year,
newest year first, 3,796 records for 206 reporters from ``"1989"`` to ``"2019"`` (about
402 KB of JSON), the newest released on 2021-01-18. Error shapes are mapped once in
``xippios.usda.gats._client.classify``.

The client caches this path for an hour (``_client.CACHED_PATHS``), so the wrapper reads
the response, not only its JSON: on a cache hit it also returns when the entry was
stored, which a task reports as ``meta.retrieved_at`` (conventions §4, ADR-0015).
"""

from datetime import datetime

from xippios.core import parse
from xippios.core.client import decode_json

from xippios.usda.gats._client import SOURCE, client, stored_at
from xippios.usda.gats.models import UNTradeDataReleaseInfo

__all__ = ["GATSData_GetUNTradeExportDataReleaseInfo"]


async def GATSData_GetUNTradeExportDataReleaseInfo() -> tuple[
    list[UNTradeDataReleaseInfo], datetime | None
]:
    """Call ``GATSData_GetUNTradeExportDataReleaseInfo``.

    Returns:
        One ``UNTradeDataReleaseInfo`` per reporter and statistical year, in upstream
        order (newest year first, reporters in code order), e.g.
            ``UNTradeDataReleaseInfo(statistical_year="2019", product_type="X",
            reporter_code="AC", release_time_stamp=datetime(2020, 10, 11, 1, 15, 48))``,
        and when the client's cache answered, the time the entry was stored (UTC);
        ``None`` for an answer from the wire.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = "/api/gats/UNTrade/data/exports/dataReleaseDates"
    response = await client.get(path)
    records = parse(
        list[UNTradeDataReleaseInfo],
        decode_json(response, source=SOURCE, path=path),
        source=SOURCE,
        endpoint="GATSData_GetUNTradeExportDataReleaseInfo",
    )
    return records, stored_at(response)
