"""``GET /api/gats/commodities``: every HS10 commodity code with its units of measure.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCommodities``: no parameters, the response typed only as ``object``.
Upstream: "Returns a set of records with Commodity Information. Commodity record contains
HS10 Code and Census and FAS Unit Of Measure IDS. Please see UnitsOfMeasure end point for
Units of measure description." The record shape is the one recorded on 2026-10-26
(``models.Commodity``): one answer, never paged, 24,936 records and about 7.6 MB of JSON,
the largest answer in the family so far, committed whole as
``tests/fixtures/get_commodities/all.json`` (8,383,278 bytes). Error shapes are
mapped once in ``xippios.usda.gats._client.classify``.

The client caches this path for a day (``_client.COMMODITIES_TTL``), so the wrapper reads
it with ``client.get_answer``, whose ``retrieved_at`` ``tasks.list_commodities``
reports as ``meta.retrieved_at``: on a cache hit the time the entry was stored, else the
time the answer arrived (conventions §4, ADR-0015).

Parsing the 24,936 records into models takes longer than the search after it, so the
wrapper keeps the records it parsed beside the cache entry they came from, one slot: an
answer from the entry the slot holds returns the same records, an answer from another
entry, or from none, is parsed and replaces the slot. The slot holds the entry itself
and compares it by identity: a new entry is a new object, whether the day's entry
expired, the cache was cleared (core's test plugin clears it around every offline test)
or the answer was too large to store, so a slot never answers for another entry and
nothing clears it by hand. The slot keeps the parsed records (about 32 MB for the 24,936
models, measured with ``tracemalloc``) and the entry's 7.6 MB body alive until the next
call replaces them, also after the cache's entry has expired or been cleared.
"""

from datetime import datetime
from typing import NamedTuple

import httpx
from xippios.core import parse
from xippios.core.client import CachedResponse, cache_key

from xippios.usda.gats._client import BASE_URL, COMMODITIES_PATH, SOURCE, cache, client
from xippios.usda.gats.models import Commodity

__all__ = ["get_commodities"]

_KEY = cache_key("GET", httpx.URL(f"{BASE_URL}{COMMODITIES_PATH}"))
"""The client's cache key of the commodities answer (``_client.PathCaches``)."""


class _Parsed(NamedTuple):
    """The records parsed from one cached answer, and the cache entry they came from."""

    entry: CachedResponse
    records: list[Commodity]


_parsed: _Parsed | None = None
"""The one slot: the last records parsed from a cached answer, or ``None``."""


async def get_commodities() -> tuple[list[Commodity], datetime]:
    """Call ``GATSData_GetCommodities``.

    The records are parsed once per cache entry: within the day the client keeps the
    answer, every call after the first returns the same list (see the module docstring).

    Returns:
        Every commodity record, current and historical, in upstream order (by code), one
        ``Commodity`` per record, e.g.
            ``Commodity(hs10_code="0103910000", start_date="198901", end_dtate=None,
            product_type="X", commodity_name="SWINE,<50KG EACH",
            commodity_description="SWINE, LIVE, NESOI, WEIGHING LESS THAN 50 KG EACH  (NO)",
            is_ag_commodity=False, census_uom_id1=78, census_uom_id2=78,
            fas_converted_uom_id=78, fas_non_converted_uom_id=78)``,
        and when it was retrieved, timezone-aware UTC: on a cache hit the time the
        entry was stored, else the time the answer arrived. The list is shared by the
        calls answered from the same entry: a caller that changes it copies it first.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    global _parsed
    answer = await client.get_answer(COMMODITIES_PATH)
    # The entry the answer came from, or the one the client has just stored it as: no
    # await lies between the client's lookup or store and this one.
    entry = cache.get(_KEY)
    held = _parsed
    if held is not None and entry is not None and held.entry is entry:
        return held.records, answer.retrieved_at
    records = parse(
        list[Commodity],
        answer.payload,
        source=SOURCE,
        endpoint="GATSData_GetCommodities",
    )
    _parsed = None if entry is None else _Parsed(entry, records)
    return records, answer.retrieved_at
