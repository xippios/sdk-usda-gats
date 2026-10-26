"""Task-shaped functions for USDA FAS Global Agricultural Trade System.

The public API (ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register
exactly what is named there.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.

The six Census data tasks, ``get_census_exports``, ``get_census_imports`` and
``get_census_reexports``, and ``get_customs_district_exports``,
``get_customs_district_imports`` and ``get_customs_district_reexports`` by US customs
district, answer one partner and one month across every HS10 product (and district), as
one upstream call returns it; never paged, never sliced upstream. Before that call they
check the arguments (``params``) and fetch a release list, which the client caches for
an hour (``_client.RELEASE_DATES_PATHS``): GATS answers a month it has not released with
``[]``, the same as a partner without trade (``future_month.json`` and
``no_data_valid_partner.json`` under ``tests/fixtures/GATSData_GetCensusExports/``), so
a month the list lacks is refused as ``NotFoundError`` naming the months it holds. The
imports forms check the imports list (``GATSData_GetCensusImportDataReleaseInfo``); the
exports forms and, by assumption, the re-exports forms check the exports list
(``GATSData_GetCensusExportDataReleaseInfo``): upstream publishes no re-export release
list, and every HS10 code of the recorded re-export answers is listed under ``"X"`` in
``GATSData_GetCommodities``. An empty list for a listed partner in a released month is a
successful empty result. ``hs10_code`` keeps the records whose code starts with it, and
``customs_district_id`` the records of one district, after the one data call; nothing
else is selected, ordered or changed.

Release metadata. ``meta.vintage`` of a data task is ``releaseTimeStamp`` of the
month's record in its release list, as upstream states it (``"2026-10-06T08:00:00"`` for
2026-08): upstream's identifier of the release that last revised the month's figures
(conventions §4), set for an empty result too. Upstream says "Census reports data on a
monthly basis with corrections applied once a year", and the list records only each
month's latest release: the annual revision re-released 2023-01 to 2025-12 at
``2026-06-24T08:00:00``. The model keeps the time naive, and ``isoformat()`` gives back
upstream's text for every recorded time. The statistical month stays in
``meta.request`` (``year``, ``month``) and on every record's ``date`` (``"202608"``).
For up to ``_client.RELEASE_DATES_TTL``, an hour, after a release the cached list may
still give a revised month the previous release's time, an accepted lag; a month
released in that hour is refused, and the refusal says when the list was fetched.
``meta.published_at`` stays ``None`` on every task: ``ResultMeta`` takes only a
timezone-aware time, FAS states no zone for its time stamps, and an invented zone could
shift them by hours in an as-of store. sdk-usda-esr and sdk-usda-nass leave theirs empty
for the same reason. ``get_census_release_dates`` returns every month's time as upstream
states it and leaves ``vintage`` empty; its ``meta.retrieved_at`` is the time the
client's cache stored the list when the cache answered (conventions §4), else the time
of the call.

The ``list_*`` tasks but one answer from the five lists packaged under ``reference/`` and
make no upstream call (sdk-usda-psd's shape): ``meta.endpoint`` is the operation the list
was fetched from (``"GATSData_GetCountries"``), ``meta.retrieved_at`` is when the task
answered, and ``meta.vintage`` is the day the package fetched the list (``"2026-10-26"``,
UTC), the ``fetched`` date as the file stores it: upstream gives these lists no version
identifier. ``list_commodities`` is the exception: the HS10 list, 24,936 records and
7.6 MB, is not packaged, so it makes one live request (``GATSData_GetCommodities``),
which the client keeps for a day (``_client.COMMODITIES_TTL``); its ``meta.retrieved_at``
is when the list was fetched, from the cache's stored time on a hit, and ``vintage``
stays empty. The lists' filters (``search``, ``region_code``, ``hs10_code``,
``product_type``) only select records, which keep upstream's order and values;
``meta.request`` carries them, ``None`` when not given. ``meta.total`` stays unset:
upstream reports no count.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from xippios.core import InvalidRequestError, NotFoundError, Result, ResultMeta, parse, sync

from xippios.usda.gats import api
from xippios.usda.gats._client import SOURCE
from xippios.usda.gats.models import (
    CensusExport,
    CensusImport,
    Commodity,
    Country,
    CustomsDistrict,
    CustomsDistrictExport,
    CustomsDistrictImport,
    DataReleaseInfo,
    HS6Commodity,
    ProductType,
    Region,
    UnitOfMeasure,
)
from xippios.usda.gats.params import (
    PackagedList,
    packaged_values,
    validate_customs_district_id,
    validate_hs10_code,
    validate_partner_month,
)

__all__ = [
    "get_census_exports",
    "get_census_imports",
    "get_census_reexports",
    "get_census_release_dates",
    "get_customs_district_exports",
    "get_customs_district_imports",
    "get_customs_district_reexports",
    "list_commodities",
    "list_countries",
    "list_customs_districts",
    "list_hs6_commodities",
    "list_regions",
    "list_units_of_measure",
]

HS10_NOTE = "filter by hs10_code, a full code or a prefix such as the chapter '02', to see the rest"
"""What a cut Census data result tells the agent: the one filter the tools have."""

DISTRICT_NOTE = (
    "filter by hs10_code, a full code or a prefix such as the chapter '02', or by "
    "customs_district_id, e.g. 10 (NEW YORK, N.Y.), to see the rest"
)
"""What a cut customs-district result tells the agent: the two filters the tools have."""

RELEASE_DATES_NOTE = (
    "the list runs newest first, so the rows shown are the latest released months; "
    "200 months reach back more than sixteen years"
)
"""What a cut release-date list tells the agent: which months it got. The tool has no
filter, so the note names none (ADR-0016)."""

COUNTRIES_NOTE = (
    "filter by region_code, e.g. 'R40' (East Asia), or by search on the code, the name or "
    "the ISO or GENC code to see the rest"
)
"""What a cut countries list would tell the agent: its two filters. The cap of its own
lets the 322 packaged codes through whole, so only a list grown past it is cut."""

HS6_NOTE = (
    "filter by search, on the code, the name and the description, e.g. '0201' or "
    "'wheat', to see the rest"
)
"""What the cut HS6 list tells the agent: the one filter the tool has."""

COMMODITIES_NOTE = (
    "filter by search (name or description, e.g. 'wheat'), by hs10_code (a code or a "
    "prefix such as '0201') or by product_type ('X' exports, 'M' imports) to see the rest"
)
"""What the cut HS10 list tells the agent: the three filters the tool has."""

try:
    from xippios.core.mcp import ResultCap
except ImportError:  # pragma: no cover - a base install, without the mcp extra, has no server
    MCP_CAPS: "Mapping[str, ResultCap]" = {}
else:
    MCP_CAPS = {
        "get_census_exports": ResultCap(note=HS10_NOTE),
        "get_census_imports": ResultCap(note=HS10_NOTE),
        "get_census_reexports": ResultCap(note=HS10_NOTE),
        "get_census_release_dates": ResultCap(note=RELEASE_DATES_NOTE),
        "get_customs_district_exports": ResultCap(note=DISTRICT_NOTE),
        "get_customs_district_imports": ResultCap(note=DISTRICT_NOTE),
        "get_customs_district_reexports": ResultCap(note=DISTRICT_NOTE),
        "list_commodities": ResultCap(note=COMMODITIES_NOTE),
        "list_countries": ResultCap(max_rows=400, max_bytes=100_000, note=COUNTRIES_NOTE),
        "list_hs6_commodities": ResultCap(note=HS6_NOTE),
    }
"""MCP result caps of their own, by task function name (conventions §8, ADR-0016).

The Census data tools keep the family's bounds, 200 rows or 64 KB, with a note of their
own: a tool with a filter names it (§8). One partner-month is one record per HS10 code,
777 records and about 154 KB of JSON for exports to China in August 2026, 3,294 records
and about 1.1 MB for imports from China; ``hs10_code`` narrows it to a chapter, a heading
or one product. By customs district it is one record per district and code, 1,697
records for exports to China, so those notes name ``customs_district_id`` as well.
``get_census_release_dates`` keeps the default bounds with a note of its own,
``RELEASE_DATES_NOTE``: 716 months, newest first, of which the newest 200 arrive, 202608
back to 201001 as recorded, 16 years and 8 months; the tool has no filter, so the note
names none. ``list_countries`` is a reference list an agent needs whole: 322 codes,
past the default 200 rows, and about 57 KB of compact JSON, so its cap of 400 rows or
100,000 bytes lets it through whole, with a note naming its filters for a list that
outgrows it. ``list_hs6_commodities`` (2,909 codes, about 0.7 MB) and
``list_commodities`` (24,936 records, about 7 MB) are too large to serve whole: they keep
the default bounds with notes naming their filters. ``list_regions`` (15),
``list_units_of_measure`` (108) and ``list_customs_districts`` (53) fit the default.
``ResultCap`` lives in ``xippios.core.mcp``, which needs the ``mcp`` extra, so a base
install, which serves no MCP tool, has no caps.
"""


class _Coded(Protocol):
    """A Census record: its HS10 code."""

    @property
    def hs10_code(self) -> str: ...


class _Districted(Protocol):
    """A customs-district record: its district id."""

    @property
    def customs_district_id(self) -> int: ...


RELEASE_LISTS: dict[ProductType, tuple[str, str]] = {
    ProductType.X: ("exports", "GATSData_GetCensusExportDataReleaseInfo"),
    ProductType.M: ("imports", "GATSData_GetCensusImportDataReleaseInfo"),
}
"""The release list of each ``productType``: its flow and its operation."""


def _check(
    partner_code: str,
    year: int,
    month: int,
    hs10_code: str | None,
    customs_district_id: int | None = None,
) -> None:
    """Every argument of a Census data task, before any call; see ``params``."""
    validate_partner_month(partner_code, year, month)
    if hs10_code is not None:
        validate_hs10_code(hs10_code)
    if customs_district_id is not None:
        validate_customs_district_id(customs_district_id)


def _release_of(
    month_code: str,
    releases: list[DataReleaseInfo],
    stored: datetime | None,
    flow: str,
    operation: str,
    data: str | None = None,
) -> DataReleaseInfo:
    """The record of ``month_code`` in the flow's release list, else ``NotFoundError``.

    Args:
        month_code: The requested month as six digits, e.g. ``"203501"``.
        releases: The flow's release list, one record per released month.
        stored: When the client's cache stored the list, or ``None`` if fetched now.
        flow: ``"exports"`` or ``"imports"``, the list's flow, for the message.
        operation: The release-date operation, for the message.
        data: What was asked for, e.g. ``"re-exports"``, ``"customs-district imports"``;
            ``None`` for the flow itself.

    Raises:
        NotFoundError: The list has no record for ``month_code``: not released yet, or
            before the data starts.
    """
    release = next((r for r in releases if r.statistical_year_month == month_code), None)
    if release is not None:
        return release
    asked = data or flow
    months = {record.statistical_year_month for record in releases}
    when = (
        f" The release list was fetched at {stored:%Y-%m-%d %H:%M} UTC and is kept for an "
        "hour; a month released since then is refused until it is fetched again."
        if stored is not None
        else ""
    )
    own = (
        f" GATS publishes no release list for {asked}: the package checks the {flow} list."
        if asked != flow
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
        f"GATS has no Census {asked} for {month_code}: {reason}. GATS answers a month it has "
        f"not released with an empty list, so the package checks the release list first."
        f"{own}{when}",
        source=SOURCE,
    )


async def _release(
    product_type: ProductType, year: int, month: int, data: str | None = None
) -> DataReleaseInfo:
    """The month's record in the release list of ``product_type``; see ``_release_of``.

    The list comes from the client's cache when it holds it; ``data`` names what was
    asked for in the refusal, e.g. ``"re-exports"``.
    """
    if product_type is ProductType.X:
        releases, stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    else:
        releases, stored = await api.GATSData_GetCensusImportDataReleaseInfo()
    flow, operation = RELEASE_LISTS[product_type]
    return _release_of(f"{year:04d}{month:02d}", releases, stored, flow, operation, data)


def _matching[R: _Coded](records: list[R], hs10_code: str | None) -> list[R]:
    """The records whose ``hs10_code`` starts with ``hs10_code``, in upstream order."""
    if hs10_code is None:
        return records
    return [record for record in records if record.hs10_code.startswith(hs10_code)]


def _in_district[R: _Districted](records: list[R], customs_district_id: int | None) -> list[R]:
    """The records of the district ``customs_district_id``, in upstream order."""
    if customs_district_id is None:
        return records
    return [record for record in records if record.customs_district_id == customs_district_id]


def _data_meta(
    endpoint: str,
    release: DataReleaseInfo,
    partner_code: str,
    year: int,
    month: int,
    hs10_code: str | None,
    **filters: int | None,
) -> ResultMeta:
    """``ResultMeta`` of a Census data task: ``vintage`` the month's release time.

    ``vintage`` is the release record's ``releaseTimeStamp`` as upstream states it: the
    model keeps the time naive, and ``isoformat()`` gives back upstream's text,
    ``"2026-10-06T08:00:00"`` for 2026-08. ``published_at`` stays ``None``: ``ResultMeta``
    takes only a zone-aware time, and FAS states no zone. ``filters`` are the task's
    other filters, e.g. ``customs_district_id``, recorded in ``meta.request`` after
    ``hs10_code``.
    """
    return ResultMeta(
        source=SOURCE,
        endpoint=endpoint,
        vintage=release.release_time_stamp.isoformat(),
        request={
            "partner_code": partner_code,
            "year": year,
            "month": month,
            "hs10_code": hs10_code,
            **filters,
        },
    )


async def get_census_exports_async(
    partner_code: str, year: int, month: int, hs10_code: str | None = None
) -> Result[list[CensusExport]]:
    """US exports to one partner in one month by HS10 product, as the US Census Bureau reported.

    One record per HS10 code exported that month, as upstream sends it: ``value`` (the
    snapshot names no currency), ``quantity1`` and ``quantity2`` with four unit-of-measure
    ids (``list_units_of_measure``); 777 records for China in August 2026. Two requests:
    the exports release list (``GATSData_GetCensusExportDataReleaseInfo``, kept by the
    client for an hour) to check that the month is released, then the month
    (``GATSData_GetCensusExports``). The arguments are checked before either: an unknown
    partner code raises ``InvalidRequestError`` naming up to three close codes with their
    names (``"CHN"`` leads to ``"CH"``), or pointing to ``list_countries`` when none is
    close; a code GATS discontinued before the month (``"SZ"``, Switzerland, after
    198712) is refused naming the listed codes of the same name (``"SR"``). A month not
    released yet, or before January 1967, raises ``NotFoundError`` naming the months
    released; a listed partner without exports that month gives an empty list.
    ``meta.vintage`` is the month's release time from that list, as upstream states it
    (``"2026-10-06T08:00:00"`` for August 2026): the release that last revised the
    figures, since Census applies corrections once a year. For up to an hour after a
    release the cached list may still give the previous release's time, an accepted lag.
    The month itself is in ``meta.request`` and in every record's ``date``
    (``"202608"``). ``meta.published_at`` stays empty: FAS states no time zone, and
    ``ResultMeta`` takes only a zone-aware time. The MCP server returns at most 200 rows
    or 64 KB, so pass ``hs10_code`` there to see a chapter or one product.

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"CH"`` (China), ``"MX"`` (Mexico), ``"CA"`` (Canada),
            ``"JA"`` (Japan).
        year: Calendar year, four digits, e.g. ``2026``; the data starts in 1967.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text: a full code such as ``"0103910000"`` for one product, or a
            prefix such as ``"02"`` for chapter 02 or ``"0201"`` for a heading. ``None``
            (the default) keeps every product. Applied after the one data request.
    """
    _check(partner_code, year, month, hs10_code)
    release = await _release(ProductType.X, year, month)
    records = await api.GATSData_GetCensusExports(partner_code, year, month)
    meta = _data_meta("GATSData_GetCensusExports", release, partner_code, year, month, hs10_code)
    return Result(data=_matching(records, hs10_code), meta=meta)


async def get_census_imports_async(
    partner_code: str, year: int, month: int, hs10_code: str | None = None
) -> Result[list[CensusImport]]:
    """US imports from one partner in one month by HS10 product, as the US Census Bureau reported.

    One record per HS10 code imported that month, as upstream sends it: every field of
    an export record (``value``, ``quantity1``, ``quantity2``, four unit-of-measure ids)
    and five more, ``consumption_quantity1``, ``consumption_quantity2``,
    ``consumption_value``, ``consumption_cif_value`` and ``cif_value``; 3,294 records for
    China in August 2026. Upstream's documentation describes no field of either record:
    every field is as the recorded answers show it. Two requests: the imports release
    list (``GATSData_GetCensusImportDataReleaseInfo``, kept by the client for an hour) to
    check that the month is released, then the month (``GATSData_GetCensusImport``). The
    arguments are checked before either: an unknown partner code raises
    ``InvalidRequestError`` naming up to three close codes with their names (``"CHN"``
    leads to ``"CH"``), or pointing to ``list_countries`` when none is close; a code GATS
    discontinued before the month (``"SZ"``, Switzerland, after 198712) is refused naming
    the listed codes of the same name (``"SR"``). A month not released yet, or before
    January 1967, raises ``NotFoundError`` naming the months released; a listed partner
    without imports that month gives an empty list. ``meta.vintage`` is the month's
    release time from that list, as upstream states it (``"2026-10-06T08:00:00"`` for
    August 2026): the release that last revised the figures, since Census applies
    corrections once a year. For up to an hour after a release the cached list may still
    give the previous release's time, an accepted lag. The month itself is in
    ``meta.request`` and in every record's ``date`` (``"202608"``).
    ``meta.published_at`` stays empty: FAS states no time zone, and ``ResultMeta`` takes
    only a zone-aware time. The MCP server returns at most 200 rows or 64 KB, so pass
    ``hs10_code`` there to see a chapter or one product.

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"CH"`` (China), ``"MX"`` (Mexico), ``"CA"`` (Canada),
            ``"JA"`` (Japan).
        year: Calendar year, four digits, e.g. ``2026``; the data starts in 1967.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text: a full code such as ``"0106199195"`` for one product, or a
            prefix such as ``"02"`` for chapter 02 or ``"0201"`` for a heading. ``None``
            (the default) keeps every product. Applied after the one data request.
    """
    _check(partner_code, year, month, hs10_code)
    release = await _release(ProductType.M, year, month)
    records = await api.GATSData_GetCensusImport(partner_code, year, month)
    meta = _data_meta("GATSData_GetCensusImport", release, partner_code, year, month, hs10_code)
    return Result(data=_matching(records, hs10_code), meta=meta)


async def get_census_reexports_async(
    partner_code: str, year: int, month: int, hs10_code: str | None = None
) -> Result[list[CensusExport]]:
    """US re-exports to one partner in one month by HS10 product, as the US Census Bureau reported.

    Re-exports, in upstream's words, "are all imported commodities from few countries
    into USA, that are ultimately exported out to other countries from USA". One record
    per HS10 code re-exported that month, the same ten fields as an export record
    (``value``, ``quantity1``, ``quantity2``, four unit-of-measure ids); 12 records for
    Iceland (``"IC"``) in August 2026, chapter 62 the largest with four. Two requests:
    the exports release list (``GATSData_GetCensusExportDataReleaseInfo``, kept by the
    client for an hour), then the month (``GATSData_GetCensusReExports``). Upstream
    publishes no re-export release list, so the package checks the exports list, by
    assumption: every HS10 code of the recorded re-exports is an export code (``"X"``) in
    ``list_commodities``. A month the exports list lacks raises ``NotFoundError`` naming
    the months released, and ``meta.vintage`` is that list's release time for the month
    (``"2026-10-06T08:00:00"`` for August 2026), the exports' release, not one the
    re-exports state. The arguments are checked before either request as for
    ``get_census_exports``: an unknown partner code names close codes (``"ISL"`` leads to
    ``"IC"``) or ``list_countries``, a code discontinued before the month is refused. A
    listed partner without re-exports that month gives an empty list. The month is in
    ``meta.request`` and in every record's ``date``; ``meta.published_at`` stays empty.
    The MCP server returns at most 200 rows or 64 KB; pass ``hs10_code`` there to narrow.

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"IC"`` (Iceland), ``"CH"`` (China), ``"MX"`` (Mexico).
        year: Calendar year, four digits, e.g. ``2026``; the data starts in 1967.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text: a full code such as ``"0709202000"`` for one product, or a
            prefix such as ``"62"`` for chapter 62 or ``"4202"`` for a heading. ``None``
            (the default) keeps every product. Applied after the one data request.
    """
    _check(partner_code, year, month, hs10_code)
    release = await _release(ProductType.X, year, month, "re-exports")
    records = await api.GATSData_GetCensusReExports(partner_code, year, month)
    meta = _data_meta("GATSData_GetCensusReExports", release, partner_code, year, month, hs10_code)
    return Result(data=_matching(records, hs10_code), meta=meta)


async def get_customs_district_exports_async(
    partner_code: str,
    year: int,
    month: int,
    hs10_code: str | None = None,
    customs_district_id: int | None = None,
) -> Result[list[CustomsDistrictExport]]:
    """US exports to one partner in one month by US customs district and HS10 product.

    One record per customs district and HS10 code, as the US Census Bureau reported:
    ``customs_district_id`` (``list_customs_districts`` names it) and the ten fields of
    an export record. Over the districts, a code's records add up to its record in
    ``get_census_exports``, as recorded. 107 records in 14 districts for Iceland
    (``"IC"``) in August 2026, 16 of them in district 10 (NEW YORK, N.Y.); 1,697 in 31
    districts for China. Two requests: the exports release list
    (``GATSData_GetCensusExportDataReleaseInfo``, kept by the client for an hour), then the
    month (``GATSData_GetCustomsDistrictsExports``). The arguments are checked before
    either, as for ``get_census_exports``, and ``customs_district_id`` against the
    packaged districts list: an id it lacks raises ``InvalidRequestError`` naming the
    nearest listed ids with their names. A month not released yet raises
    ``NotFoundError``; a listed partner without exports gives an empty list.
    ``meta.vintage`` is the exports list's release time for the month
    (``"2026-10-06T08:00:00"`` for August 2026); ``meta.published_at`` stays empty. The
    MCP server returns at most 200 rows or 64 KB, so pass ``hs10_code`` or
    ``customs_district_id`` there to narrow.

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"IC"`` (Iceland), ``"CH"`` (China), ``"MX"`` (Mexico).
        year: Calendar year, four digits, e.g. ``2026``.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text, e.g. ``"0709202000"`` (one product), ``"21"`` (chapter 21).
            ``None`` (the default) keeps every product.
        customs_district_id: Keep only this US customs district, an id
            ``list_customs_districts`` lists, e.g. ``10`` (NEW YORK, N.Y.), ``1``
            (PORTLAND,MAINE), ``52`` (MIAMI, FLA.). ``None`` (the default) keeps every
            district. Both filters apply after the one data request.
    """
    _check(partner_code, year, month, hs10_code, customs_district_id)
    release = await _release(ProductType.X, year, month, "customs-district exports")
    records = await api.GATSData_GetCustomsDistrictsExports(partner_code, year, month)
    meta = _data_meta(
        "GATSData_GetCustomsDistrictsExports",
        release,
        partner_code,
        year,
        month,
        hs10_code,
        customs_district_id=customs_district_id,
    )
    selected = _in_district(_matching(records, hs10_code), customs_district_id)
    return Result(data=selected, meta=meta)


async def get_customs_district_imports_async(
    partner_code: str,
    year: int,
    month: int,
    hs10_code: str | None = None,
    customs_district_id: int | None = None,
) -> Result[list[CustomsDistrictImport]]:
    """US imports from one partner in one month by US customs district and HS10 product.

    One record per customs district and HS10 code, as the US Census Bureau reported:
    ``customs_district_id`` (``list_customs_districts`` names it) and the fifteen fields
    of an import record, the consumption and CIF fields among them. 123 records in 21
    districts for Iceland (``"IC"``) in August 2026, 51 of them fish fillets
    (``hs10_code`` ``"0304"``), 28 records in district 10 (NEW YORK, N.Y.). Two requests:
    the imports release list (``GATSData_GetCensusImportDataReleaseInfo``, kept by the
    client for an hour), then the month (``GATSData_GetCustomsDistrictsImports``). The
    arguments are checked before either, as for ``get_census_imports``, and
    ``customs_district_id`` against the packaged districts list: an id it lacks raises
    ``InvalidRequestError`` naming the nearest listed ids with their names. A month not
    released yet raises ``NotFoundError``; a listed partner without imports gives an empty
    list. ``meta.vintage`` is the imports list's release time for the month
    (``"2026-10-06T08:00:00"`` for August 2026); ``meta.published_at`` stays empty. The
    MCP server returns at most 200 rows or 64 KB, so pass ``hs10_code`` or
    ``customs_district_id`` there to narrow.

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"IC"`` (Iceland), ``"CH"`` (China), ``"MX"`` (Mexico).
        year: Calendar year, four digits, e.g. ``2026``.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text, e.g. ``"0304"`` (fish fillets), ``"0302140003"`` (one
            product), ``"03"`` (chapter 03). ``None`` (the default) keeps every product.
        customs_district_id: Keep only this US customs district, an id
            ``list_customs_districts`` lists, e.g. ``10`` (NEW YORK, N.Y.), ``4``
            (BOSTON, MASS.), ``1`` (PORTLAND,MAINE). ``None`` (the default) keeps every
            district. Both filters apply after the one data request.
    """
    _check(partner_code, year, month, hs10_code, customs_district_id)
    release = await _release(ProductType.M, year, month, "customs-district imports")
    records = await api.GATSData_GetCustomsDistrictsImports(partner_code, year, month)
    meta = _data_meta(
        "GATSData_GetCustomsDistrictsImports",
        release,
        partner_code,
        year,
        month,
        hs10_code,
        customs_district_id=customs_district_id,
    )
    selected = _in_district(_matching(records, hs10_code), customs_district_id)
    return Result(data=selected, meta=meta)


async def get_customs_district_reexports_async(
    partner_code: str,
    year: int,
    month: int,
    hs10_code: str | None = None,
    customs_district_id: int | None = None,
) -> Result[list[CustomsDistrictExport]]:
    """US re-exports to one partner in one month by US customs district and HS10 product.

    One record per customs district and HS10 code, as the US Census Bureau reported:
    ``customs_district_id`` (``list_customs_districts`` names it) and the ten fields of a
    re-export record; over the districts, a code's records add up to its record in
    ``get_census_reexports``, as recorded. 13 records in 5 districts for Iceland
    (``"IC"``) in August 2026, 5 of them in district 10 (NEW YORK, N.Y.). Two requests:
    the exports release list (``GATSData_GetCensusExportDataReleaseInfo``, kept by the
    client for an hour), then the month (``GATSData_GetCustomsDistrictsReExports``).
    Upstream publishes no re-export release list, so the package checks the exports
    list, by assumption, as ``get_census_reexports`` does: a month it lacks raises
    ``NotFoundError``, and ``meta.vintage`` is its release time for the month
    (``"2026-10-06T08:00:00"`` for August 2026), the exports' release. The arguments are
    checked before either request, ``customs_district_id`` against the packaged districts
    list (an id it lacks names the nearest listed ids). A listed partner without
    re-exports gives an empty list; ``meta.published_at`` stays empty. The MCP server
    returns at most 200 rows or 64 KB; pass ``hs10_code`` or ``customs_district_id``
    there to narrow.

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"IC"`` (Iceland), ``"CH"`` (China), ``"MX"`` (Mexico).
        year: Calendar year, four digits, e.g. ``2026``.
        month: Calendar month from 1 to 12, e.g. ``8`` (August).
        hs10_code: Keep only the products whose HS10 code starts with this, 1 to 10
            digits as text, e.g. ``"62"`` (chapter 62), ``"1905901049"`` (one product).
            ``None`` (the default) keeps every product.
        customs_district_id: Keep only this US customs district, an id
            ``list_customs_districts`` lists, e.g. ``10`` (NEW YORK, N.Y.), ``41``
            (CLEVELAND, OHIO), ``52`` (MIAMI, FLA.). ``None`` (the default) keeps every
            district. Both filters apply after the one data request.
    """
    _check(partner_code, year, month, hs10_code, customs_district_id)
    release = await _release(ProductType.X, year, month, "customs-district re-exports")
    records = await api.GATSData_GetCustomsDistrictsReExports(partner_code, year, month)
    meta = _data_meta(
        "GATSData_GetCustomsDistrictsReExports",
        release,
        partner_code,
        year,
        month,
        hs10_code,
        customs_district_id=customs_district_id,
    )
    selected = _in_district(_matching(records, hs10_code), customs_district_id)
    return Result(data=selected, meta=meta)


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
    changed; the six Census data tasks give their month's time as ``meta.vintage``, the
    re-export forms the exports list's, since re-exports have no list of their own. One
    request, kept by the client for an hour; ``meta.retrieved_at`` is when it was
    fetched. ``meta.published_at`` and ``meta.vintage`` stay empty. The MCP server
    returns the newest 200 months, more than sixteen years, and says so.

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


def _packaged[M](name: str, kind: type[list[M]]) -> tuple[list[M], PackagedList]:
    """The packaged list ``name`` parsed into ``kind``, in upstream order, with its file."""
    packaged = packaged_values(name)
    if packaged is None:  # pragma: no cover - the five lists ship with the package
        raise KeyError(name)
    return parse(kind, packaged.records, source=SOURCE, endpoint=packaged.endpoint), packaged


def _packaged_meta(packaged: PackagedList, request: dict[str, str | None]) -> ResultMeta:
    """Answered now, from the list the package fetched on ``packaged.fetched``."""
    return ResultMeta(
        source=SOURCE,
        endpoint=packaged.endpoint,
        vintage=packaged.fetched.isoformat(),
        request=request,
    )


def _matches(search: str | None, *fields: str | None) -> bool:
    """Case-insensitive substring match of ``search`` in any of ``fields``.

    A ``search`` of ``None`` matches every record; a field that is ``None`` (a country
    without a GENC code, a commodity without a description) matches nothing. Fields are
    matched one at a time, never joined.
    """
    if search is None:
        return True
    needle = search.casefold()
    return any(needle in field.casefold() for field in fields if field is not None)


def _search(search: str | None) -> str | None:
    """``search`` unchanged, or ``InvalidRequestError`` when it is neither text nor ``None``."""
    if search is not None and not isinstance(search, str):
        raise InvalidRequestError(f"search must be text, got {search!r}.", source=SOURCE)
    return search


async def list_regions_async() -> Result[list[Region]]:
    """List GATS's regions with their codes, the values region_code of list_countries takes.

    Answered from ``GATSData_GetRegions`` as packaged with this version
    (``reference/regions.json``), without an upstream call: 15 regions when packaged, in
    upstream order, from ``"R05"`` North America, ``"R10"`` Caribbean and ``"R25"``
    European Union-27 to ``"R40"`` East Asia, ``"R70"`` Oceania and ``"R99"``
    Miscellaneous Designated Areas. Every country's ``region_code`` is one of them.
    ``meta.vintage`` is the day the package fetched the list (``"2026-10-26"``),
    ``meta.retrieved_at`` when this task answered.
    """
    regions, packaged = _packaged("regions", list[Region])
    return Result(data=regions, meta=_packaged_meta(packaged, {}))


async def list_countries_async(
    region_code: str | None = None, search: str | None = None
) -> Result[list[Country]]:
    """List GATS's countries with their codes and regions, the values partner_code takes.

    Answered from ``GATSData_GetCountries`` as packaged with this version
    (``reference/countries.json``), without an upstream call: 322 codes when packaged,
    current and discontinued, in upstream order, each with its region (``list_regions``),
    its ISO code and its GENC code where upstream has one. Codes are GATS's own, not ISO:
    ``"CH"`` China, ``"MX"`` Mexico, ``"JA"`` Japan, ``"IC"`` Iceland; aggregates such as
    ``"01"`` Caribbean,nes have no GENC code. 26 carry a ``discontinued_on`` month, the
    last a Census task accepts for them (``"SZ"`` Switzerland, ``"198712"``; ``"SR"``
    Switzerland is current). ``meta.vintage`` is the day the package fetched the list
    (``"2026-10-25"``), ``meta.retrieved_at`` when this task answered. The MCP server
    returns the whole list.

    Args:
        region_code: Keep the countries of this GATS region, spelled exactly as
            ``list_regions`` spells it, e.g. ``"R05"`` (North America: CA, GL, MX, SB,
            US), ``"R40"`` (East Asia, 9 codes), ``"R55"`` (Sub-Saharan Africa, 67). A
            code no country carries yields an empty list. Omit (``None``) for every
            region.
        search: Keep the countries whose code, name, ISO3 code or GENC code contains
            this text, ignoring case, e.g. ``"iceland"`` (IC Iceland), ``"united"`` (AE,
            U0, UK, US), ``"CHN"`` (CH China, by its ISO3 and GENC code), ``"che"`` (SE
            Seychelles, SZ and SR Switzerland, V5). A short text matches widely:
            ``"IC"`` keeps 44, every name with "ic" in it. Omit (``None``) for every
            country.
    """
    _search(search)
    countries, packaged = _packaged("countries", list[Country])
    selected = [
        c
        for c in countries
        if (region_code is None or c.region_code == region_code)
        and _matches(search, c.country_code, c.country_name, c.iso3_code, c.genc_code)
    ]
    request = {"region_code": region_code, "search": search}
    return Result(data=selected, meta=_packaged_meta(packaged, request))


async def list_hs6_commodities_async(search: str | None = None) -> Result[list[HS6Commodity]]:
    """List GATS's HS6 commodities with their codes, names and units of measure.

    Answered from ``GATSData_GetHS6Commodities`` as packaged with this version
    (``reference/HS6Commodities.json``), without an upstream call: 2,909 codes when
    packaged, in code order, e.g. ``"020110"`` Bovine Carcass Fr/Ch, ``"100190"`` Wheat,
    except Durum; each with a name, a description and four unit-of-measure ids
    (``list_units_of_measure``). Upstream: "Use this to correlate the Import, Export and
    Re-export data records obtained by querying UN Trade Data"; the first six digits of
    every HS10 code in the Census records are a listed code. For HS10 codes use
    ``list_commodities``. ``meta.vintage`` is the day the package fetched the list
    (``"2026-10-26"``), ``meta.retrieved_at`` when this task answered. The MCP server
    returns at most 200 rows or 64 KB, so pass ``search`` there.

    Args:
        search: Keep the commodities where this text occurs, ignoring case, in the code,
            the name or the description, e.g. ``"wheat"`` (15 codes, durum and other
            wheat, wheat flour, buckwheat), ``"0201"`` (the three codes of heading 0201,
            bovine meat fresh or chilled), ``"bovine"``. Omit (``None``) for all.
    """
    _search(search)
    commodities, packaged = _packaged("HS6Commodities", list[HS6Commodity])
    selected = [
        c
        for c in commodities
        if _matches(search, c.hs6_code, c.commodity_name, c.commodity_description)
    ]
    return Result(data=selected, meta=_packaged_meta(packaged, {"search": search}))


async def list_units_of_measure_async() -> Result[list[UnitOfMeasure]]:
    """List GATS's units of measure with their ids, the unit ids of every data record.

    Answered from ``GATSData_GetUnitsOfMeasure`` as packaged with this version
    (``reference/unitsOfMeasure.json``), without an upstream call: 108 units when
    packaged, ids ``0`` to ``107`` in order, e.g. ``47`` Kilograms (``KG``), ``70``
    Metric Tons (``MT``), ``78`` Numbers (``NO``), ``0`` NONE. The ``census_uom_id1``,
    ``census_uom_id2``, ``fas_converted_uom_id`` and ``fas_non_converted_uom_id`` of the
    Census and commodity records are these ids; ``enums.UnitOfMeasureId`` names the same
    ids (``UnitOfMeasureId.KILOGRAMS``). A code is not unique: ``"CRT"`` (Crates) is 33
    and 105. ``meta.vintage`` is the day the package fetched the list (``"2026-10-26"``),
    ``meta.retrieved_at`` when this task answered.
    """
    units, packaged = _packaged("unitsOfMeasure", list[UnitOfMeasure])
    return Result(data=units, meta=_packaged_meta(packaged, {}))


async def list_customs_districts_async() -> Result[list[CustomsDistrict]]:
    """List the US customs districts with their ids, the customs_district_id values.

    Answered from ``GATSData_GetCustomsDistricts`` as packaged with this version
    (``reference/customsDistricts.json``), without an upstream call: 53 districts when
    packaged, ids ``0`` to ``99`` in order with gaps, e.g. ``10`` NEW YORK, N.Y., ``30``
    SEATTLE, WASH., ``52`` MIAMI, FLA., each with its region, one of five (``"EC"`` EAST
    COAST DISTRICTS, ``"GL"``, ``"GP"``, ``"WC"``, ``"OP"``). Upstream: "US Customs
    Districts, the point of Entry and Exit for the Commodity Imports and Exports". Id
    ``0`` is Z UNKNOW CDIST CODES; ``60``, ``70``, ``80`` and ``99`` are vessels,
    shipments under $251, mail and military shipments. ``meta.vintage`` is the day the
    package fetched the list (``"2026-10-26"``), ``meta.retrieved_at`` when this task
    answered.
    """
    districts, packaged = _packaged("customsDistricts", list[CustomsDistrict])
    return Result(data=districts, meta=_packaged_meta(packaged, {}))


async def list_commodities_async(
    search: str | None = None,
    hs10_code: str | None = None,
    product_type: str | None = None,
) -> Result[list[Commodity]]:
    """List GATS's HS10 commodity codes with their product types and units, fetched live.

    Every commodity record ``GATSData_GetCommodities`` lists, current and historical, in
    code order: an HS10 code, its start month, a product type, a short name, a
    description, an agricultural flag and four unit-of-measure ids
    (``list_units_of_measure``). 24,936 records on 2026-10-26, by ``product_type``:
    ``"X"`` 5,919 (export codes, as in the Census exports and re-exports records), ``"M"``
    14,469 (import codes), ``"T"`` 2,704 and ``"B"`` 1,844. Upstream documents none of
    the four; the ``"T"`` and ``"B"`` records carry seven-digit codes padded with three
    spaces (``"0011010   "``) and no description, kept as sent. A code is not unique: it
    repeats across product types and with a later ``start_date`` (``"0207410000"`` under
    ``"M"`` is chicken cuts from ``"198901"`` and ducks from ``"201201"``). Not packaged,
    for its size: one request, kept by the client for a day, so a search after the first
    sends nothing; ``meta.retrieved_at`` is when the list was fetched. ``meta.vintage``
    and ``meta.published_at`` stay empty: upstream gives the list no version or date. The
    filters apply after the one request. The MCP server returns at most 200 rows or
    64 KB, so pass a filter there; for HS6 codes use ``list_hs6_commodities``.

    Args:
        search: Keep the records where this text occurs, ignoring case, in the name or
            the description, e.g. ``"wheat"``, ``"fish fillets"``, ``"swine"``. Omit
            (``None``) for all.
        hs10_code: Keep the records whose code starts with this, 1 to 10 digits as text:
            a full code such as ``"0103910000"`` or a prefix such as ``"0304"`` (fish
            fillets) or ``"02"`` (chapter 02). A padded ``"T"`` or ``"B"`` code matches
            a prefix of up to seven digits. Omit (``None``) for all.
        product_type: Keep the records of this product type, exactly as upstream writes
            it: ``"X"`` (exports), ``"M"`` (imports), ``"T"`` or ``"B"``. A code no record
            carries yields an empty list. Omit (``None``) for all.
    """
    _search(search)
    if hs10_code is not None:
        validate_hs10_code(hs10_code)
    commodities, stored = await api.GATSData_GetCommodities()
    selected = [
        c
        for c in commodities
        if (hs10_code is None or c.hs10_code.startswith(hs10_code))
        and (product_type is None or c.product_type == product_type)
        and _matches(search, c.commodity_name, c.commodity_description)
    ]
    meta = ResultMeta(
        source=SOURCE,
        endpoint="GATSData_GetCommodities",
        retrieved_at=stored or datetime.now(UTC),
        request={"search": search, "hs10_code": hs10_code, "product_type": product_type},
    )
    return Result(data=selected, meta=meta)


get_census_exports = sync(get_census_exports_async)
get_census_imports = sync(get_census_imports_async)
get_census_reexports = sync(get_census_reexports_async)
get_census_release_dates = sync(get_census_release_dates_async)
get_customs_district_exports = sync(get_customs_district_exports_async)
get_customs_district_imports = sync(get_customs_district_imports_async)
get_customs_district_reexports = sync(get_customs_district_reexports_async)
list_commodities = sync(list_commodities_async)
list_countries = sync(list_countries_async)
list_customs_districts = sync(list_customs_districts_async)
list_hs6_commodities = sync(list_hs6_commodities_async)
list_regions = sync(list_regions_async)
list_units_of_measure = sync(list_units_of_measure_async)
