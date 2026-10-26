"""``GET /api/gats/UNTradeReExports/reporterCode/{reporterCode}/year/{year}``.

One reporter's re-exports in one year, as reported by UN Comtrade and served by GATS.
Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetUNTradeReExports``: two path parameters, ``reporterCode`` and ``year``, both
typed ``string`` and neither described; the response typed only as ``object``. Upstream:
"Given Reporter Code (Ex IN for India), and Export Year (for ex, 2010), this API End point
returns a list of records of Commodity Re-Export data as reported by UN COMTrade for a
given year. UN COMTrade reports data on a yearly basis at a HS6 Code Level." The record is
``models.UNTradeRecord``: the recorded answer carries the exports' eleven fields in their
order and nothing else, so the exports' model is reused rather than copied
(``tests/fixtures/GATSData_GetUNTradeReExports/MC_2019.json``, 421 records, about 92 KB of
JSON, for Macau in 2019). Iceland, which has 2019 exports and imports, answers ``[]`` for
2019 (``IC_2019``). Re-exports have no release-date operation in the snapshot. One answer
is one reporter-year across all partners and products, never paged. Error shapes are
mapped once in ``xippios.usda.gats._client.classify``; the probes recorded for
``GATSData_GetUNTradeExports`` were not repeated here.
"""

from urllib.parse import quote

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import UNTradeRecord

__all__ = ["GATSData_GetUNTradeReExports"]


async def GATSData_GetUNTradeReExports(reporter_code: str, year: str) -> list[UNTradeRecord]:
    """Call ``GATSData_GetUNTradeReExports``.

    Args:
        reporter_code: ``reporterCode``, a GATS country code, e.g. ``"MC"`` (Macau),
            ``"IN"`` (India, upstream's example).
        year: ``year``, text as the snapshot types it, four digits, e.g. ``"2019"``;
            upstream's example is 2010.

    Returns:
        One ``UNTradeRecord`` per partner and HS6 code, in upstream order; ``[]`` when
        upstream has none.

    Raises:
        NotFoundError: Upstream answered HTTP 404.
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    path = (
        f"/api/gats/UNTradeReExports/reporterCode/{quote(reporter_code, safe='')}"
        f"/year/{quote(year, safe='')}"
    )
    raw = await client.get_json(path)
    return parse(list[UNTradeRecord], raw, source=SOURCE, endpoint="GATSData_GetUNTradeReExports")
