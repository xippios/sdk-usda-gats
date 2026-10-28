"""``GET /api/gats/UNTrade/data/imports/dataReleaseDates``: release time per reporter-year.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetUNTradeImportDataReleaseInfo``: no parameters, the response typed only as
``object``. Upstream: "Returns a set of records with the date of the last release of UN
Trade Import Data. Use this information to query for only the UN Trade Import data that
has changed since last invocation of this API End point". The record is
``models.UNTradeDataReleaseInfo``, as for the exports list: one per reporter and
statistical year, newest year first, 3,832 records for 207 reporters from ``"1989"`` to
``"2019"`` (about 406 KB of JSON), the newest released on 2021-01-18. Error shapes are
mapped once in ``xippios.usda.gats._client.classify``.

The client caches this path for an hour (``_client.CACHED_PATHS``), so the wrapper reads
it with ``client.get_answer``, whose ``retrieved_at`` a task reports as
``meta.retrieved_at``: on a cache hit the time the entry was stored, else the time the
answer arrived (conventions §4, ADR-0015).
"""

from datetime import datetime

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import UNTradeDataReleaseInfo

__all__ = ["GATSData_GetUNTradeImportDataReleaseInfo"]


async def GATSData_GetUNTradeImportDataReleaseInfo() -> tuple[
    list[UNTradeDataReleaseInfo], datetime
]:
    """Call ``GATSData_GetUNTradeImportDataReleaseInfo``.

    Returns:
        One ``UNTradeDataReleaseInfo`` per reporter and statistical year, in upstream
        order (newest year first, reporters in code order), e.g.
            ``UNTradeDataReleaseInfo(statistical_year="2019", product_type="M",
            reporter_code="AC", release_time_stamp=datetime(2020, 10, 11, 1, 15, 44))``,
        and when it was retrieved, timezone-aware UTC: on a cache hit the time the
        entry was stored, else the time the answer arrived.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = "/api/gats/UNTrade/data/imports/dataReleaseDates"
    answer = await client.get_answer(path)
    records = parse(
        list[UNTradeDataReleaseInfo],
        answer.payload,
        source=SOURCE,
        endpoint="GATSData_GetUNTradeImportDataReleaseInfo",
    )
    return records, answer.retrieved_at
