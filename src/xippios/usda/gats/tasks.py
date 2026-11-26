"""Task functions, the public API: the adapters serve ``__all__`` (conventions §2).

``/add-endpoint`` adds them.

The six Census data tasks, ``get_census_exports``, ``get_census_imports`` and
``get_census_reexports``, and ``get_customs_district_exports``,
``get_customs_district_imports`` and ``get_customs_district_reexports`` by US customs
district, answer one partner and one month across every HS10 product (and district), as
one upstream call returns it; never paged, never sliced upstream. Before that call they
check the arguments (``params``) and fetch a release list, which the client caches for
an hour (``_client.RELEASE_DATES_PATHS``): GATS answers a month it has not released with
``[]``, the same as a partner without trade (``future_month.json`` and
``no_data_valid_partner.json`` under ``tests/fixtures/get_census_exports/``), so
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
``meta.published_at`` is the same release time parsed, without a zone as FAS prints it,
with ``meta.published_at_naive`` set (sdk-core ADR-0041, decision 2): an invented zone could
shift it by hours in an as-of store, so a consumer that knows the publisher's zone assigns
it.
``get_census_release_dates`` returns every month's time as upstream states it, or one
statistical year's months (``statistical_year``, a filter applied after the one request
and recorded in ``meta.request``), and leaves ``vintage`` and ``published_at`` empty,
since it answers no single release; its ``meta.retrieved_at`` is the time the client's
cache stored the list when the cache answered (conventions §4), else the time the list
arrived.

The three Census series tasks, ``get_census_export_series``, ``get_census_import_series``
and ``get_census_reexport_series``, answer one partner over a range of months from the same
wrappers as the month tasks, one data call per month (sdk-usda-psd's ``get_time_series`` is
the family's precedent for a series assembled from one call per period). A call spans at
most ``SERIES.value`` months, core's one ``Ceiling`` (sdk-core ADR-0054): 60 in Python and
over HTTP; the MCP server starts with 24, and its ``--series-months`` sets another ceiling
from 1 to 60 through the tool set's hooks (``mcp_add_options``, ``mcp_apply_options``). The
entry point ``xippios-usda-gats-mcp`` sets the MCP ceiling, since core's ``main`` applies
the option, and so does a host that applies the tool set's hooks with their defaults. The
ceiling is process-wide: a Python or HTTP call made in the MCP server's process meets the
MCP ceiling too. Every argument is checked first, the partner code for the start and for the
end month, so a code discontinued inside the range is refused when it is no other code's
parent; a parent code passes for every month (``params.validate_partner_month``). The flow's
release list is fetched once, the imports list for imports and the exports list for exports
and, by the same assumption, re-exports; a range with a month the list lacks is refused
whole as ``NotFoundError`` naming the first such month and the latest released, never
trimmed. Then the months are fetched oldest first, one request after the other at the
client's pace (``_client.RATE_LIMIT``, one per second, and the quota policy on top), never
concurrently, by core's ``fetch_periods``, and returned as one list in month order: every
record carries its month in ``date``, so nothing is grouped or summed, and a month that
answers ``[]`` contributes nothing. ``hs10_code`` filters every month. ``meta.vintage`` is
the newest ``releaseTimeStamp`` among the range's months, as upstream states it: the most
recent of the releases that last revised them, which across the annual revision can be an
earlier month's than the end month's; ``get_census_release_dates`` gives each month's own.
``meta.published_at`` is that newest time, naive, with ``meta.published_at_naive`` set.
``meta.request`` carries the arguments, ``hs10_code`` when given.

The three UN Trade data tasks, ``get_un_exports``, ``get_un_imports`` and
``get_un_reexports``, answer one reporter and one statistical year across every partner
and HS6 product, as one upstream call returns it: data "as reported by UN COMTrade", in
upstream's words, under GATS's own codes. Reporter, partner and HS6 codes stay GATS's, as
``list_countries`` and ``list_hs6_commodities`` list them; nothing is mapped onto another
source's codes (sdk-core ADR-0028). Before the call they check the arguments, the two country
codes for membership only, since the UN data keeps codes the countries list marks
discontinued in 1987 (``DA``, Denmark) for 2019, and fetch the flow's UN Trade release
list, which the client keeps for a day (``_client.UN_RELEASE_DATES_TTL``), the feed being
frozen. An ISO or GENC code that several listed codes share (``"AUS"``: ``A2``, ``AS``),
given as a country code, is refused after that list is read, naming first the codes it
holds as reporters (``AS``), since the recorded lists follow no rule on the codes
themselves (``_un_ranked``); when the list cannot be read the refusal comes unranked, and
every other refusal comes before any request. GATS answers an unknown reporter, a year
far ahead and
a year not released alike with ``[]`` (``unknown_reporter.json``, ``future_year.json``,
``unreleased_year.json`` under ``tests/fixtures/get_un_trade_exports/``), so a
reporter-year the list lacks is refused as ``NotFoundError`` naming the reporter's listed
years and the list's latest year. The imports task checks the imports list
(``GATSData_GetUNTradeImportDataReleaseInfo``); the exports task and, by assumption as
on the Census side, the re-exports task check the exports list
(``GATSData_GetUNTradeExportDataReleaseInfo``): upstream publishes no UN Trade re-export
release list. An empty list for a listed reporter-year is a successful empty result
(Iceland's 2019 re-exports). ``partner_code`` and ``hs6_code`` select records after the
one data call. ``meta.vintage`` is the reporter-year's ``releaseTimeStamp`` from that
list as upstream states it (``"2020-06-03T05:50:46"`` for Iceland's 2019 exports) and
``meta.published_at`` its parsed time, naive, with ``meta.published_at_naive`` set, as for
the Census tasks; the year is in ``meta.request`` and on every record. As recorded on
2026-10-26 the UN Trade feed is frozen (conventions §4): both release lists end with
statistical year 2019, and their newest release time is 2021-01-18, the last release the
README's status table names. ``get_un_release_dates`` returns either list, whole or filtered by
reporter or year, with ``retrieved_at`` from the cache as for the Census list.

The ``list_*`` tasks but one answer from the five lists packaged under ``reference/`` and
make no upstream call, through core's ``PackagedList`` (sdk-core ADR-0041, decision 1):
``meta.endpoint`` is the operation the list was fetched from (``"GATSData_GetCountries"``),
``meta.retrieved_at`` is when the package fetched it, the file's ``fetched``, the UTC
time of the fetch to the second (``"2026-10-28T19:22:40Z"`` for the countries), and
``meta.vintage`` stays empty: upstream gives these lists no version identifier, and a
fetch date is none. ``list_commodities`` is the exception: the HS10 list, 24,936 records and
7.6 MB, is not packaged, so it makes one live request (``GATSData_GetCommodities``),
which the client keeps for a day (``_client.COMMODITIES_TTL``); its ``meta.retrieved_at``
is when the list was fetched, from the cache's stored time on a hit, and ``vintage``
stays empty. The lists' filters (``search``, ``region_code``, ``hs6_code``, ``hs10_code``,
``product_type``) only select records, which keep upstream's order and values;
``meta.request`` carries those given and leaves out one not given. ``meta.total`` stays
unset: upstream reports no count.
"""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime
from typing import Protocol

from xippios.core import (
    Answer,
    Ceiling,
    InvalidRequestError,
    NotFoundError,
    PackagedList,
    Result,
    ResultCap,
    ResultMeta,
    UnknownCode,
    XippiosError,
    fetch_periods,
    matches,
    names_codes,
    sync,
)

from xippios.usda.gats import api
from xippios.usda.gats._client import SOURCE
from xippios.usda.gats.errors import UN_PARTNER_REASON
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
    UNTradeDataReleaseInfo,
    UNTradeRecord,
)
from xippios.usda.gats.params import (
    COUNTRIES,
    DISTRICTS,
    HS6_CODES,
    PACKAGE,
    shared_three_letter_code,
    validate_country_code,
    validate_customs_district_id,
    validate_hs6_code,
    validate_hs6_prefix,
    validate_hs10_code,
    validate_partner_month,
    validate_reporter_code,
    validate_year,
)

__all__ = [
    "get_census_export_series",
    "get_census_exports",
    "get_census_import_series",
    "get_census_imports",
    "get_census_reexport_series",
    "get_census_reexports",
    "get_census_release_dates",
    "get_customs_district_exports",
    "get_customs_district_imports",
    "get_customs_district_reexports",
    "get_un_exports",
    "get_un_imports",
    "get_un_reexports",
    "get_un_release_dates",
    "list_commodities",
    "list_countries",
    "list_customs_districts",
    "list_hs6_commodities",
    "list_regions",
    "list_units_of_measure",
]

# A task named here is Python-only: no tool, no route; the adapters skip it (sdk-core ADR-0040,
# decision 4).
BULK_TASKS: frozenset[str] = frozenset()

HS10_NOTE = "filter by hs10_code, a full code or a prefix such as the chapter '02', to see the rest"
"""What a cut Census data result tells the agent: the one filter the tools have."""

DISTRICT_NOTE = (
    "filter by hs10_code, a full code or a prefix such as the chapter '02', or by "
    "customs_district_id, e.g. 10 (NEW YORK, N.Y.), to see the rest"
)
"""What a cut customs-district result tells the agent: the two filters the tools have."""

SERIES_NOTE = (
    "the rows run month by month, oldest first, and the rows shown are the newest; filter "
    "by hs10_code, a full code or a prefix such as the chapter '03', or ask for fewer "
    "months to see the rest"
)
"""What a cut Census series tells the agent: which rows it got, the newest months' as its
cap keeps them, its one filter and a shorter range, the two ways to narrow it.

The longest range is ``SERIES``'s: 60 months in Python and over HTTP, 24 on the MCP
server, which ``--series-months`` sets from 1 to 60. A range past the ceiling is refused
before any request, naming it; this note only asks for fewer months."""

SERIES = Ceiling(
    60,
    unit="months",
    mcp=24,
    option="--series-months",
    help="one request per month, so 60 months take about a minute of calls",
    source=SOURCE,
)
"""The most months one Census series call spans, core's one ``Ceiling`` (sdk-core ADR-0054).

60 months, five years, in Python and over HTTP, a self-imposed bound: one data request per
month at the client's pace of one request per second, so the longest series takes about a
minute and spends 60 of api.data.gov's 1,000 requests per hour for the key. The MCP server
starts with 24, two years and about 24 seconds for one tool call, and its
``--series-months`` sets another from 1 to 60 through the tool set's hooks,
``mcp_add_options`` and ``mcp_apply_options``. The ceiling in force, ``SERIES.value``, is
the process's: a Python or HTTP call made in the MCP server's process meets the MCP
ceiling too, so one ceiling, and one MCP server, per process."""

mcp_add_options = SERIES.add_options
"""Add ``--series-months`` to the MCP server's command line, a hook of core's ``main``."""

mcp_apply_options = SERIES.apply_options
"""Set the series' ceiling from ``--series-months``, a hook of core's ``main``; a value
outside 1 to 60 is the parser's error, exit status 2, nothing served."""

MCP_INSTRUCTIONS = (
    "USDA FAS Global Agricultural Trade System via xippios. "
    "Tools are read-only. "
    "Where list tools (usda_gats_list_*) exist, call them first to find valid values, "
    "then query."
)
"""The MCP server's instructions, which core's tool set reads from this module."""

RELEASE_DATES_NOTE = (
    "the list runs newest first, so the rows shown are the latest released months; "
    "200 months reach back more than sixteen years; filter by statistical_year, e.g. "
    "1987, to see the rest"
)
"""What a cut release-date list tells the agent: which months it got and its one filter,
``statistical_year``, which keeps one year's months, twelve at most (sdk-core ADR-0038)."""

UN_DATA_NOTE = (
    "filter by partner_code, e.g. 'US' (United States), or by hs6_code, a full code or a "
    "prefix such as the chapter '03', to see the rest"
)
"""What a cut UN Trade data result tells the agent: the two filters the tools have."""

UN_RELEASE_DATES_NOTE = (
    "the list runs newest year first, one row per reporter and year; filter by "
    "reporter_code, e.g. 'IC' (Iceland), or by year, e.g. 2019, to see the rest"
)
"""What a cut UN Trade release-date list tells the agent: its order and its two filters."""

COUNTRIES_NOTE = (
    "filter by region_code, e.g. 'R40' (East Asia), or by search on the code, the name or "
    "the ISO or GENC code to see the rest"
)
"""What a cut countries list would tell the agent: its two filters. The cap of its own
lets the 322 packaged codes through whole, so only a list grown past it is cut."""

HS6_NOTE = (
    "filter by search, on the code, the name and the description, e.g. 'wheat', or by "
    "hs6_code (a code or a prefix such as '0201') to see the rest"
)
"""What the cut HS6 list tells the agent: the two filters the tool has."""

COMMODITIES_NOTE = (
    "filter by search (name or description, e.g. 'wheat'), by hs10_code (a code or a "
    "prefix such as '0201') or by product_type ('X' exports, 'M' imports) to see the rest"
)
"""What the cut HS10 list tells the agent: the three filters the tool has."""

MCP_CAPS: Mapping[str, ResultCap] = {
    "get_census_export_series": ResultCap(note=SERIES_NOTE, keep="last"),
    "get_census_exports": ResultCap(note=HS10_NOTE),
    "get_census_import_series": ResultCap(note=SERIES_NOTE, keep="last"),
    "get_census_imports": ResultCap(note=HS10_NOTE),
    "get_census_reexport_series": ResultCap(note=SERIES_NOTE, keep="last"),
    "get_census_reexports": ResultCap(note=HS10_NOTE),
    "get_census_release_dates": ResultCap(note=RELEASE_DATES_NOTE, paged=True),
    "get_customs_district_exports": ResultCap(note=DISTRICT_NOTE),
    "get_customs_district_imports": ResultCap(note=DISTRICT_NOTE),
    "get_customs_district_reexports": ResultCap(note=DISTRICT_NOTE),
    "get_un_exports": ResultCap(note=UN_DATA_NOTE),
    "get_un_imports": ResultCap(note=UN_DATA_NOTE),
    "get_un_reexports": ResultCap(note=UN_DATA_NOTE),
    "get_un_release_dates": ResultCap(note=UN_RELEASE_DATES_NOTE, paged=True),
    "list_commodities": ResultCap(note=COMMODITIES_NOTE, paged=True),
    "list_countries": ResultCap(max_rows=400, max_bytes=100_000, note=COUNTRIES_NOTE),
    "list_hs6_commodities": ResultCap(note=HS6_NOTE, paged=True),
}
"""MCP result caps of their own, by task function name (conventions §8, sdk-core ADR-0038).

The Census data tools keep the family's bounds, 200 rows or 64 KB, with a note of their
own: a tool with a filter names it (§8). One partner-month is one record per HS10 code,
777 records and about 154 KB of JSON for exports to China in August 2026, 3,294 records
and about 1.1 MB for imports from China; ``hs10_code`` narrows it to a chapter, a heading
or one product. By customs district it is one record per district and code, 1,697
records for exports to China, so those notes name ``customs_district_id`` as well.
The three Census series tools keep the default bounds with a note of their own,
``SERIES_NOTE``, naming ``hs10_code`` and a shorter range as the ways to narrow: a series
is one record per HS10 code and month, in month order, so the rows shown are the oldest
months' (197 records for exports to Iceland over July and August 2026, all of them within
the bounds; 777 for exports to China in August 2026 alone, which are cut).
``get_census_release_dates`` keeps the default bounds with a note of its own,
``RELEASE_DATES_NOTE``: 716 months, newest first, of which the newest 200 arrive, 202608
back to 201001 as recorded, 16 years and 8 months; the note names its one filter,
``statistical_year``, which keeps one year's months, twelve at most, so any year fits.
The UN Trade data tools keep the default bounds too, with a note naming
their two filters, ``partner_code`` and ``hs6_code``: one reporter-year is one record per
partner and HS6 code, about 240 bytes each, so 200 rows arrive within 64 KB; 3,980
records for Iceland's 2019 exports, 23,396 (about 5.2 MB) for its imports, 75,919
(about 17 MB) for India's 2016 exports, as recorded. ``get_un_release_dates`` keeps the
default bounds with a note naming ``reporter_code`` and ``year``: the exports list holds
3,796 reporter-years, newest year first, so the 200 rows shown are 2019's 32, 2018's 80
and 88 of 2017's as recorded; one reporter (31 years for Iceland) or one year (32
reporters for 2019) fits. ``list_countries`` is a reference list an agent needs whole: 322 codes,
past the default 200 rows, and about 57 KB of compact JSON, so its cap of 400 rows or
100,000 bytes lets it through whole, with a note naming its filters for a list that
outgrows it. ``list_hs6_commodities`` (2,909 codes, about 0.7 MB) and
``list_commodities`` (24,936 records, about 7 MB) are too large to serve whole: they keep
the default bounds with notes naming their filters, ``search`` and ``hs6_code`` for the
HS6 list. ``list_regions`` (15),
``list_units_of_measure`` (108) and ``list_customs_districts`` (53) fit the default.
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
"""The Census release list of each ``productType``: its flow and its operation."""

UN_RELEASE_LISTS: dict[ProductType, tuple[str, str]] = {
    ProductType.X: ("exports", "GATSData_GetUNTradeExportDataReleaseInfo"),
    ProductType.M: ("imports", "GATSData_GetUNTradeImportDataReleaseInfo"),
}
"""The UN Trade release list of each ``productType``: its flow and its operation."""


def _product_type(product_type: ProductType) -> ProductType:
    """``product_type`` as ``ProductType`` (a plain ``"X"`` too), else ``InvalidRequestError``."""
    try:
        return ProductType(product_type)
    except (ValueError, TypeError):
        raise InvalidRequestError(
            f'product_type must be "X" (exports) or "M" (imports), upstream\'s productType '
            f"codes, got {product_type!r}. Nothing was sent.",
            source=SOURCE,
        ) from None


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
    fetched: datetime,
    flow: str,
    operation: str,
    data: str | None = None,
    *,
    series: tuple[str, str] | None = None,
) -> DataReleaseInfo:
    """The record of ``month_code`` in the flow's release list, else ``NotFoundError``.

    Args:
        month_code: The requested month as six digits, e.g. ``"203501"``.
        releases: The flow's release list, one record per released month.
        fetched: When the list was retrieved: the time the client's cache stored it on a
            hit, else the time it arrived (``client.get_answer``).
        flow: ``"exports"`` or ``"imports"``, the list's flow, for the message.
        operation: The release-date operation, for the message.
        data: What was asked for, e.g. ``"re-exports"``, ``"customs-district imports"``;
            ``None`` for the flow itself.
        series: The first and the last month of a series task's range, six digits each,
            e.g. ``("202607", "202609")``: the refusal names the range and says that a
            series is refused whole. ``None`` for a month task.

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
        f" The release list was fetched at {fetched:%Y-%m-%d %H:%M} UTC and is kept for an "
        "hour; a month released since then is refused until it is fetched again."
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
    within = "" if series is None else f", in the requested range {series[0]} to {series[1]}"
    whole = (
        ""
        if series is None
        else " A series is refused whole, never trimmed to the months released: every "
        "month of the range must be in the release list."
    )
    raise NotFoundError(
        f"GATS has no Census {asked} for {month_code}{within}: {reason}. GATS answers a month "
        f"it has not released with an empty list, so the package checks the release list "
        f"first.{whole}{own}{when}",
        source=SOURCE,
    )


async def _releases(product_type: ProductType) -> Answer[list[DataReleaseInfo]]:
    """The Census release list of ``product_type`` and when it was retrieved, as ``Answer``.

    One request, or none while the cache holds the list (``_client.RELEASE_DATES_TTL``);
    the time is the cache's stored time on a hit, else the time the list arrived.
    """
    if product_type is ProductType.X:
        return await api.get_census_export_data_release_info()
    return await api.get_census_import_data_release_info()


async def _release(
    product_type: ProductType, year: int, month: int, data: str | None = None
) -> tuple[DataReleaseInfo, datetime]:
    """The month's record in the release list of ``product_type`` and the list's time.

    The list comes from the client's cache when it holds it, and its time is the cache's
    stored time on a hit, else the time it arrived; ``data`` names what was asked for in
    the refusal, e.g. ``"re-exports"``. See ``_release_of``.
    """
    listed = await _releases(product_type)
    releases, fetched = listed.payload, listed.retrieved_at
    flow, operation = RELEASE_LISTS[product_type]
    release = _release_of(f"{year:04d}{month:02d}", releases, fetched, flow, operation, data)
    return release, fetched


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
    retrieved_at: datetime,
    partner_code: str,
    year: int,
    month: int,
    hs10_code: str | None,
    **filters: int | None,
) -> ResultMeta:
    """``ResultMeta`` of a Census data task: ``vintage`` the month's release time.

    ``vintage`` is the release record's ``releaseTimeStamp`` as upstream states it: the
    model keeps the time naive, and ``isoformat()`` gives back upstream's text,
    ``"2026-10-06T08:00:00"`` for 2026-08. ``published_at`` is that time, naive as FAS
    prints it, with ``published_at_naive`` set (sdk-core ADR-0041, decision 2). ``filters`` are the
    task's other filters, e.g. ``customs_district_id``, recorded in ``meta.request`` after
    ``hs10_code``; a filter left ``None`` is left out. ``retrieved_at`` is the oldest of
    the call's two reads, the release list's and the month's, as the client gives each
    (conventions §4).
    """
    return ResultMeta(
        source=SOURCE,
        endpoint=endpoint,
        retrieved_at=retrieved_at,
        published_at=release.release_time_stamp,
        published_at_naive=True,
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
    close. A parent code, one that is another record's ``country_parent_code`` in
    ``list_countries``, passes for every month: for August 2026 ``"Y1"``
    (Leeward-Windward Islands) held every product of ``"AC"`` (Antigua and Barbuda) at no
    lower a value, and ``"AS"`` (Australia) the same records as ``"A2"`` apart from the
    code. A code GATS discontinued before the month that is no parent is refused, naming
    the listed codes of the same name (``"D1"``, Denmark, after 198712, names ``"9U"``).
    The two-digit codes of region ``R99`` (``"01"`` Caribbean,nes to ``"18"`` ASEAN) pass
    too; ``"01"`` and ``"18"`` gave an empty list for August 2026. A month not released
    yet, or before January 1967, raises ``NotFoundError`` naming the months released; a
    listed partner without exports that month gives an empty list.
    ``meta.vintage`` is the month's release time from that list, as upstream states it
    (``"2026-10-06T08:00:00"`` for August 2026): the release that last revised the
    figures, since Census applies corrections once a year. For up to an hour after a
    release the cached list may still give the previous release's time, an accepted lag.
    The month itself is in ``meta.request`` and in every record's ``date``
    (``"202608"``). ``meta.published_at`` is that time, without a zone as FAS prints it,
    and ``meta.published_at_naive`` says so.

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
    release, listed_at = await _release(ProductType.X, year, month)
    answer = await api.get_census_exports(partner_code, year, month)
    records = answer.payload
    meta = _data_meta(
        "GATSData_GetCensusExports",
        release,
        min(listed_at, answer.retrieved_at),
        partner_code,
        year,
        month,
        hs10_code,
    )
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
    discontinued before the month that is no parent (``"D1"``, Denmark, after 198712) is
    refused naming the listed codes of the same name (``"9U"``). A parent code, another
    record's ``country_parent_code`` in ``list_countries`` (``"Y1"``, ``"AS"``), and the
    two-digit codes of region ``R99`` (``"01"``, ``"18"``) pass for every month, an empty
    list meaning no data. A month not released yet, or before January 1967, raises
    ``NotFoundError`` naming the months released; a listed partner without imports that
    month gives an empty list. ``meta.vintage`` is the month's release time from that list,
    as upstream states it (``"2026-10-06T08:00:00"`` for August 2026): the release that last
    revised the figures, since Census applies corrections once a year. For up to an hour
    after a release the cached list may still give the previous release's time, an accepted
    lag. The month itself is in ``meta.request`` and in every record's ``date``
    (``"202608"``). ``meta.published_at`` is that time, without a zone as FAS prints it, and
    ``meta.published_at_naive`` says so.

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
    release, listed_at = await _release(ProductType.M, year, month)
    answer = await api.get_census_import(partner_code, year, month)
    records = answer.payload
    meta = _data_meta(
        "GATSData_GetCensusImport",
        release,
        min(listed_at, answer.retrieved_at),
        partner_code,
        year,
        month,
        hs10_code,
    )
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
    ``"IC"``) or ``list_countries``, a code discontinued before the month is refused when
    it is no parent, and a parent code (another record's ``country_parent_code`` in
    ``list_countries``, e.g. ``"Y1"``) or a two-digit code of region ``R99`` (``"01"``)
    passes for every month. A listed partner without re-exports that month gives an empty
    list. The month is in ``meta.request`` and in every record's ``date``;
    ``meta.published_at`` is the release time, naive (``meta.published_at_naive``).

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
    release, listed_at = await _release(ProductType.X, year, month, "re-exports")
    answer = await api.get_census_re_exports(partner_code, year, month)
    records = answer.payload
    meta = _data_meta(
        "GATSData_GetCensusReExports",
        release,
        min(listed_at, answer.retrieved_at),
        partner_code,
        year,
        month,
        hs10_code,
    )
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
    nearest listed ids with their names. A parent code (``"Y1"``) and a two-digit code of
    region ``R99`` (``"01"``) pass as there, and a discontinued code that is no parent is
    refused after its month. A month not released yet raises ``NotFoundError``; a listed
    partner without exports gives an empty list. ``meta.vintage`` is the exports list's
    release time for the month (``"2026-10-06T08:00:00"`` for August 2026);
    ``meta.published_at`` is that time, naive (``meta.published_at_naive``).

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
    release, listed_at = await _release(ProductType.X, year, month, "customs-district exports")
    answer = await api.get_customs_districts_exports(partner_code, year, month)
    records = answer.payload
    meta = _data_meta(
        "GATSData_GetCustomsDistrictsExports",
        release,
        min(listed_at, answer.retrieved_at),
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
    ``InvalidRequestError`` naming the nearest listed ids with their names. A parent code
    (``"Y1"``) and a two-digit code of region ``R99`` (``"01"``) pass as there, and a
    discontinued code that is no parent is refused after its month. A month not released
    yet raises ``NotFoundError``; a listed partner without imports gives an empty list.
    ``meta.vintage`` is the imports list's release time for the month
    (``"2026-10-06T08:00:00"`` for August 2026); ``meta.published_at`` is that time, naive
    (``meta.published_at_naive``).

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
    release, listed_at = await _release(ProductType.M, year, month, "customs-district imports")
    answer = await api.get_customs_districts_imports(partner_code, year, month)
    records = answer.payload
    meta = _data_meta(
        "GATSData_GetCustomsDistrictsImports",
        release,
        min(listed_at, answer.retrieved_at),
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
    list (an id it lacks names the nearest listed ids); a parent code (``"Y1"``) and a
    two-digit code of region ``R99`` (``"01"``) pass as for ``get_census_exports``, and a
    discontinued code that is no parent is refused after its month. A listed partner
    without re-exports gives an empty list; ``meta.published_at`` is the release time,
    naive (``meta.published_at_naive``).

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
    release, listed_at = await _release(ProductType.X, year, month, "customs-district re-exports")
    answer = await api.get_customs_districts_re_exports(partner_code, year, month)
    records = answer.payload
    meta = _data_meta(
        "GATSData_GetCustomsDistrictsReExports",
        release,
        min(listed_at, answer.retrieved_at),
        partner_code,
        year,
        month,
        hs10_code,
        customs_district_id=customs_district_id,
    )
    selected = _in_district(_matching(records, hs10_code), customs_district_id)
    return Result(data=selected, meta=meta)


def _series_months(
    partner_code: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    hs10_code: str | None,
) -> list[tuple[int, int]]:
    """Every argument of a Census series task, checked before any call; its months in order.

    ``validate_partner_month`` checks the partner code, the year and the month of the
    start and then of the end month: a code discontinued inside the range that is no
    other code's parent is refused at the end month, naming its ``discontinuedOn``; a
    parent code passes for every month. Then the start must not be after the end, the
    span must pass ``SERIES.check``, and ``hs10_code`` must pass ``validate_hs10_code``.
    A refusal of the span is core's: it names the ceiling in force and, below 60, that it
    is the ceiling set for this process, that the MCP server starts with 24 by default and
    that ``--series-months`` raises it, up to 60, and says that nothing was sent.

    Returns:
        ``(year, month)`` of every month from the start to the end, both included, oldest
        first, e.g. ``[(2026, 7), (2026, 8)]``.

    Raises:
        UnknownCode: The packaged countries list lacks ``partner_code``.
        InvalidRequestError: A year or a month is not valid, the code is a leaf
            discontinued before the start or the end month, the start is after the end,
            the range spans more months than ``SERIES.value``, or ``hs10_code`` is
            not 1 to 10 digits.
    """
    validate_partner_month(partner_code, start_year, start_month)
    validate_partner_month(partner_code, end_year, end_month)
    start = f"{start_year:04d}-{start_month:02d}"
    end = f"{end_year:04d}-{end_month:02d}"
    if (start_year, start_month) > (end_year, end_month):
        raise InvalidRequestError(
            f"the range starts at {start}, after its end {end}. Nothing was sent. Pass the "
            "earlier month as start_year and start_month, e.g. start_year=2026, "
            "start_month=6, end_year=2026, end_month=8.",
            source=SOURCE,
        )
    first = start_year * 12 + start_month - 1
    last = end_year * 12 + end_month - 1
    span = last - first + 1
    SERIES.check(
        span,
        asked=f"{start} to {end}",
        advice=(
            "Ask for a shorter range, or for consecutive ranges of at most "
            f"{SERIES.value} months one after another."
        ),
    )
    if hs10_code is not None:
        validate_hs10_code(hs10_code)
    return [(index // 12, index % 12 + 1) for index in range(first, last + 1)]


async def _series[R: _Coded](
    fetch: Callable[[str, int, int], Awaitable[Answer[list[R]]]],
    endpoint: str,
    product_type: ProductType,
    data: str | None,
    partner_code: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    hs10_code: str | None,
) -> tuple[list[R], ResultMeta]:
    """A Census series: the checks, the release list once, then ``fetch`` month by month.

    The arguments are checked first (``_series_months``). The release list of
    ``product_type`` is fetched once, or answered by the client's cache, and every month
    of the range must be in it: the first month it lacks raises ``NotFoundError``
    (``_release_of``), before any data request, so a range is never trimmed to the
    months released. Then core's ``fetch_periods`` runs ``fetch`` once per month, oldest
    first, each request awaited before the next: the client's rate limiter and quota
    policy pace them, and nothing runs concurrently. A request after the first month that
    fails raises its error, naming the months answered before it, and the series returns
    nothing (sdk-core ADR-0054). ``hs10_code`` filters every month's records, which are
    kept in upstream order and concatenated in month order; a month that answers ``[]``
    adds nothing.

    Args:
        fetch: The month's data wrapper, e.g. ``api.get_census_exports``.
        endpoint: Its operation, ``meta.endpoint``, e.g. ``"GATSData_GetCensusExports"``.
        product_type: Which release list to check: ``ProductType.X`` for exports and
            re-exports, ``ProductType.M`` for imports.
        data: What was asked for, for the refusal, e.g. ``"re-exports"``; ``None`` when
            it is the list's own flow.
        partner_code: The partner, e.g. ``"IC"``.
        start_year: The first month's year, e.g. ``2026``.
        start_month: The first month, e.g. ``7``.
        end_year: The last month's year, e.g. ``2026``.
        end_month: The last month, included, e.g. ``8``.
        hs10_code: A prefix of the HS10 code, e.g. ``"03"``, or ``None``.

    Returns:
        The records in month order and their ``ResultMeta``: ``vintage`` the newest
        ``releaseTimeStamp`` among the range's months as upstream states it,
        ``published_at`` that time, naive, with ``published_at_naive`` set, ``request``
        the arguments, ``hs10_code`` when given. The task builds its ``Result`` from the
        two, since pydantic cannot parametrise ``Result`` with a type variable bound to a
        protocol.
    """
    months = _series_months(partner_code, start_year, start_month, end_year, end_month, hs10_code)
    listed = await _releases(product_type)
    releases, fetched = listed.payload, listed.retrieved_at
    flow, operation = RELEASE_LISTS[product_type]
    codes = [f"{year:04d}{month:02d}" for year, month in months]
    found = [
        _release_of(code, releases, fetched, flow, operation, data, series=(codes[0], codes[-1]))
        for code in codes
    ]
    answers = await fetch_periods(
        [f"{year:04d}-{month:02d}" for year, month in months],
        lambda period: fetch(partner_code, int(period[:4]), int(period[5:])),
    )
    records = [record for _, answer in answers for record in _matching(answer.payload, hs10_code)]
    retrieved_at = min([fetched, *(answer.retrieved_at for _, answer in answers)])
    newest = max(release.release_time_stamp for release in found)
    meta = ResultMeta(
        source=SOURCE,
        endpoint=endpoint,
        retrieved_at=retrieved_at,
        published_at=newest,
        published_at_naive=True,
        vintage=newest.isoformat(),
        request={
            "partner_code": partner_code,
            "start_year": start_year,
            "start_month": start_month,
            "end_year": end_year,
            "end_month": end_month,
            "hs10_code": hs10_code,
        },
    )
    return records, meta


async def get_census_export_series_async(
    partner_code: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    hs10_code: str | None = None,
) -> Result[list[CensusExport]]:
    """US exports to one partner over a range of months by HS10 product, oldest month first.

    The records ``get_census_exports`` answers for each month from the start month to the
    end month, both included, as one list in month order, each month's records in
    upstream order; every record carries its month in ``date`` (``"202607"``), and a month
    without exports adds none. 197 records for Iceland (``"IC"``) over July and August
    2026, 105 and 92. Up to 60 months in Python and over HTTP; the entry point
    ``xippios-usda-gats-mcp`` starts the MCP server with a ceiling of 24, which its
    ``--series-months`` sets from 1 to 60 (``series_ceiling()``, one ceiling per process).
    Requests: the exports release list
    (``GATSData_GetCensusExportDataReleaseInfo``) once, or none while the client keeps
    it, for an hour; then one ``GATSData_GetCensusExports`` request per month, one after
    another at the client's pace of one request per second, never at once. Each spends
    one of api.data.gov's 1,000 requests per hour for the key, and 60 months take about
    a minute; a quota spent partway raises ``RateLimitError`` and returns none of the
    months. Everything is checked before the first request: the partner code as for
    ``get_census_exports`` (an unknown code names close codes) for the start and for the
    end month, so a code discontinued inside the range that is no parent is refused
    naming its last month (``"D1"``, Denmark, 198712, for 1987-06 to 1988-01), while a
    parent code (another record's ``country_parent_code`` in ``list_countries``: ``"Y1"``,
    ``"AS"``) and a two-digit code of region ``R99`` (``"01"``, ``"18"``) pass for every
    month, a month without data adding nothing; a start after the end, or a range of more
    months than the ceiling, raises ``InvalidRequestError`` naming the ceiling. Every month
    of the range must be released: the first month the release list lacks raises
    ``NotFoundError`` naming it and the latest month released, so an end month not released
    yet refuses the series rather than trimming it. ``meta.vintage`` is the newest release
    time among the range's months, as upstream states it: ``"2026-10-06T08:00:00"`` for
    2026-06 to 2026-08, August's release. Across Census's annual revision it can be an
    earlier month's: ``"2026-06-24T08:00:00"`` for 2025-12 to 2026-02, December's revised
    release, not February's. Each month's own release time is in
    ``get_census_release_dates``. ``meta.published_at`` is that newest time, naive
    (``meta.published_at_naive``).

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"IC"`` (Iceland), ``"CH"`` (China), ``"MX"`` (Mexico).
        start_year: The first month's year, four digits, e.g. ``2026``; the data starts
            in January 1967.
        start_month: The first month, 1 to 12, e.g. ``6`` (June).
        end_year: The last month's year, four digits, e.g. ``2026``.
        end_month: The last month, 1 to 12, included, e.g. ``8`` (August); at most 59
            months after the first in Python and over HTTP, 23 on the MCP server as
            ``xippios-usda-gats-mcp`` starts it without ``--series-months``.
        hs10_code: Keep only the products whose HS10 code starts with this, in every
            month, 1 to 10 digits as text: a prefix such as ``"03"`` (chapter 03, fish)
            or ``"0304"`` (fish fillets), or a full code such as ``"0203292000"`` for one
            product. ``None`` (the default) keeps every product. Applied after each
            month's request.
    """
    records, meta = await _series(
        api.get_census_exports,
        "GATSData_GetCensusExports",
        ProductType.X,
        None,
        partner_code,
        start_year,
        start_month,
        end_year,
        end_month,
        hs10_code,
    )
    return Result(data=records, meta=meta)


async def get_census_import_series_async(
    partner_code: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    hs10_code: str | None = None,
) -> Result[list[CensusImport]]:
    """US imports from one partner over a range of months by HS10 product, oldest month first.

    The records ``get_census_imports`` answers for each month from the start month to the
    end month, both included, as one list in month order, each month's records in
    upstream order, with their consumption and CIF fields; every record carries its month
    in ``date``, and a month without imports adds none. 157 records for Iceland
    (``"IC"``) over July and August 2026, 83 and 74, of which 85 are fish (``hs10_code``
    ``"03"``). Up to 60 months in Python and over HTTP; the entry point
    ``xippios-usda-gats-mcp`` starts the MCP server with a ceiling of 24, which its
    ``--series-months`` sets from 1 to 60 (``series_ceiling()``, one ceiling per process).
    Requests: the imports release list
    (``GATSData_GetCensusImportDataReleaseInfo``) once, or none while the client keeps
    it, for an hour; then one ``GATSData_GetCensusImport`` request per month, one after
    another at the client's pace of one request per second, never at once, each one of
    api.data.gov's 1,000 requests per hour for the key: 60 months take about a minute,
    and a quota spent partway raises ``RateLimitError`` and returns none of the months.
    The arguments are checked before the first request as for
    ``get_census_export_series``, a parent code or a two-digit code of region ``R99``
    passing for every month and a discontinued code that is no parent refused after its
    month; the first month the imports list lacks raises ``NotFoundError`` naming it and the
    latest month released, so the series is refused, not trimmed. ``meta.vintage`` is the
    newest release time among the range's months in the imports list, as upstream states it
    (``"2026-10-06T08:00:00"`` for 2026-06 to 2026-08); each month's own is in
    ``get_census_release_dates``. ``meta.published_at`` is that newest time, naive
    (``meta.published_at_naive``).

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"IC"`` (Iceland), ``"CH"`` (China), ``"MX"`` (Mexico).
        start_year: The first month's year, four digits, e.g. ``2026``; the data starts
            in January 1967.
        start_month: The first month, 1 to 12, e.g. ``6`` (June).
        end_year: The last month's year, four digits, e.g. ``2026``.
        end_month: The last month, 1 to 12, included, e.g. ``8`` (August); at most 59
            months after the first in Python and over HTTP, 23 on the MCP server as
            ``xippios-usda-gats-mcp`` starts it without ``--series-months``.
        hs10_code: Keep only the products whose HS10 code starts with this, in every
            month, 1 to 10 digits as text: a prefix such as ``"03"`` (chapter 03, fish)
            or ``"0304"`` (fish fillets), or a full code such as ``"0302140003"`` for one
            product. ``None`` (the default) keeps every product. Applied after each
            month's request.
    """
    records, meta = await _series(
        api.get_census_import,
        "GATSData_GetCensusImport",
        ProductType.M,
        None,
        partner_code,
        start_year,
        start_month,
        end_year,
        end_month,
        hs10_code,
    )
    return Result(data=records, meta=meta)


async def get_census_reexport_series_async(
    partner_code: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    hs10_code: str | None = None,
) -> Result[list[CensusExport]]:
    """US re-exports to one partner over a range of months by HS10 product, oldest month first.

    The records ``get_census_reexports`` answers for each month from the start month to
    the end month, both included, as one list in month order, each month's records in
    upstream order; every record carries its month in ``date``, and a month without
    re-exports adds none. 31 records for Iceland (``"IC"``) over July and August 2026, 19
    and 12. Up to 60 months in Python and over HTTP; the entry point
    ``xippios-usda-gats-mcp`` starts the MCP server with a ceiling of 24, which its
    ``--series-months`` sets from 1 to 60 (``series_ceiling()``, one ceiling per process).
    Requests: the exports release list
    (``GATSData_GetCensusExportDataReleaseInfo``) once, or none while the client keeps
    it, for an hour; then one ``GATSData_GetCensusReExports`` request per month, one
    after another at the client's pace of one request per second, never at once, each one
    of api.data.gov's 1,000 requests per hour for the key: 60 months take about a minute,
    and a quota spent partway raises ``RateLimitError`` and returns none of the months.
    Upstream publishes no re-export release list, so the package checks the exports list,
    by assumption, as ``get_census_reexports`` does. The arguments are checked before the
    first request as for ``get_census_export_series``, a parent code or a two-digit code
    of region ``R99`` passing for every month and a discontinued code that is no parent
    refused after its month; the first month the exports list lacks raises ``NotFoundError``
    naming it and the latest month released, so the series is refused, not trimmed.
    ``meta.vintage`` is the newest release time among the range's months in the exports list
    (``"2026-10-06T08:00:00"`` for 2026-06 to 2026-08), the exports' releases, not ones the
    re-exports state; each month's own is in ``get_census_release_dates``.
    ``meta.published_at`` is that newest time, naive (``meta.published_at_naive``).

    Args:
        partner_code: GATS's two-character country code, not ISO, as ``list_countries``
            lists it, e.g. ``"IC"`` (Iceland), ``"CH"`` (China), ``"MX"`` (Mexico).
        start_year: The first month's year, four digits, e.g. ``2026``; the data starts
            in January 1967.
        start_month: The first month, 1 to 12, e.g. ``6`` (June).
        end_year: The last month's year, four digits, e.g. ``2026``.
        end_month: The last month, 1 to 12, included, e.g. ``8`` (August); at most 59
            months after the first in Python and over HTTP, 23 on the MCP server as
            ``xippios-usda-gats-mcp`` starts it without ``--series-months``.
        hs10_code: Keep only the products whose HS10 code starts with this, in every
            month, 1 to 10 digits as text: a prefix such as ``"03"`` (chapter 03, fish)
            or ``"62"`` (chapter 62, 7 of Iceland's 31 records), or a full code such as
            ``"0709202000"`` for one product. ``None`` (the default) keeps every product.
            Applied after each month's request.
    """
    records, meta = await _series(
        api.get_census_re_exports,
        "GATSData_GetCensusReExports",
        ProductType.X,
        "re-exports",
        partner_code,
        start_year,
        start_month,
        end_year,
        end_month,
        hs10_code,
    )
    return Result(data=records, meta=meta)


async def get_census_release_dates_async(
    product_type: ProductType, statistical_year: int | None = None
) -> Result[list[DataReleaseInfo]]:
    """When GATS last released each month of US Census exports or imports: poll for releases.

    One record per statistical month, newest first, from ``"196701"`` to the latest
    released (``"202608"`` on 2026-10-25), 716 months: ``statistical_year_month`` and
    ``release_time_stamp``, the time of the month's latest release, as upstream states it,
    without a time zone (``2026-10-06T08:00:00`` for 2026-08). A month the annual
    revision corrected carries the revision's time: 2023-01 to 2025-12 read
    ``2026-06-24T08:00:00``. Compare it with a stored one to fetch only the months that
    changed; the six Census data tasks give their month's time as ``meta.vintage``, the
    three series tasks the newest among their months, the re-export forms the exports
    list's, since re-exports have no list of their own. ``statistical_year`` keeps one
    year's months, newest first. One request, kept by the client for an hour, the filter
    applied after it; ``meta.retrieved_at`` is when it was fetched. ``meta.published_at``
    and ``meta.vintage`` stay empty: the list is no single release.

    Args:
        product_type: Which list, by upstream's ``productType`` code: ``"X"`` exports
            (``GATSData_GetCensusExportDataReleaseInfo``), ``"M"`` imports
            (``GATSData_GetCensusImportDataReleaseInfo``).
        statistical_year: Keep only the months of this statistical year, four digits,
            e.g. ``2026`` (202608 back to 202601, eight months as recorded), ``2025``
            (twelve, all re-released at ``2026-06-24T08:00:00``), ``1987`` (twelve, all
            at ``2008-01-01T08:00:00``). A year the list lacks, before 1967 or not
            released yet, gives an empty list. ``None`` (the default) keeps every month.
    """
    code = _product_type(product_type)
    if statistical_year is not None:
        validate_year(statistical_year, "statistical_year")
    if code is ProductType.X:
        endpoint = "GATSData_GetCensusExportDataReleaseInfo"
        listed = await api.get_census_export_data_release_info()
    else:
        endpoint = "GATSData_GetCensusImportDataReleaseInfo"
        listed = await api.get_census_import_data_release_info()
    releases, retrieved_at = listed.payload, listed.retrieved_at
    year = None if statistical_year is None else f"{statistical_year:04d}"
    selected = [r for r in releases if year is None or r.statistical_year_month.startswith(year)]
    meta = ResultMeta(
        source=SOURCE,
        endpoint=endpoint,
        retrieved_at=retrieved_at,
        request={"product_type": code.value, "statistical_year": statistical_year},
    )
    return Result(data=selected, meta=meta)


def _un_check(
    reporter_code: str,
    year: int,
    partner_code: str | None,
    hs6_code: str | None,
    reporters: frozenset[str] | None = None,
) -> None:
    """Every argument of a UN Trade data task, before the data call; see ``params``.

    Both country codes are checked for membership in the packaged countries list only:
    the Census tasks' ``discontinuedOn`` rule (``validate_partner_month``) does not apply,
    since the UN data keeps GATS's older codes for 2019, among them ``DA`` (Denmark,
    discontinued 198712), a leaf that rule refuses after its month. ``reporters`` ranks
    the close codes of a refusal (``_un_ranked``).
    """
    validate_reporter_code(reporter_code, reporters=reporters)
    validate_year(year)
    if partner_code is not None:
        validate_country_code(
            partner_code, "partner_code", reason=UN_PARTNER_REASON, reporters=reporters
        )
    if hs6_code is not None:
        validate_hs6_code(hs6_code)


async def _un_releases(product_type: ProductType) -> Answer[list[UNTradeDataReleaseInfo]]:
    """The UN Trade release list of ``product_type`` and when it was retrieved, as ``Answer``.

    One request, or none while the cache holds the list (``_client.UN_RELEASE_DATES_TTL``,
    a day); the time is the cache's stored time on a hit, else the time the list arrived.
    """
    if product_type is ProductType.X:
        return await api.get_un_trade_export_data_release_info()
    return await api.get_un_trade_import_data_release_info()


async def _un_ranked(
    product_type: ProductType, check: Callable[[frozenset[str] | None], None]
) -> None:
    """Run a UN Trade task's argument checks; rank a shared ISO or GENC code's refusal.

    ``check`` runs first with no reporters, before any request. A refusal of a country
    code passes through unless the value is an ISO or GENC code several listed codes
    share (``params.shared_three_letter_code``: ``"AUS"`` leads to ``A2`` and ``AS``).
    For that one the flow's release list is read, which the task reads before its data
    anyway, and ``check`` runs again with the list's reporters: the refusal names the
    codes the list holds as reporters first, still before the data call. No rule on the
    codes themselves ranks them: as recorded on 2026-10-26 both lists hold ``AS`` and
    never ``A2`` (Australia), ``NO`` and never ``N3`` (Norway), but ``F1`` and never
    ``FR`` (France), ``SR`` and never ``SZ`` (Switzerland), and both ``GM`` and ``GE``
    (Germany) for different years. The list only ranks the refusal: when it cannot be
    read (no key, a refused key, a spent quota, the network), the refusal is raised as
    the first check made it, unranked, since a refused argument is refused whatever the
    list does.

    Args:
        product_type: The flow whose list ranks the codes: ``ProductType.X`` for the
            exports and re-exports tasks, ``ProductType.M`` for the imports task.
        check: The task's checks with the reporters to rank by, e.g.
            ``lambda reporters: _un_check("AUS", 2019, None, None, reporters)``.

    Raises:
        UnknownCode: A country code, a six-digit ``hs6_code``, the packaged lists lack;
            for a shared ISO or GENC code ranked by the release list's reporters, or in
            the countries list's order when the list cannot be read. Never the list's
            own error: a ``ConfigError``, ``AuthError``, ``RateLimitError`` or
            ``TransportError`` from reading it gives way to the refusal.
        InvalidRequestError: Another argument is not valid.
    """
    refused: UnknownCode | None = None
    try:
        check(None)
    except UnknownCode as unknown:
        shared = shared_three_letter_code(unknown.value)
        if unknown.param not in {"reporter_code", "partner_code"} or not shared:
            raise
        refused = unknown
    if refused is None:
        return
    flow, operation = UN_RELEASE_LISTS[product_type]
    listed = f"The UN Trade {flow} release list ({operation}) was"
    try:
        releases = (await _un_releases(product_type)).payload
    except XippiosError as failed:
        sent = (
            f"{listed} asked for to rank the codes and could not be read "
            f"({type(failed).__name__}), and nothing else was sent."
        )
        raise _sent(refused, sent) from None
    try:
        check(frozenset(release.reporter_code for release in releases))
    except UnknownCode as ranked:
        raise _sent(
            ranked, f"{listed} read to rank the codes, and nothing else was sent."
        ) from None


def _sent(refusal: UnknownCode, sent: str) -> UnknownCode:
    """``refusal`` saying what was sent in place of ``Nothing was sent.`` (conventions §5).

    ``UnknownCode`` says ``Nothing was sent.``, true for a check before any request; a
    refusal that ``_un_ranked`` raises once it asked for the UN Trade release list says
    instead that the list was read, or asked for and not read, and that nothing else was.

    Args:
        refusal: The check's refusal, e.g. of ``"AUS"`` as ``reporter_code``.
        sent: The sentence that takes ``Nothing was sent.``'s place.
    """
    refusal.message = refusal.message.replace("Nothing was sent.", sent, 1)
    refusal.args = (refusal.message,)
    return refusal


def _years(years: Iterable[str]) -> str:
    """Four-digit years as runs, e.g. ``"1991 to 1999, 2015, 2016, 2019"``.

    A run of three years or more is written ``"<first> to <last>"``; anything that is not
    four ASCII digits is listed as it is, in text order.
    """
    ordered = sorted(set(years))
    if not all(len(year) == 4 and year.isascii() and year.isdigit() for year in ordered):
        return ", ".join(ordered)
    runs: list[list[int]] = []
    for year in map(int, ordered):
        if runs and year == runs[-1][-1] + 1:
            runs[-1].append(year)
        else:
            runs.append([year])
    return ", ".join(
        f"{run[0]} to {run[-1]}" if len(run) > 2 else ", ".join(map(str, run)) for run in runs
    )


def _un_release_of(
    reporter_code: str,
    year: int,
    releases: list[UNTradeDataReleaseInfo],
    fetched: datetime,
    flow: str,
    operation: str,
    data: str | None = None,
) -> UNTradeDataReleaseInfo:
    """The reporter-year's record in the flow's UN release list, else ``NotFoundError``.

    Args:
        reporter_code: The reporter, e.g. ``"IC"``.
        year: The statistical year, e.g. ``2020``, matched as four digits against
            ``statistical_year``.
        releases: The flow's UN release list, one record per reporter and year.
        fetched: When the list was retrieved: the time the client's cache stored it on a
            hit, else the time it arrived (``client.get_answer``).
        flow: ``"exports"`` or ``"imports"``, the list's flow, for the message.
        operation: The release-date operation, for the message.
        data: What was asked for, e.g. ``"re-exports"``; ``None`` for the flow itself.

    Raises:
        NotFoundError: The list has no record for the reporter-year. The message names
            the reporter's listed years, or that it has none, and the latest year and the
            newest release time the list holds for any reporter.
    """
    statistical_year = f"{year:04d}"
    release = next(
        (
            r
            for r in releases
            if r.reporter_code == reporter_code and r.statistical_year == statistical_year
        ),
        None,
    )
    if release is not None:
        return release
    asked = data or flow
    listed = {r.statistical_year for r in releases if r.reporter_code == reporter_code}
    when = (
        f" The release list was fetched at {fetched:%Y-%m-%d %H:%M} UTC and is kept for a "
        "day; a reporter-year released since then is refused until it is fetched again."
    )
    own = (
        f" GATS publishes no UN Trade release list for {asked}: the package checks the {flow} list."
        if asked != flow
        else ""
    )
    if not releases:
        reason = f"{operation} answered with no release"
    else:
        years = "year" if len(listed) == 1 else "years"
        held = (
            f"{operation} lists {len(listed)} {years} of {flow} for reporter {reporter_code}, "
            f"{_years(listed)}"
            if listed
            else f"{operation} lists no year of {flow} for reporter {reporter_code}"
        )
        latest = max(r.statistical_year for r in releases)
        newest = max(r.release_time_stamp for r in releases)
        reason = (
            f"{held}; the latest year it lists for any reporter is {latest}, and its newest "
            f"release time is {newest.isoformat()}"
        )
    raise NotFoundError(
        f"GATS has no UN Trade {asked} for reporter {reporter_code} in {statistical_year}: "
        f"{reason}. GATS answers a reporter-year it has not released with an empty list, "
        f"so the package checks the release list first.{own}{when}",
        source=SOURCE,
    )


async def _un_release(
    product_type: ProductType, reporter_code: str, year: int, data: str | None = None
) -> tuple[UNTradeDataReleaseInfo, datetime]:
    """The reporter-year's record in the UN release list of ``product_type``, and its time.

    The list comes from the client's cache when it holds it, and its time is the cache's
    stored time on a hit, else the time it arrived; ``data`` names what was asked for in
    the refusal, e.g. ``"re-exports"``. See ``_un_release_of``.
    """
    listed = await _un_releases(product_type)
    releases, fetched = listed.payload, listed.retrieved_at
    flow, operation = UN_RELEASE_LISTS[product_type]
    release = _un_release_of(reporter_code, year, releases, fetched, flow, operation, data)
    return release, fetched


def _un_selected(
    records: list[UNTradeRecord], partner_code: str | None, hs6_code: str | None
) -> list[UNTradeRecord]:
    """The records of ``partner_code`` whose HS6 code starts with ``hs6_code``, in order."""
    return [
        record
        for record in records
        if (partner_code is None or record.partner_country_code == partner_code)
        and (hs6_code is None or record.hs6_code.startswith(hs6_code))
    ]


def _un_meta(
    endpoint: str,
    release: UNTradeDataReleaseInfo,
    retrieved_at: datetime,
    reporter_code: str,
    year: int,
    partner_code: str | None,
    hs6_code: str | None,
) -> ResultMeta:
    """``ResultMeta`` of a UN Trade data task: ``vintage`` the reporter-year's release time.

    ``vintage`` is the release record's ``releaseTimeStamp`` as upstream states it, the
    naive time written back with ``isoformat()``: ``"2020-06-03T05:50:46"`` for Iceland's
    2019 exports. ``published_at`` is that time, naive as FAS prints it, with
    ``published_at_naive`` set (sdk-core ADR-0041, decision 2). A filter left ``None`` is
    left out of ``request``. ``retrieved_at`` is the oldest of the call's two reads, the
    release list's and the year's, as the client gives each (conventions §4). A full
    ``hs6_code`` is named by the packaged HS6 list, so an answer without rows names it too;
    a prefix names nothing of its own, and the rows' codes name themselves (``NamedBy``).
    """
    named = HS6_CODES.name_of(hs6_code) if hs6_code is not None else None
    return ResultMeta(
        names={} if named is None else {"hs6_code": {hs6_code: named}},
        source=SOURCE,
        endpoint=endpoint,
        retrieved_at=retrieved_at,
        published_at=release.release_time_stamp,
        published_at_naive=True,
        vintage=release.release_time_stamp.isoformat(),
        request={
            "reporter_code": reporter_code,
            "year": year,
            "partner_code": partner_code,
            "hs6_code": hs6_code,
        },
    )


async def get_un_exports_async(
    reporter_code: str, year: int, partner_code: str | None = None, hs6_code: str | None = None
) -> Result[list[UNTradeRecord]]:
    """One reporter's exports in one year by partner and HS6 code, as UN Comtrade reported them.

    Upstream: "Commodity Export data as reported by UN COMTrade for a given year", at the
    HS6 level. One record per partner and HS6 code, as upstream sends it: ``year``,
    ``reporter_country_code``, ``partner_country_code``, ``hs6_code``, four
    unit-of-measure ids (``list_units_of_measure``), ``quantity1``, ``quantity2`` and
    ``value`` (the snapshot names no currency); 3,980 records for Iceland (``"IC"``) in
    2019, 646 HS6 codes to 115 partners, 1,024 of them in chapter 03. The codes are
    GATS's own, as ``list_countries`` and ``list_hs6_commodities`` list them, not UN
    Comtrade's: the data keeps codes the countries list marks discontinued in 1987, such
    as ``"AS"`` (Australia) and ``"NO"`` (Norway), for later years, never their same-name
    successors (``"A2"``, ``"N3"``). The UN Trade data is frozen: its release lists end
    with statistical year 2019, their newest release on 2021-01-18, as recorded on
    2026-10-26; ``get_un_release_dates`` lists every reporter-year. Two requests: the
    exports release list (``GATSData_GetUNTradeExportDataReleaseInfo``, kept by the
    client for a day) to check that the reporter-year is listed, then the year
    (``GATSData_GetUNTradeExports``), one answer however large (India's 2016 exports:
    75,919 records, about 17 MB). The arguments are checked before either request, but
    for an ISO or GENC code several listed codes share: an unknown reporter or partner
    code raises ``InvalidRequestError`` naming up to three close codes (``"ISL"`` leads
    to ``"IC"``), or pointing to ``list_countries``; the Census tasks' discontinuation
    check does not apply. A shared ISO or GENC code is refused once the release list is
    read, naming first the codes the list holds as reporters: ``"AUS"`` names ``"AS"``,
    the code the UN data uses, before ``"A2"``; ``"FRA"`` names ``"F1"`` before
    ``"FR"``; unranked when the list cannot be read. A reporter-year the list lacks raises
    ``NotFoundError`` naming the reporter's listed years and the list's latest year; a
    listed reporter-year without exports gives an empty list. ``meta.vintage`` is the
    reporter-year's release time from that list, as upstream states it
    (``"2020-06-03T05:50:46"`` for Iceland 2019); ``meta.published_at`` is that time,
    without a zone as FAS prints it, and ``meta.published_at_naive`` says so.

    Args:
        reporter_code: The reporting country, GATS's two-character code, not ISO, as
            ``list_countries`` lists it, e.g. ``"IC"`` (Iceland), ``"IN"`` (India,
            upstream's example, to 2016), ``"AS"`` (Australia, to 2016).
        year: The statistical year, four digits, e.g. ``2019``; the release lists run
            from 1989 to 2019.
        partner_code: Keep only the records of this partner, a code ``list_countries``
            lists, e.g. ``"US"`` (United States, 298 of Iceland's 2019 records), ``"NO"``
            (Norway), ``"15"`` (Areas, not elsewhere specified). ``None`` (the default)
            keeps every partner.
        hs6_code: Keep only the products whose HS6 code starts with this, 1 to 6 digits
            as text: a full code ``list_hs6_commodities`` lists, such as ``"030444"``
            (Codlet Fillets Frh/Ch), or a prefix such as ``"03"`` for chapter 03 or
            ``"0304"`` for a heading. ``None`` (the default) keeps every product. Both
            filters apply after the one data request.
    """
    await _un_ranked(
        ProductType.X,
        lambda reporters: _un_check(reporter_code, year, partner_code, hs6_code, reporters),
    )
    release, listed_at = await _un_release(ProductType.X, reporter_code, year)
    answer = await api.get_un_trade_exports(reporter_code, f"{year:04d}")
    meta = _un_meta(
        "GATSData_GetUNTradeExports",
        release,
        min(listed_at, answer.retrieved_at),
        reporter_code,
        year,
        partner_code,
        hs6_code,
    )
    return Result(data=_un_selected(answer.payload, partner_code, hs6_code), meta=meta)


async def get_un_imports_async(
    reporter_code: str, year: int, partner_code: str | None = None, hs6_code: str | None = None
) -> Result[list[UNTradeRecord]]:
    """One reporter's imports in one year by partner and HS6 code, as UN Comtrade reported them.

    Upstream: "Commodity Import data as reported by UN COMTrade for a given year", at the
    HS6 level. One record per partner and HS6 code, the eleven fields of an export record
    (``get_un_exports``); 2,377 records for Sao Tome and Principe (``"TP"``) in 2019,
    1,026 HS6 codes and 58 partners, 957 of the records with Portugal (``"PO"``) as
    partner. A large reporter answers far more: Iceland's 2019 imports are 23,396
    records, about 5.2 MB of JSON. The codes are GATS's own, not UN Comtrade's, as for
    the exports. The UN Trade data is frozen at statistical year 2019, last released on
    2021-01-18, as recorded on 2026-10-26. Two requests: the
    imports release list (``GATSData_GetUNTradeImportDataReleaseInfo``, kept by the client
    for a day), then the year (``GATSData_GetUNTradeImports``). The imports list is not
    the exports list: 68 reporter-years are listed only for imports, 32 only for exports.
    The arguments are checked as for ``get_un_exports``, membership only and before
    either request, but for an ISO code several listed codes share, refused once the
    imports list is read, its reporters named first (``"NOR"`` names ``"NO"`` before
    ``"N3"``). A reporter-year the imports list lacks raises ``NotFoundError`` naming the
    reporter's listed years; a listed reporter-year without imports gives an empty list.
    ``meta.vintage`` is the reporter-year's release time from that list
    (``"2020-07-16T01:15:37"`` for Sao Tome and Principe 2019); ``meta.published_at`` is
    that time, naive (``meta.published_at_naive``).

    Args:
        reporter_code: The reporting country, GATS's two-character code, not ISO, as
            ``list_countries`` lists it, e.g. ``"TP"`` (Sao Tome and Principe), ``"IC"``
            (Iceland), ``"AS"`` (Australia, to 2018).
        year: The statistical year, four digits, e.g. ``2019``; the release lists run
            from 1989 to 2019.
        partner_code: Keep only the records of this partner, a code ``list_countries``
            lists, e.g. ``"PO"`` (Portugal), ``"CH"`` (China), ``"F1"`` (France).
            ``None`` (the default) keeps every partner.
        hs6_code: Keep only the products whose HS6 code starts with this, 1 to 6 digits
            as text: a full code ``list_hs6_commodities`` lists, such as ``"100630"``
            (Rice, Semi-Milled), or a prefix such as ``"10"`` for chapter 10 or ``"1006"``
            for a heading. ``None`` (the default) keeps every product. Both filters apply
            after the one data request.
    """
    await _un_ranked(
        ProductType.M,
        lambda reporters: _un_check(reporter_code, year, partner_code, hs6_code, reporters),
    )
    release, listed_at = await _un_release(ProductType.M, reporter_code, year)
    answer = await api.get_un_trade_imports(reporter_code, f"{year:04d}")
    meta = _un_meta(
        "GATSData_GetUNTradeImports",
        release,
        min(listed_at, answer.retrieved_at),
        reporter_code,
        year,
        partner_code,
        hs6_code,
    )
    return Result(data=_un_selected(answer.payload, partner_code, hs6_code), meta=meta)


async def get_un_reexports_async(
    reporter_code: str, year: int, partner_code: str | None = None, hs6_code: str | None = None
) -> Result[list[UNTradeRecord]]:
    """One reporter's re-exports in one year by partner and HS6 code, as UN Comtrade reported them.

    Upstream: "Commodity Re-Export data as reported by UN COMTrade for a given year", at
    the HS6 level. One record per partner and HS6 code, the eleven fields of an export
    record (``get_un_exports``); 421 records for Macau (``"MC"``) in 2019, every quantity
    0, 27 of them to ``"AS"`` (Australia, a code the countries list marks discontinued in
    1987, kept by the UN data). Iceland, listed for 2019 exports, answers an empty list
    for its 2019 re-exports. The UN Trade data is frozen at statistical year 2019, last
    released on 2021-01-18, as recorded on 2026-10-26. Two requests: the exports release list
    (``GATSData_GetUNTradeExportDataReleaseInfo``, kept by the client for a day), then
    the year (``GATSData_GetUNTradeReExports``). Upstream publishes no UN re-export
    release list, so the package checks the exports list, by assumption, as the Census
    re-export tasks do: a reporter-year it lacks raises ``NotFoundError`` naming the
    reporter's listed export years, and ``meta.vintage`` is that list's release time for
    the reporter-year (``"2020-06-03T05:51:31"`` for Macau 2019), the exports' release,
    not one the re-exports state. The arguments are checked as for ``get_un_exports``,
    membership only and before either request, but for an ISO code several listed codes
    share, refused once the exports list is read, its reporters named first. A listed
    reporter-year without re-exports gives an empty list; ``meta.published_at`` is the
    release time, naive (``meta.published_at_naive``).

    Args:
        reporter_code: The reporting country, GATS's two-character code, not ISO, as
            ``list_countries`` lists it, e.g. ``"MC"`` (Macau), ``"IC"`` (Iceland),
            ``"IN"`` (India, upstream's example, to 2016).
        year: The statistical year, four digits, e.g. ``2019``; the release lists run
            from 1989 to 2019.
        partner_code: Keep only the records of this partner, a code ``list_countries``
            lists, e.g. ``"HK"`` (Hong Kong), ``"CH"`` (China), ``"AS"`` (Australia).
            ``None`` (the default) keeps every partner.
        hs6_code: Keep only the products whose HS6 code starts with this, 1 to 6 digits
            as text: a full code ``list_hs6_commodities`` lists, such as ``"220421"``
            (Grape Wines , < 2L), or a prefix such as ``"22"`` for chapter 22 or ``"2204"``
            for a heading. ``None`` (the default) keeps every product. Both filters apply
            after the one data request.
    """
    await _un_ranked(
        ProductType.X,
        lambda reporters: _un_check(reporter_code, year, partner_code, hs6_code, reporters),
    )
    release, listed_at = await _un_release(ProductType.X, reporter_code, year, "re-exports")
    answer = await api.get_un_trade_re_exports(reporter_code, f"{year:04d}")
    meta = _un_meta(
        "GATSData_GetUNTradeReExports",
        release,
        min(listed_at, answer.retrieved_at),
        reporter_code,
        year,
        partner_code,
        hs6_code,
    )
    return Result(data=_un_selected(answer.payload, partner_code, hs6_code), meta=meta)


def _un_release_dates_check(
    reporter_code: str | None, year: int | None, reporters: frozenset[str] | None = None
) -> None:
    """The filters of ``get_un_release_dates``, those given; ``reporters`` as for ``_un_check``."""
    if reporter_code is not None:
        validate_reporter_code(reporter_code, reporters=reporters)
    if year is not None:
        validate_year(year)


async def get_un_release_dates_async(
    product_type: ProductType, reporter_code: str | None = None, year: int | None = None
) -> Result[list[UNTradeDataReleaseInfo]]:
    """When GATS last released each reporter-year of UN Trade exports or imports: the coverage.

    One record per reporter and statistical year, newest year first and reporters in code
    order within a year: ``statistical_year`` (``"2019"``), ``product_type``,
    ``reporter_code`` and ``release_time_stamp``, the time of the reporter-year's latest
    release as upstream states it, without a time zone (``2020-06-03T05:50:46`` for
    Iceland's 2019 exports). The UN Trade feed is frozen: as recorded on 2026-10-26 the
    lists cover 1989 to 2019: 3,796 exports records for 206 reporters and 3,832 imports
    records for 207, 32 reporters for 2019 in each; the newest release time is 2021-01-18
    (the Netherlands' 2014), and no reporter-year has been released since. The two lists
    differ: 32 reporter-years are listed only for exports, 68 only for imports. The three UN data
    tasks check a reporter-year against this list and give its time as ``meta.vintage``,
    the re-exports task the exports list's, since re-exports have no list of their own.
    One request, kept by the client for a day, since the feed is frozen;
    ``meta.retrieved_at`` is when it was fetched. ``meta.published_at`` and
    ``meta.vintage`` stay empty: the list is no single release. The filters apply after
    the request.

    Args:
        product_type: Which list, by upstream's ``productType`` code: ``"X"`` exports
            (``GATSData_GetUNTradeExportDataReleaseInfo``), ``"M"`` imports
            (``GATSData_GetUNTradeImportDataReleaseInfo``).
        reporter_code: Keep only this reporter's years, GATS's two-character code as
            ``list_countries`` lists it, e.g. ``"IC"`` (Iceland, 31 years, 1989 to
            2019), ``"MC"`` (Macau, 12 years), ``"IN"`` (India, to 2016). Checked
            against the packaged list, membership only; an ISO code several listed
            codes share is refused naming first the code the list holds (``"AUS"``
            names ``"AS"``). ``None`` (the default) keeps every reporter.
        year: Keep only this statistical year, four digits, e.g. ``2019`` (32
            reporters), ``2016``. ``None`` (the default) keeps every year.
    """
    code = _product_type(product_type)
    await _un_ranked(
        code, lambda reporters: _un_release_dates_check(reporter_code, year, reporters)
    )
    listed = await _un_releases(code)
    releases, retrieved_at = listed.payload, listed.retrieved_at
    statistical_year = None if year is None else f"{year:04d}"
    selected = [
        r
        for r in releases
        if (reporter_code is None or r.reporter_code == reporter_code)
        and (statistical_year is None or r.statistical_year == statistical_year)
    ]
    meta = ResultMeta(
        source=SOURCE,
        endpoint=UN_RELEASE_LISTS[code][1],
        retrieved_at=retrieved_at,
        request={"product_type": code.value, "reporter_code": reporter_code, "year": year},
    )
    return Result(data=selected, meta=meta)


def _search(search: str | None) -> str | None:
    """``search`` unchanged, or ``InvalidRequestError`` when it is neither text nor ``None``."""
    if search is not None and not isinstance(search, str):
        raise InvalidRequestError(
            f"search must be text, got {search!r}. Nothing was sent.", source=SOURCE
        )
    return search


async def list_regions_async() -> Result[list[Region]]:
    """List GATS's regions with their codes, the values region_code of list_countries takes.

    Answered from ``GATSData_GetRegions`` as packaged with this version
    (``reference/regions.json``), without an upstream call: 15 regions when packaged, in
    upstream order, from ``"R05"`` North America, ``"R10"`` Caribbean and ``"R25"``
    European Union-27 to ``"R40"`` East Asia, ``"R70"`` Oceania and ``"R99"``
    Miscellaneous Designated Areas. Every country's ``region_code`` is one of them.
    ``meta.retrieved_at`` is when the package fetched the list (2026-10-28);
    ``meta.vintage`` stays empty.
    """
    packaged = PackagedList.load(PACKAGE, "regions")
    regions = packaged.parse(Region, source=SOURCE)
    return Result(data=regions, meta=packaged.meta(SOURCE))


async def list_countries_async(
    region_code: str | None = None, search: str | None = None
) -> Result[list[Country]]:
    """List GATS's countries with their codes and regions, the values partner_code takes.

    Answered from ``GATSData_GetCountries`` as packaged with this version
    (``reference/countries.json``), without an upstream call: 322 codes when packaged,
    current and discontinued, in upstream order, each with its region (``list_regions``),
    its ISO code and its GENC code where upstream has one. Codes are GATS's own, not ISO:
    ``"CH"`` China, ``"MX"`` Mexico, ``"JA"`` Japan, ``"IC"`` Iceland; aggregates such as
    ``"01"`` Caribbean,nes have no GENC code. 26 carry a ``discontinued_on`` month. For
    the 7 that are no other record's ``country_parent_code`` it is the last a Census task
    accepts (``"D1"`` Denmark, ``"198712"``); the 19 parents among them pass for every
    month (``"SZ"`` Switzerland, the parent of ``"SR"`` Switzerland and ``"LS"``
    Liechtenstein). ``meta.retrieved_at`` is when the package fetched the list
    (2026-10-28); ``meta.vintage`` stays empty.

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
    packaged = PackagedList.load(PACKAGE, "countries")
    selected = [
        c
        for c in packaged.parse(Country, source=SOURCE)
        if (region_code is None or c.region_code == region_code)
        and matches(search, c.country_code, c.country_name, c.iso3_code, c.genc_code)
    ]
    request = {"region_code": region_code, "search": search}
    return Result(data=selected, meta=packaged.meta(SOURCE, request=request))


async def list_hs6_commodities_async(
    search: str | None = None, hs6_code: str | None = None
) -> Result[list[HS6Commodity]]:
    """List GATS's HS6 commodities with their codes, names and units of measure.

    Answered from ``GATSData_GetHS6Commodities`` as packaged with this version
    (``reference/HS6Commodities.json``), without an upstream call: 2,909 codes when
    packaged, in code order, e.g. ``"020110"`` Bovine Carcass Fr/Ch, ``"100190"`` Wheat,
    except Durum; each with a name, a description and four unit-of-measure ids
    (``list_units_of_measure``). Upstream: "Use this to correlate the Import, Export and
    Re-export data records obtained by querying UN Trade Data"; the first six digits of
    every HS10 code in the Census records are a listed code. For HS10 codes use
    ``list_commodities``. ``meta.retrieved_at`` is when the package fetched the list
    (2026-10-28); ``meta.vintage`` stays empty. The filters only select codes, in code
    order.

    Args:
        search: Keep the commodities where this text occurs, ignoring case, in the code,
            the name or the description, e.g. ``"wheat"`` (15 codes, durum and other
            wheat, wheat flour, buckwheat), ``"0201"`` (the three codes of heading 0201,
            bovine meat fresh or chilled), ``"bovine"``. Omit (``None``) for all.
        hs6_code: Keep the codes that start with this, 1 to 6 digits as text: a full
            code such as ``"100190"`` or a prefix such as ``"0201"`` (heading 0201, three
            codes) or ``"02"`` (chapter 02, 81 codes). A prefix no code starts with
            yields an empty list. Omit (``None``) for all.
    """
    _search(search)
    if hs6_code is not None:
        validate_hs6_prefix(
            hs6_code, hint="search finds the codes by name or description, e.g. 'wheat'."
        )
    packaged = PackagedList.load(PACKAGE, "HS6Commodities")
    selected = [
        c
        for c in packaged.parse(HS6Commodity, source=SOURCE)
        if (hs6_code is None or c.hs6_code.startswith(hs6_code))
        and matches(search, c.hs6_code, c.commodity_name, c.commodity_description)
    ]
    request = {"search": search, "hs6_code": hs6_code}
    return Result(data=selected, meta=packaged.meta(SOURCE, request=request))


async def list_units_of_measure_async() -> Result[list[UnitOfMeasure]]:
    """List GATS's units of measure with their ids, the unit ids of every data record.

    Answered from ``GATSData_GetUnitsOfMeasure`` as packaged with this version
    (``reference/unitsOfMeasure.json``), without an upstream call: 108 units when
    packaged, ids ``0`` to ``107`` in order, e.g. ``47`` Kilograms (``KG``), ``70``
    Metric Tons (``MT``), ``78`` Numbers (``NO``), ``0`` NONE. The ``census_uom_id1``,
    ``census_uom_id2``, ``fas_converted_uom_id`` and ``fas_non_converted_uom_id`` of the
    Census and commodity records are these ids; ``enums.UnitOfMeasureId`` names the same
    ids (``UnitOfMeasureId.KILOGRAMS``). A code is not unique: ``"CRT"`` (Crates) is 33
    and 105. ``meta.retrieved_at`` is when the package fetched the list (2026-10-28);
    ``meta.vintage`` stays empty.
    """
    packaged = PackagedList.load(PACKAGE, "unitsOfMeasure")
    units = packaged.parse(UnitOfMeasure, source=SOURCE)
    return Result(data=units, meta=packaged.meta(SOURCE))


async def list_customs_districts_async() -> Result[list[CustomsDistrict]]:
    """List the US customs districts with their ids, the customs_district_id values.

    Answered from ``GATSData_GetCustomsDistricts`` as packaged with this version
    (``reference/customsDistricts.json``), without an upstream call: 53 districts when
    packaged, ids ``0`` to ``99`` in order with gaps, e.g. ``10`` NEW YORK, N.Y., ``30``
    SEATTLE, WASH., ``52`` MIAMI, FLA., each with its region, one of five (``"EC"`` EAST
    COAST DISTRICTS, ``"GL"``, ``"GP"``, ``"WC"``, ``"OP"``). Upstream: "US Customs
    Districts, the point of Entry and Exit for the Commodity Imports and Exports". Id
    ``0`` is Z UNKNOW CDIST CODES; ``60``, ``70``, ``80`` and ``99`` are vessels,
    shipments under $251, mail and military shipments. ``meta.retrieved_at`` is when the
    package fetched the list (2026-10-28); ``meta.vintage`` stays empty.
    """
    packaged = PackagedList.load(PACKAGE, "customsDistricts")
    districts = packaged.parse(CustomsDistrict, source=SOURCE)
    return Result(data=districts, meta=packaged.meta(SOURCE))


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
    for its size: one request, kept by the client for a day and parsed into records once
    for it, so a search after the first sends nothing and builds no records anew;
    ``meta.retrieved_at`` is when the list was fetched. ``meta.vintage``
    and ``meta.published_at`` stay empty: upstream gives the list no version or date. The
    filters apply after the one request; for HS6 codes use ``list_hs6_commodities``.

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
    listed = await api.get_commodities()
    commodities, retrieved_at = listed.payload, listed.retrieved_at
    selected = [
        c
        for c in commodities
        if (hs10_code is None or c.hs10_code.startswith(hs10_code))
        and (product_type is None or c.product_type == product_type)
        and matches(search, c.commodity_name, c.commodity_description)
    ]
    meta = ResultMeta(
        source=SOURCE,
        endpoint="GATSData_GetCommodities",
        retrieved_at=retrieved_at,
        request={"search": search, "hs10_code": hs10_code, "product_type": product_type},
    )
    return Result(data=selected, meta=meta)


get_census_export_series = names_codes(partner_code=COUNTRIES)(sync(get_census_export_series_async))
get_census_exports = names_codes(partner_code=COUNTRIES)(sync(get_census_exports_async))
get_census_import_series = names_codes(partner_code=COUNTRIES)(sync(get_census_import_series_async))
get_census_imports = names_codes(partner_code=COUNTRIES)(sync(get_census_imports_async))
get_census_reexport_series = names_codes(partner_code=COUNTRIES)(
    sync(get_census_reexport_series_async)
)
get_census_reexports = names_codes(partner_code=COUNTRIES)(sync(get_census_reexports_async))
get_census_release_dates = sync(get_census_release_dates_async)
get_customs_district_exports = names_codes(partner_code=COUNTRIES, customs_district_id=DISTRICTS)(
    sync(get_customs_district_exports_async)
)
get_customs_district_imports = names_codes(partner_code=COUNTRIES, customs_district_id=DISTRICTS)(
    sync(get_customs_district_imports_async)
)
get_customs_district_reexports = names_codes(partner_code=COUNTRIES, customs_district_id=DISTRICTS)(
    sync(get_customs_district_reexports_async)
)
get_un_exports = names_codes(reporter_code=COUNTRIES, partner_code=COUNTRIES)(
    sync(get_un_exports_async)
)
get_un_imports = names_codes(reporter_code=COUNTRIES, partner_code=COUNTRIES)(
    sync(get_un_imports_async)
)
get_un_reexports = names_codes(reporter_code=COUNTRIES, partner_code=COUNTRIES)(
    sync(get_un_reexports_async)
)
get_un_release_dates = names_codes(reporter_code=COUNTRIES)(sync(get_un_release_dates_async))
list_commodities = sync(list_commodities_async)
list_countries = sync(list_countries_async)
list_customs_districts = sync(list_customs_districts_async)
list_hs6_commodities = sync(list_hs6_commodities_async)
list_regions = sync(list_regions_async)
list_units_of_measure = sync(list_units_of_measure_async)
