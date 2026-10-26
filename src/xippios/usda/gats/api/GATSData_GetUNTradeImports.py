"""``GET /api/gats/UNTradeImports/reporterCode/{reporterCode}/year/{year}``.

One reporter's imports in one year, as reported by UN Comtrade and served by GATS.
Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetUNTradeImports``: two path parameters, ``reporterCode`` and ``year``, both
typed ``string`` and neither described; the response typed only as ``object``. Upstream:
"Given Reporter Code (Ex IN for India), and Import Year (for ex, 2010), this API End point
returns a list of records of Commodity Import data as reported by UN COMTrade for a given
year. UN COMTrade reports data on a yearly basis at a HS6 Code Level." The record is
``models.UNTradeRecord``: the recorded answer carries the exports' eleven fields in their
order and nothing else, so the exports' model is reused rather than copied
(``tests/fixtures/GATSData_GetUNTradeImports/TP_2019.json``, 2,377 records, about 525 KB of
JSON, for Sao Tome and Principe in 2019; Iceland's 2019 imports, 23,396 records and about
5.2 MB, were recorded on 2026-10-26 and not committed). One answer is one reporter-year
across all partners and products, never paged. Error shapes are mapped once in
``xippios.usda.gats._client.classify``; the probes recorded for
``GATSData_GetUNTradeExports`` were not repeated here.
"""

from urllib.parse import quote

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import UNTradeRecord

__all__ = ["GATSData_GetUNTradeImports"]


async def GATSData_GetUNTradeImports(reporter_code: str, year: str) -> list[UNTradeRecord]:
    """Call ``GATSData_GetUNTradeImports``.

    Args:
        reporter_code: ``reporterCode``, a GATS country code, e.g. ``"TP"`` (Sao Tome and
            Principe), ``"IN"`` (India, upstream's example).
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
        f"/api/gats/UNTradeImports/reporterCode/{quote(reporter_code, safe='')}"
        f"/year/{quote(year, safe='')}"
    )
    raw = await client.get_json(path)
    return parse(list[UNTradeRecord], raw, source=SOURCE, endpoint="GATSData_GetUNTradeImports")
