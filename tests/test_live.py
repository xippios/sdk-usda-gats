"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

One live smoke test per task function, twenty tasks in all, twenty-six keyed calls.
Each data task spends one call for its month or year, and its release list once per flow
and program: the tests share the client's cache, so ``get_census_exports`` fetches the
Census exports list and ``get_census_imports`` the imports list, and
``get_census_release_dates``, the re-export tasks, the customs-district tasks and the
three series answer their check from the cache; ``get_un_exports`` and
``get_un_imports`` fetch the two UN Trade lists, and ``get_un_reexports`` and
``get_un_release_dates`` answer from them. The export series asks for Iceland from June
to August 2026, three data calls, the import and re-export series from July to August,
two data calls each.
The Census data tasks ask for Iceland (``"IC"``), a listed partner with modest trade, so the
nightly run stays light, in August 2026, released on 2026-10-06; ``vintage`` is that
month's release time as upstream writes it, a date and a time without a zone. The UN
Trade tasks ask for the reporter-years the fixtures hold, all of statistical year 2019:
Iceland's exports of chapter 03, Sao Tome and Principe's imports, Macau's re-exports, and
Iceland's years in the exports release list. The UN Trade feed is frozen, its newest
release dated 2021-01-18 as recorded on 2026-10-26, so these tests assert what the
answers show, codes from the packaged lists included, and never newer data. The five
packaged lists answer without a call, so their test fetches each list through its
endpoint wrapper, one call each, and checks that the packaged records equal it: the
freshness check ``reference/README.md`` promises. A difference fails the test naming what
is gone and what is new; ``/refresh-reference-data`` then refreshes the package.
``list_commodities`` fetches the HS10 list live, one call of about 7.6 MB. The tests
record what they answered as test properties (``--junitxml`` shows them), never a key.
Next to them, the template's reachability check, ``test_upstream_answers``, sends no key:
a plain request to ``BASE_URL`` that spends no quota call.
"""

import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest
from xippios.core import PackagedList, ResultMeta, UpstreamModel
from xippios.core.data_gov import Gateway

from xippios.usda.gats import api, tasks
from xippios.usda.gats._client import BASE_URL, config
from xippios.usda.gats.models import ProductType
from xippios.usda.gats.params import PACKAGE, validate_partner_code

pytestmark = [pytest.mark.live, pytest.mark.anyio]

PARTNER = validate_partner_code("IC")  # Iceland, in the packaged countries list
YEAR, MONTH = 2026, 8
RELEASE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


async def test_upstream_answers() -> None:
    """The base URL answers without a server error (sdk-template's reachability check).

    A plain request, not the package's client, so no key goes out and no call counts
    against the key's quota; a keyed gateway's answer to it (a 403 or a 404, say) still
    shows the host is up.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        timeout=config.timeouts.to_httpx(),
        follow_redirects=True,
    ) as http:
        response = await http.get(BASE_URL)
    assert response.status_code < 500


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
    result = await tasks.get_census_export_series_async(PARTNER, YEAR, 6, YEAR, MONTH)
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
    result = await tasks.get_census_import_series_async(PARTNER, YEAR, 7, YEAR, MONTH)
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
    result = await tasks.get_census_reexport_series_async(PARTNER, YEAR, 7, YEAR, MONTH)
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


def _keyed(records: list[Any]) -> list[str]:
    """Each record as sorted JSON: comparable by value without a quadratic scan."""
    return [json.dumps(r.model_dump(mode="json"), sort_keys=True) for r in records]


LISTS = [
    ("list_regions", "GATSData_GetRegions"),
    ("list_countries", "GATSData_GetCountries"),
    ("list_hs6_commodities", "GATSData_GetHS6Commodities"),
    ("list_units_of_measure", "GATSData_GetUnitsOfMeasure"),
    ("list_customs_districts", "GATSData_GetCustomsDistricts"),
]


@pytest.mark.parametrize(("task", "endpoint"), LISTS, ids=[task for task, _ in LISTS])
async def test_packaged_list_equals_the_live_list(task: str, endpoint: str) -> None:
    packaged = await getattr(tasks, f"{task}_async")()
    live: list[UpstreamModel] = await getattr(api, endpoint)()
    ours, theirs = _keyed(packaged.data), _keyed(live)
    stale = sorted(set(ours) - set(theirs))
    new = sorted(set(theirs) - set(ours))
    behind = bool(stale or new)
    assert not behind, (
        f"{task} is behind upstream (packaged {packaged.meta.retrieved_at:%Y-%m-%d}): "
        f"{len(stale)} packaged records upstream no longer sends, {len(new)} upstream "
        "records the package lacks; "
        f"first of each: {stale[:5]}, {new[:5]}. Refresh with /refresh-reference-data."
    )
    assert ours == theirs, f"{task}: the same records in another order"
    assert packaged.meta.endpoint == endpoint


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
