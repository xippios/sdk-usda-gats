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

The client caches this path for a day (``_client.UN_RELEASE_DATES_TTL``), the feed being
frozen, so the wrapper reads it with ``client.get_answer``, which parses it and stores only
an answer that parsed, and whose ``retrieved_at`` a task reports as ``meta.retrieved_at``:
on a cache hit the time the entry was stored, else the time the answer arrived (conventions
§4, sdk-core ADR-0037).
"""

from xippios.core import Answer

from xippios.usda.gats._client import client
from xippios.usda.gats.models import UNTradeDataReleaseInfo

__all__ = ["get_un_trade_import_data_release_info"]


async def get_un_trade_import_data_release_info() -> Answer[list[UNTradeDataReleaseInfo]]:
    """Call ``GATSData_GetUNTradeImportDataReleaseInfo``.

    Returns:
        Core's ``Answer``: as ``payload`` one ``UNTradeDataReleaseInfo`` per reporter and
        statistical year, in upstream order (newest year first, reporters in code order),
        e.g.
            ``UNTradeDataReleaseInfo(statistical_year="2019", product_type="M",
            reporter_code="AC", release_time_stamp=datetime(2020, 10, 11, 1, 15, 44))``,
        and as ``retrieved_at`` when it was retrieved, timezone-aware UTC: on a cache hit
        the time the entry was stored, else the time the answer arrived.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
        ValidationError: The answer is no JSON, or no list of these records; the cache
            keeps no such answer, so the next call asks again.
    """
    path = "/api/gats/UNTrade/data/imports/dataReleaseDates"
    return await client.get_answer(
        path,
        parse=list[UNTradeDataReleaseInfo],
        endpoint="GATSData_GetUNTradeImportDataReleaseInfo",
    )
