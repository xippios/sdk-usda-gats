"""``GET /api/gats/UNTradeExports/reporterCode/{reporterCode}/year/{year}``.

One reporter's exports in one year, as reported by UN Comtrade and served by GATS.
Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetUNTradeExports``: two path parameters, ``reporterCode`` and ``year``, both
typed ``string`` and neither described; the response typed only as ``object``. Upstream:
"Given Reporter Code (Ex IN for India), and Export Year (for ex, 2010), this API End point
returns a list of records of Commodity Export data as reported by UN COMTrade for a given
year. UN COMTrade reports data on a yearly basis at a HS6 Code Level." The record shape is
the recorded one (``models.UNTradeRecord``), one record per partner and HS6 code: one
answer is one reporter-year across all partners and products, never paged or sliced
(3,980 records, about 885 KB of JSON, for Iceland in 2019, and about 17 MB for India in
2016, as the note "One UN Trade answer is a reporter's whole year" of
``docs/upstream/OBSERVED.md`` has it). The codes in it are GATS's, never UN Comtrade's.

An unknown reporter code, a year without a release record for any reporter and a year the
release lists do not hold for the reporter all answer HTTP 200 with ``[]``, and a year that
is not a number HTTP 404 with an empty body, which core's status mapping raises as
``NotFoundError``: the notes of ``docs/upstream/OBSERVED.md`` under "Empty answers and
refusals", with their fixtures.
"""

from urllib.parse import quote

from xippios.core import Answer

from xippios.usda.gats._client import client
from xippios.usda.gats.models import UNTradeRecord

__all__ = ["get_un_trade_exports"]


async def get_un_trade_exports(reporter_code: str, year: str) -> Answer[list[UNTradeRecord]]:
    """Call ``GATSData_GetUNTradeExports``.

    Args:
        reporter_code: ``reporterCode``, a GATS country code, e.g. ``"IC"`` (Iceland),
            ``"IN"`` (India, upstream's example).
        year: ``year``, text as the snapshot types it, four digits, e.g. ``"2019"``;
            upstream's example is 2010.

    Returns:
        Core's ``Answer``: as ``payload`` one ``UNTradeRecord`` per partner and HS6 code, in
        upstream order; ``[]`` when upstream has none,
        and as ``retrieved_at`` the time the answer arrived, timezone-aware UTC.

    Raises:
        NotFoundError: Upstream answered HTTP 404 (recorded for the year ``"abc"``).
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/gats/UNTradeExports/reporterCode/{quote(reporter_code, safe='')}"
        f"/year/{quote(year, safe='')}"
    )
    return await client.get_answer(
        path, parse=list[UNTradeRecord], endpoint="GATSData_GetUNTradeExports"
    )
