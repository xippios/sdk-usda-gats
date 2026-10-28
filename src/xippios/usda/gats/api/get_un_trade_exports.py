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
(3,980 records, about 885 KB of JSON, for Iceland in 2019; 75,919 records, about 17 MB,
for India in 2016, recorded on 2026-10-26 and not kept). The codes in it are GATS's,
never UN Comtrade's.

Recorded answers (2026-10-26): an unknown reporter code (``ZZ``, 2019), a year without a
release record for any reporter (2035) and the year after the release lists' latest
(Iceland, 2020) all answer HTTP 200 with ``[]`` (``unknown_reporter``, ``future_year``,
``unreleased_year``); a year that is not a number (``abc``) answers HTTP 404 with an empty
``text/plain`` body (``year_text``), which core's status mapping raises as
``NotFoundError``.
"""

from urllib.parse import quote

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import UNTradeRecord

__all__ = ["get_un_trade_exports"]


async def get_un_trade_exports(reporter_code: str, year: str) -> list[UNTradeRecord]:
    """Call ``GATSData_GetUNTradeExports``.

    Args:
        reporter_code: ``reporterCode``, a GATS country code, e.g. ``"IC"`` (Iceland),
            ``"IN"`` (India, upstream's example).
        year: ``year``, text as the snapshot types it, four digits, e.g. ``"2019"``;
            upstream's example is 2010.

    Returns:
        One ``UNTradeRecord`` per partner and HS6 code, in upstream order; ``[]`` when
        upstream has none.

    Raises:
        NotFoundError: Upstream answered HTTP 404 (recorded for the year ``"abc"``).
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/gats/UNTradeExports/reporterCode/{quote(reporter_code, safe='')}"
        f"/year/{quote(year, safe='')}"
    )
    raw = await client.get_json(path)
    return parse(list[UNTradeRecord], raw, source=SOURCE, endpoint="GATSData_GetUNTradeExports")
