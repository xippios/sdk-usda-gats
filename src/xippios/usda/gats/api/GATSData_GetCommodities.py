"""``GET /api/gats/commodities``: every HS10 commodity code with its units of measure.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetCommodities``: no parameters, the response typed only as ``object``.
Upstream: "Returns a set of records with Commodity Information. Commodity record contains
HS10 Code and Census and FAS Unit Of Measure IDS. Please see UnitsOfMeasure end point for
Units of measure description." The record shape is the one recorded on 2026-10-26
(``models.Commodity``): one answer, never paged, 24,936 records and about 7.6 MB of JSON,
the largest answer in the family so far, committed whole as
``tests/fixtures/GATSData_GetCommodities/all.json`` (8,383,278 bytes). Error shapes are
mapped once in ``xippios.usda.gats._client.classify``.

The client caches this path for a day (``_client.COMMODITIES_TTL``), so the wrapper reads
the response, not only its JSON: on a cache hit it also returns when the entry was
stored, which ``tasks.list_commodities`` reports as ``meta.retrieved_at`` (conventions
§4, ADR-0015).
"""

from datetime import datetime

from xippios.core import parse
from xippios.core.client import decode_json

from xippios.usda.gats._client import COMMODITIES_PATH, SOURCE, client, stored_at
from xippios.usda.gats.models import Commodity

__all__ = ["GATSData_GetCommodities"]


async def GATSData_GetCommodities() -> tuple[list[Commodity], datetime | None]:
    """Call ``GATSData_GetCommodities``.

    Returns:
        Every commodity record, current and historical, in upstream order (by code), one
        ``Commodity`` per record, e.g.
            ``Commodity(hs10_code="0103910000", start_date="198901", end_dtate=None,
            product_type="X", commodity_name="SWINE,<50KG EACH",
            commodity_description="SWINE, LIVE, NESOI, WEIGHING LESS THAN 50 KG EACH  (NO)",
            is_ag_commodity=False, census_uom_id1=78, census_uom_id2=78,
            fas_converted_uom_id=78, fas_non_converted_uom_id=78)``,
        and when the client's cache answered, the time the entry was stored (UTC);
        ``None`` for an answer from the wire.

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    response = await client.get(COMMODITIES_PATH)
    records = parse(
        list[Commodity],
        decode_json(response, source=SOURCE, path=COMMODITIES_PATH),
        source=SOURCE,
        endpoint="GATSData_GetCommodities",
    )
    return records, stored_at(response)
