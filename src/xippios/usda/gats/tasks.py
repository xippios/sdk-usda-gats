"""Task-shaped functions for USDA FAS Global Agricultural Trade System.

The public API (ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register
exactly what is named there.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.

The Census data tasks, ``get_census_exports`` and ``get_census_imports``, answer one
partner and one month across every HS10 product, as one upstream call returns it; never
paged, never sliced upstream. Before that call they check the arguments (``params``)
and fetch the flow's release list, which the client caches for an hour
(``_client.CACHED_PATHS``): GATS answers a month it has not released with ``[]``, the
same as a partner without trade (``future_month.json`` and ``no_data_valid_partner.json``
under ``tests/fixtures/GATSData_GetCensusExports/``), so a month the list lacks is
refused as ``NotFoundError`` naming the months it holds. An empty list for a listed
partner in a released month is a successful empty result. ``hs10_code`` keeps the
records whose code starts with it, after the one data call; nothing else is selected,
ordered or changed.

Release metadata. ``meta.vintage`` of a data task is the statistical month as the
records name it in ``date``, six digits (``"202608"``); every recorded record carries the
requested month there, so it is set for an empty result too. The figures are the latest
revision GATS holds for that month: upstream says "Census reports data on a monthly
basis with corrections applied once a year", and the release list records only the
latest release of each month. ``meta.published_at`` stays ``None`` on every task. The
release record of the month carries a time, ``releaseTimeStamp``
(``2026-10-06T08:00:00`` for 2026-08), but without a time zone, and the snapshot states
none; ``ResultMeta`` takes only a timezone-aware time, and an invented zone could shift
it by hours in an as-of store. sdk-usda-esr and sdk-usda-nass leave theirs empty for the
same reason. ``get_census_release_dates`` returns the time as upstream states it.
``meta.retrieved_at`` of ``get_census_release_dates`` is the time the client's cache
stored the list when the cache answered (conventions §4), else the time of the call.
"""

from collections.abc import Mapping
from datetime import UTC, datetime

from xippios.core import InvalidRequestError, NotFoundError, Result, ResultMeta, sync

from xippios.usda.gats import api
from xippios.usda.gats._client import SOURCE
from xippios.usda.gats.models import CensusExport, CensusImport, DataReleaseInfo, ProductType
from xippios.usda.gats.params import (
    validate_hs10_code,
    validate_month,
    validate_partner_code,
    validate_year,
)

__all__ = ["get_census_exports", "get_census_imports", "get_census_release_dates"]

HS10_NOTE = "filter by hs10_code, a full code or a prefix such as the chapter '02', to see the rest"
"""What a cut Census data result tells the agent: the one filter the tools have."""

try:
    from xippios.core.mcp import ResultCap
except ImportError:  # pragma: no cover - a base install, without the mcp extra, has no server
    MCP_CAPS: "Mapping[str, ResultCap]" = {}
else:
    MCP_CAPS = {
        "get_census_exports": ResultCap(note=HS10_NOTE),
        "get_census_imports": ResultCap(note=HS10_NOTE),
    }
"""MCP result caps of their own, by task function name (conventions §8, ADR-0016).

The Census data tools keep the family's bounds, 200 rows or 64 KB, with a note of their
own: a tool with a filter names it (§8). One partner-month is one record per HS10 code,
777 records and about 154 KB of JSON for exports to China in August 2026, 3,294 records
and about 1.1 MB for imports from China; ``hs10_code`` narrows it to a chapter, a heading
or one product. ``get_census_release_dates`` keeps the default and its note: 716 months,
newest first, of which the newest 200 arrive. ``ResultCap`` lives in ``xippios.core.mcp``,
which needs the ``mcp`` extra, so a base install, which serves no MCP tool, has no caps.
"""


def _check(partner_code: str, year: int, month: int, hs10_code: str | None) -> None:
    """Every argument of a Census data task, before any call; see ``params``."""
    validate_partner_code(partner_code)
    validate_year(year)
    validate_month(month)
    if hs10_code is not None:
        validate_hs10_code(hs10_code)


def _released(
    month_code: str,
    releases: list[DataReleaseInfo],
    stored: datetime | None,
    flow: str,
    operation: str,
) -> None:
    """Raise ``NotFoundError`` unless ``month_code`` is in the flow's release list.

    Args:
        month_code: The requested month as six digits, e.g. ``"203501"``.
        releases: The flow's release list, one record per released month.
        stored: When the client's cache stored the list, or ``None`` if fetched now.
        flow: ``"exports"`` or ``"imports"``, for the message.
        operation: The release-date operation, for the message.
    """
    months = {release.statistical_year_month for release in releases}
    if month_code in months:
        return
    when = (
        f" The release list was fetched at {stored:%Y-%m-%d %H:%M} UTC and is kept for an "
        "hour; a month released since then is refused until it is fetched again."
        if stored is not None
        else ""
    )
    if not months:
        reason = f"{operation} answered with no released month"
    else:
        earliest, latest = min(months), max(months)
        if month_code > latest:
            reason = f"it is not released yet: the latest {flow} month released is {latest}"
        elif month_code < earliest:
            reason = f"the {flow} data starts at {earliest}"
        else:
            reason = f"{operation} lists no release for it"
        reason += f" ({operation} lists {len(months)} months, {earliest} to {latest})"
    raise NotFoundError(
        f"GATS has no Census {flow} for {month_code}: {reason}. GATS answers a month it has "
        f"not released with an empty list, so the package checks the release list first.{when}",
        source=SOURCE,
    )


def _matching[R: (CensusExport, CensusImport)](records: list[R], hs10_code: str | None) -> list[R]:
    """The records whose ``hs10_code`` starts with ``hs10_code``, in upstream order."""
    if hs10_code is None:
        return records
    return [record for record in records if record.hs10_code.startswith(hs10_code)]


def _data_meta(
    endpoint: str, partner_code: str, year: int, month: int, hs10_code: str | None
) -> ResultMeta:
    """``ResultMeta`` of a Census data task: ``vintage`` the month, ``published_at`` empty."""
    return ResultMeta(
        source=SOURCE,
        endpoint=endpoint,
        vintage=f"{year:04d}{month:02d}",
        request={
            "partner_code": partner_code,
            "year": year,
            "month": month,
            "hs10_code": hs10_code,
        },
    )


async def get_census_exports_async(
    partner_code: str, year: int, month: int, hs10_code: str | None = None
) -> Result[list[CensusExport]]:
    """US exports to one partner in one month by HS10 product, as the US Census Bureau reported.

    One record per HS10 code exported that month, as upstream sends it: ``value`` (the
    snapshot names no currency), ``quantity1`` and ``quantity2`` with four unit-of-measure
    ids; 777 records for China in August 2026. Two requests: the exports release list
    (``GATSData_GetCensusExportDataReleaseInfo``, kept by the client for an hour) to check
    that the month is released, then the month (``GATSData_GetCensusExports``). The
    arguments are checked before either: an unknown partner code raises
    ``InvalidRequestError`` naming the closest codes. A month not released yet, or before
    January 1967, raises ``NotFoundError`` naming the months released; a listed partner
    without exports that month gives an empty list. ``meta.vintage`` is the statistical
    month as the records' ``date`` names it (``"202608"``), and the figures are the latest
    revision GATS holds for it, since Census applies corrections once a year.
    ``meta.published_at`` stays empty: upstream gives the month's release time without a
    time zone; ``get_census_release_dates`` returns it as stated. The MCP server returns at
    most 200 rows or 64 KB, so pass ``hs10_code`` there to see a chapter or one product.

    Args:
        partner_code: GATS's two-character country code, not ISO, as
            ``GATSData_GetCountries`` lists it, e.g. ``"CH"`` (China), ``"MX"`` (Mexico),
            ``"CA"`` (Canada), ``"JA"`` (Japan).
        year: Calendar year, four digits, e.g. ``2026``; the data starts in 1967.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text: a full code such as ``"0103910000"`` for one product, or a
            prefix such as ``"02"`` for chapter 02 or ``"0201"`` for a heading. ``None``
            (the default) keeps every product. Applied after the one data request.
    """
    _check(partner_code, year, month, hs10_code)
    releases, stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    _released(
        f"{year:04d}{month:02d}",
        releases,
        stored,
        "exports",
        "GATSData_GetCensusExportDataReleaseInfo",
    )
    records = await api.GATSData_GetCensusExports(partner_code, year, month)
    meta = _data_meta("GATSData_GetCensusExports", partner_code, year, month, hs10_code)
    return Result(data=_matching(records, hs10_code), meta=meta)


async def get_census_imports_async(
    partner_code: str, year: int, month: int, hs10_code: str | None = None
) -> Result[list[CensusImport]]:
    """US imports from one partner in one month by HS10 product, as the US Census Bureau reported.

    One record per HS10 code imported that month, as upstream sends it: every field of
    an export record (``value``, ``quantity1``, ``quantity2``, four unit-of-measure ids)
    and five more the snapshot does not document, ``consumption_quantity1``,
    ``consumption_quantity2``, ``consumption_value``, ``consumption_cif_value`` and
    ``cif_value``; 3,294 records for China in August 2026. Two requests: the imports
    release list (``GATSData_GetCensusImportDataReleaseInfo``, kept by the client for an
    hour) to check that the month is released, then the month
    (``GATSData_GetCensusImport``). The arguments are checked before either: an unknown
    partner code raises ``InvalidRequestError`` naming the closest codes. A month not
    released yet, or before January 1967, raises ``NotFoundError`` naming the months
    released; a listed partner without imports that month gives an empty list.
    ``meta.vintage`` is the statistical month as the records' ``date`` names it
    (``"202608"``), and the figures are the latest revision GATS holds for it, since
    Census applies corrections once a year. ``meta.published_at`` stays empty: upstream
    gives the month's release time without a time zone; ``get_census_release_dates``
    returns it as stated. The MCP server returns at most 200 rows or 64 KB, so pass
    ``hs10_code`` there to see a chapter or one product.

    Args:
        partner_code: GATS's two-character country code, not ISO, as
            ``GATSData_GetCountries`` lists it, e.g. ``"CH"`` (China), ``"MX"`` (Mexico),
            ``"CA"`` (Canada), ``"JA"`` (Japan).
        year: Calendar year, four digits, e.g. ``2026``; the data starts in 1967.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text: a full code such as ``"0106199195"`` for one product, or a
            prefix such as ``"02"`` for chapter 02 or ``"0201"`` for a heading. ``None``
            (the default) keeps every product. Applied after the one data request.
    """
    _check(partner_code, year, month, hs10_code)
    releases, stored = await api.GATSData_GetCensusImportDataReleaseInfo()
    _released(
        f"{year:04d}{month:02d}",
        releases,
        stored,
        "imports",
        "GATSData_GetCensusImportDataReleaseInfo",
    )
    records = await api.GATSData_GetCensusImport(partner_code, year, month)
    meta = _data_meta("GATSData_GetCensusImport", partner_code, year, month, hs10_code)
    return Result(data=_matching(records, hs10_code), meta=meta)


async def get_census_release_dates_async(
    product_type: ProductType,
) -> Result[list[DataReleaseInfo]]:
    """When GATS last released each month of US Census exports or imports: poll for releases.

    One record per statistical month, newest first, from ``"196701"`` to the latest
    released (``"202608"`` on 2026-10-25), 716 months: ``statistical_year_month`` and
    ``release_time_stamp``, the time of the month's latest release, as upstream states it,
    without a time zone (``2026-10-06T08:00:00`` for 2026-08). A month the annual
    revision corrected carries the revision's time: 2023-01 to 2025-12 read
    ``2026-06-24T08:00:00``. Compare it with a stored one to fetch only the months that
    changed. One request, kept by the client for an hour; ``meta.retrieved_at`` is when
    it was fetched. ``meta.published_at`` and ``meta.vintage`` stay empty. The MCP server
    returns the newest 200 months.

    Args:
        product_type: Which list, by upstream's ``productType`` code: ``"X"`` exports
            (``GATSData_GetCensusExportDataReleaseInfo``), ``"M"`` imports
            (``GATSData_GetCensusImportDataReleaseInfo``).
    """
    try:
        code = ProductType(product_type)
    except (ValueError, TypeError):
        raise InvalidRequestError(
            f'product_type must be "X" (exports) or "M" (imports), upstream\'s productType '
            f"codes, got {product_type!r}.",
            source=SOURCE,
        ) from None
    if code is ProductType.X:
        endpoint = "GATSData_GetCensusExportDataReleaseInfo"
        releases, stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    else:
        endpoint = "GATSData_GetCensusImportDataReleaseInfo"
        releases, stored = await api.GATSData_GetCensusImportDataReleaseInfo()
    meta = ResultMeta(
        source=SOURCE,
        endpoint=endpoint,
        retrieved_at=stored or datetime.now(UTC),
        request={"product_type": code.value},
    )
    return Result(data=releases, meta=meta)


get_census_exports = sync(get_census_exports_async)
get_census_imports = sync(get_census_imports_async)
get_census_release_dates = sync(get_census_release_dates_async)
