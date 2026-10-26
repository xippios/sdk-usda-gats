"""``GET /api/gats/unitsOfMeasure``: every unit-of-measure id with its code and name.

Reference: ``docs/upstream/openapi/portal-document.json``, operation
``GATSData_GetUnitsOfMeasure``: no parameters, the response typed only as ``object``.
Upstream: "Returns a set of records with Units of Measure. Use this to match against
Units Of Measure IDs in the Import and Export records to get the name of the Unit of
Measure". The record shape is the recorded one,
``tests/fixtures/GATSData_GetUnitsOfMeasure/all.json`` (108 records, about 14 KB of
JSON), parsed into ``models.UnitOfMeasure``; its ``unitOfMeasureId`` is what
``censusUOMId1`` and the other unit fields of the commodity and data records hold. Error
shapes are mapped once in ``xippios.usda.gats._client.classify``.
"""

from xippios.core import parse

from xippios.usda.gats._client import SOURCE, client
from xippios.usda.gats.models import UnitOfMeasure

__all__ = ["GATSData_GetUnitsOfMeasure"]


async def GATSData_GetUnitsOfMeasure() -> list[UnitOfMeasure]:
    """Call ``GATSData_GetUnitsOfMeasure``.

    Returns:
        Every unit of measure, in upstream order (by id), one ``UnitOfMeasure`` per
        record, e.g.
            ``UnitOfMeasure(unit_of_measure_id=47, unit_of_measure_code="KG",
            unit_of_measure_name="Kilograms", unit_of_measure_description="Kilograms")``

    Raises:
        AuthError: api.data.gov refused the key in ``DATA_GOV_API_KEY``.
        RateLimitError: api.data.gov's hourly quota for the key is spent.
    """
    raw = await client.get_json("/api/gats/unitsOfMeasure")
    return parse(list[UnitOfMeasure], raw, source=SOURCE, endpoint="GATSData_GetUnitsOfMeasure")
