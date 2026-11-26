"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Each task that sends a request has a live smoke test, fifteen of the twenty tasks: the six
Census data tasks, the three series, ``get_census_release_dates``, the three UN Trade data
tasks, ``get_un_release_dates`` and ``list_commodities``. Each data task spends one call for
its month or year, and its release list once per flow and program: the tests share the
client's cache, so ``get_census_exports`` fetches the Census exports list and
``get_census_imports`` the imports list, and ``get_census_release_dates``, the re-export
tasks, the customs-district tasks and the three series answer their check from the cache;
``get_un_exports`` and ``get_un_imports`` fetch the two UN Trade lists, and
``get_un_reexports`` and ``get_un_release_dates`` answer from them. The export series asks
for Iceland from June to August 2026, three data calls, the import and re-export series from
July to August, two data calls each. The Census data tasks ask for Iceland (``"IC"``), a
listed partner with modest trade, so the nightly run stays light, in August 2026, released on
2026-10-06; ``vintage`` is that month's release time as upstream writes it, a date and a time
without a zone. The UN Trade tasks ask for the reporter-years the fixtures hold, all of
statistical year 2019: Iceland's exports of chapter 03, Sao Tome and Principe's imports,
Macau's re-exports, and Iceland's years in the exports release list. The UN Trade feed is
frozen, its newest release dated 2021-01-18 as recorded on 2026-10-26, so these tests assert
what the answers show, codes from the packaged lists included, and never newer data.
``list_commodities`` fetches the HS10 list live, one call of about 7.6 MB.

The five other list tasks, ``list_regions``, ``list_countries``, ``list_hs6_commodities``,
``list_units_of_measure`` and ``list_customs_districts``, answer from the packaged lists and
send no request, so no live test calls them: their data is held against upstream by core's
nightly comparison of the packaged lists, which fetches each list of ``LIVE_LISTS`` through
its wrapper, one keyed call each, and fails on a code gone, new or changed, naming the codes
and never a record (sdk-core ADR-0055), the signal to run ``/refresh-reference-data``. The
tests record what they answered as test properties (``--junitxml`` shows them), never a key.
Core's testing plugin prints the run's requests as ``requests sent by the live run: <n>``,
the count in the log of ``live.yml`` that ``/release-prep`` cites; core's response cache
answers a second read of a path within its lifetime, so the run sends fewer requests than
its calls.
"""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from xippios.core import PackagedCodes, PackagedList, ResultMeta
from xippios.core.testing.live import *  # noqa: F403
from xippios.usda.fas import Gateway

from xippios.usda.gats import api, tasks
from xippios.usda.gats._client import SOURCE
from xippios.usda.gats.models import ProductType
from xippios.usda.gats.params import PACKAGE, validate_partner_code


def _codes(name: str, code: str, label: str) -> PackagedCodes:
    """The packaged list ``name`` declared by its code field and its name field."""
    return PackagedList.load(PACKAGE, name).codes(code, label, source=SOURCE)


LIVE_LISTS = {  # each packaged list compared, by its file reference/<name>.json
    "regions": (_codes("regions", "regionCode", "regionName"), api.get_regions),
    "countries": (_codes("countries", "countryCode", "countryName"), api.get_countries),
    "HS6Commodities": (
        _codes("HS6Commodities", "hS6Code", "commodityName"),
        api.get_hs6_commodities,
    ),
    "unitsOfMeasure": (
        _codes("unitsOfMeasure", "unitOfMeasureId", "unitOfMeasureName"),
        api.get_units_of_measure,
    ),
    "customsDistricts": (
        _codes("customsDistricts", "customsDistrictId", "customsDistrictName"),
        api.get_customs_districts,
    ),
}
NO_LIVE_LIST: dict[str, str] = {}  # every packaged list is compared

pytestmark = [pytest.mark.live, pytest.mark.anyio]

PARTNER = validate_partner_code("IC")  # Iceland, in the packaged countries list
YEAR, MONTH = 2026, 8
RELEASE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def _vintage_is_a_release_time(vintage: str | None) -> None:
    assert vintage is not None
    assert RELEASE_TIME.match(vintage), vintage


def _published_naive(meta: ResultMeta) -> None:
    """``published_at`` is the time ``vintage`` names, without a zone, flagged naive."""
    assert meta.vintage is not None
    assert meta.published_at == datetime.fromisoformat(meta.vintage)
    assert meta.published_at_naive is True


def _quota_is_the_gateways() -> None:
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert snapshot.limit == 1000


async def test_get_census_exports_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_census_exports_async(PARTNER, YEAR, MONTH)
    assert result.data
    assert {(r.country_code, r.date) for r in result.data} == {(PARTNER, "202608")}
    _vintage_is_a_release_time(result.meta.vintage)
    _published_naive(result.meta)
    _quota_is_the_gateways()
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


async def test_get_census_imports_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_census_imports_async(PARTNER, YEAR, MONTH)
    assert result.data
    assert {(r.country_code, r.date) for r in result.data} == {(PARTNER, "202608")}
    _vintage_is_a_release_time(result.meta.vintage)
    _published_naive(result.meta)
    _quota_is_the_gateways()
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


async def test_get_census_release_dates_live(
    record_property: Callable[[str, object], None],
) -> None:
    result = await tasks.get_census_release_dates_async(ProductType.X)
    months = [r.statistical_year_month for r in result.data]
    assert max(months) >= "202608"
    assert min(months) == "196701"
    assert months == sorted(months, reverse=True), "newest first"
    assert {r.product_type for r in result.data} == {ProductType.X}
    assert (result.meta.published_at, result.meta.vintage) == (None, None)
    # The filter answers from the client's cache: no keyed call of its own.
    one_year = await tasks.get_census_release_dates_async(
        ProductType.X, statistical_year_month=f"{YEAR}"
    )
    year_months = [r.statistical_year_month for r in one_year.data]
    assert year_months == [month for month in months if month[:4] == f"{YEAR}"]
    assert 8 <= len(year_months) <= 12
    record_property("latest", months[0])
    record_property("released", result.data[0].release_time_stamp.isoformat())


async def test_get_census_reexports_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_census_reexports_async(PARTNER, YEAR, MONTH)
    assert {(r.country_code, r.date) for r in result.data} <= {(PARTNER, "202608")}
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.endpoint == "GATSData_GetCensusReExports"
    _published_naive(result.meta)
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


async def test_get_census_export_series_live(
    record_property: Callable[[str, object], None],
) -> None:
    """June to August 2026: three data calls, the exports list from the cache."""
    result = await tasks.get_census_export_series_async(
        PARTNER, start_year=YEAR, start_month=6, end_year=YEAR, end_month=MONTH
    )
    assert result.data
    dates = [r.date for r in result.data]
    assert dates == sorted(dates), "month order, oldest first"
    assert set(dates) <= {"202606", "202607", "202608"}
    assert {r.country_code for r in result.data} == {PARTNER}
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.endpoint == "GATSData_GetCensusExports"
    _published_naive(result.meta)
    record_property("records", len(result.data))
    record_property("months", sorted(set(dates)))
    record_property("vintage", result.meta.vintage)


async def test_get_census_import_series_live(
    record_property: Callable[[str, object], None],
) -> None:
    """July and August 2026: two data calls, the imports list from the cache."""
    result = await tasks.get_census_import_series_async(
        PARTNER, start_year=YEAR, start_month=7, end_year=YEAR, end_month=MONTH
    )
    assert result.data
    dates = [r.date for r in result.data]
    assert dates == sorted(dates), "month order, oldest first"
    assert set(dates) <= {"202607", "202608"}
    assert {r.country_code for r in result.data} == {PARTNER}
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.endpoint == "GATSData_GetCensusImport"
    _published_naive(result.meta)
    record_property("records", len(result.data))
    record_property("months", sorted(set(dates)))
    record_property("vintage", result.meta.vintage)


async def test_get_census_reexport_series_live(
    record_property: Callable[[str, object], None],
) -> None:
    """July and August 2026: two data calls, the exports list from the cache. A month
    may hold no re-exports, so the records may be none."""
    result = await tasks.get_census_reexport_series_async(
        PARTNER, start_year=YEAR, start_month=7, end_year=YEAR, end_month=MONTH
    )
    dates = [r.date for r in result.data]
    assert dates == sorted(dates), "month order, oldest first"
    assert {(r.country_code, r.date) for r in result.data} <= {
        (PARTNER, "202607"),
        (PARTNER, "202608"),
    }
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.endpoint == "GATSData_GetCensusReExports"
    _published_naive(result.meta)
    record_property("records", len(result.data))
    record_property("months", sorted(set(dates)))
    record_property("vintage", result.meta.vintage)


def _districts() -> set[int]:
    packaged = PackagedList.load(PACKAGE, "customsDistricts")
    return {int(record["customsDistrictId"]) for record in packaged.records}


@pytest.mark.parametrize(
    ("task", "endpoint"),
    [
        ("get_customs_district_exports", "GATSData_GetCustomsDistrictsExports"),
        ("get_customs_district_imports", "GATSData_GetCustomsDistrictsImports"),
        ("get_customs_district_reexports", "GATSData_GetCustomsDistrictsReExports"),
    ],
)
async def test_customs_district_task_live(
    task: str, endpoint: str, record_property: Callable[[str, object], None]
) -> None:
    result = await getattr(tasks, f"{task}_async")(PARTNER, YEAR, MONTH)
    assert {(r.country_code, r.date) for r in result.data} <= {(PARTNER, "202608")}
    districts = {r.customs_district_id for r in result.data}
    assert districts <= _districts(), "every district is packaged"
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.endpoint == endpoint
    _published_naive(result.meta)
    record_property("records", len(result.data))
    record_property("districts", sorted(districts))
    record_property("vintage", result.meta.vintage)


async def test_list_commodities_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.list_commodities_async(search="wheat")
    assert result.data
    assert all(
        "wheat" in f"{c.commodity_name} {c.commodity_description or ''}".casefold()
        for c in result.data
    )
    assert {c.product_type for c in result.data} <= {"X", "M", "T", "B"}
    assert (result.meta.vintage, result.meta.published_at) == (None, None)
    assert result.meta.endpoint == "GATSData_GetCommodities"
    record_property("records", len(result.data))


UN_YEAR = 2019
"""The UN Trade feed's latest statistical year, as both release lists end on 2026-10-26."""


def _listed(name: str, field: str) -> set[str]:
    packaged = PackagedList.load(PACKAGE, name)
    return {str(record[field]) for record in packaged.records}


def _in_gats_vocabulary(records: list[Any]) -> None:
    """Every reporter, partner and HS6 code is a code of the packaged lists: GATS's own."""
    countries = _listed("countries", "countryCode")
    assert {r.reporter_country_code for r in records} <= countries
    assert {r.partner_country_code for r in records} <= countries
    assert {r.hs6_code for r in records} <= _listed("HS6Commodities", "hS6Code")


@pytest.mark.parametrize(
    ("task", "reporter_code", "hs6_code", "endpoint"),
    [
        ("get_un_exports", "IC", "03", "GATSData_GetUNTradeExports"),
        ("get_un_imports", "TP", None, "GATSData_GetUNTradeImports"),
        ("get_un_reexports", "MC", None, "GATSData_GetUNTradeReExports"),
    ],
    ids=["exports_IC_chapter_03", "imports_TP", "re_exports_MC"],
)
async def test_un_data_task_live(
    task: str,
    reporter_code: str,
    hs6_code: str | None,
    endpoint: str,
    record_property: Callable[[str, object], None],
) -> None:
    result = await getattr(tasks, f"{task}_async")(reporter_code, UN_YEAR, hs6_code=hs6_code)
    assert result.data
    assert {(r.year, r.reporter_country_code) for r in result.data} == {("2019", reporter_code)}
    if hs6_code is not None:
        assert all(r.hs6_code.startswith(hs6_code) for r in result.data)
    _in_gats_vocabulary(result.data)
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.endpoint == endpoint
    _published_naive(result.meta)
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


async def test_get_un_release_dates_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_un_release_dates_async(ProductType.X, reporter_code="IC")
    years = [r.statistical_year for r in result.data]
    assert str(UN_YEAR) in years
    assert years == sorted(years, reverse=True), "newest first"
    assert {(r.reporter_code, r.product_type) for r in result.data} == {("IC", ProductType.X)}
    assert (result.meta.published_at, result.meta.vintage) == (None, None)
    record_property("years", len(years))
    record_property("latest", years[0])
    record_property("released", result.data[0].release_time_stamp.isoformat())
