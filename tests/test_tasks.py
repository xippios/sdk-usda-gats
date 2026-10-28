"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them.
"""

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from xippios.core import (
    InvalidRequestError,
    NotFoundError,
    RateLimitError,
    ResultMeta,
    UnknownCode,
)
from xippios.core.client import cache_key
from xippios.core.mcp import build_parser, main
from xippios.core.testing import (
    CLOCK_SLACK,
    FixtureResponse,
    ReplayFixture,
    assert_time_between,
    load_fixture,
    mcp_call,
    sent_urls,
)

from xippios.usda.gats import tasks
from xippios.usda.gats._client import BASE_URL, cache
from xippios.usda.gats.mcp import run, server
from xippios.usda.gats.models import DataReleaseInfo, ProductType, UNTradeDataReleaseInfo

FIXTURES = Path(__file__).parent / "fixtures"
EXPORTS = "get_census_exports"
IMPORTS = "get_census_import"
EXPORT_RELEASES = "get_census_export_data_release_info"
IMPORT_RELEASES = "get_census_import_data_release_info"
EXPORT_RELEASES_URL = f"{BASE_URL}/api/gats/census/data/exports/dataReleaseDates"
IMPORT_RELEASES_URL = f"{BASE_URL}/api/gats/census/data/imports/dataReleaseDates"
CH_EXPORTS_URL = f"{BASE_URL}/api/gats/censusExports/partnerCode/CH/year/2026/month/8"
CH_IMPORTS_URL = f"{BASE_URL}/api/gats/censusImports/partnerCode/CH/year/2026/month/8"
RE_EXPORTS = "get_census_re_exports"
DISTRICT_EXPORTS = "get_customs_districts_exports"
DISTRICT_IMPORTS = "get_customs_districts_imports"
DISTRICT_RE_EXPORTS = "get_customs_districts_re_exports"
IC_RE_EXPORTS_URL = f"{BASE_URL}/api/gats/censusReExports/partnerCode/IC/year/2026/month/8"
IC_DISTRICT_EXPORTS_URL = (
    f"{BASE_URL}/api/gats/customsDistrictExports/partnerCode/IC/year/2026/month/8"
)
IC_DISTRICT_IMPORTS_URL = (
    f"{BASE_URL}/api/gats/customsDistrictImports/partnerCode/IC/year/2026/month/8"
)
IC_DISTRICT_RE_EXPORTS_URL = (
    f"{BASE_URL}/api/gats/customsDistrictReExports/partnerCode/IC/year/2026/month/8"
)
DISTRICT_NOTE = (
    "filter by hs10_code, a full code or a prefix such as the chapter '02', or by "
    "customs_district_id, e.g. 10 (NEW YORK, N.Y.), to see the rest"
)
HS10_NOTE = "filter by hs10_code, a full code or a prefix such as the chapter '02', to see the rest"
RELEASE_DATES_NOTE = (
    "the list runs newest first, so the rows shown are the latest released months; "
    "200 months reach back more than sixteen years"
)
RELEASED_2026_08 = "2026-10-06T08:00:00"
"""``releaseTimeStamp`` of ``"202608"`` in both recorded release lists, as upstream wrote it."""


def _published_naive(meta: ResultMeta) -> None:
    """``published_at`` is the release time ``vintage`` names, parsed and kept without a
    zone as FAS prints it, with ``published_at_naive`` set (ADR-0022, rule 2)."""
    assert meta.vintage is not None
    assert meta.published_at == datetime.fromisoformat(meta.vintage)
    assert meta.published_at.tzinfo is None
    assert meta.published_at_naive is True


def _recorded(endpoint: str, case: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = json.loads(
        load_fixture(FIXTURES / endpoint / f"{case}.json").response.body
    )
    return records


def _release_time(endpoint: str, month_code: str) -> object:
    """The month's ``releaseTimeStamp`` in the recorded release list, the text upstream sent."""
    (record,) = [r for r in _recorded(endpoint, "all") if r["statisticalYearMonth"] == month_code]
    return record["releaseTimeStamp"]


def test_get_census_exports(replay_fixture: ReplayFixture) -> None:
    releases = replay_fixture(EXPORT_RELEASES, "all")
    data = replay_fixture(EXPORTS, "CH_2026_8")
    result = tasks.get_census_exports("CH", 2026, 8)
    assert len(result.data) == 777
    first = result.data[0]
    assert (first.hs10_code, first.value, first.quantity1) == (
        "0103910000",
        Decimal("20672.0"),
        Decimal("394.0"),
    )
    assert isinstance(first.value, Decimal)
    assert [r.hs10_code for r in result.data] == [
        r["hS10Code"] for r in _recorded(EXPORTS, "CH_2026_8")
    ], "every record, in upstream order"
    assert result.meta.source == "usda-gats"
    assert result.meta.endpoint == "GATSData_GetCensusExports"
    assert result.meta.request == {
        "partner_code": "CH",
        "year": 2026,
        "month": 8,
    }
    assert result.meta.vintage == RELEASED_2026_08 == _release_time(EXPORT_RELEASES, "202608")
    _published_naive(result.meta)
    assert {r.date for r in result.data} == {"202608"}, "the month is the records' own"
    assert result.meta.total is None
    assert sent_urls(releases) == [EXPORT_RELEASES_URL]
    assert sent_urls(data) == [CH_EXPORTS_URL]


def test_get_census_imports(replay_fixture: ReplayFixture) -> None:
    releases = replay_fixture(IMPORT_RELEASES, "all")
    data = replay_fixture(IMPORTS, "CH_2026_8")
    result = tasks.get_census_imports("CH", 2026, 8)
    assert len(result.data) == 3294
    first = result.data[0]
    assert (first.hs10_code, first.cif_value, first.consumption_cif_value) == (
        "0106199195",
        Decimal("55310.0"),
        Decimal("1166564.0"),
    )
    assert isinstance(first.consumption_value, Decimal)
    assert result.meta.endpoint == "GATSData_GetCensusImport"
    assert result.meta.request == {
        "partner_code": "CH",
        "year": 2026,
        "month": 8,
    }
    assert result.meta.vintage == RELEASED_2026_08 == _release_time(IMPORT_RELEASES, "202608")
    _published_naive(result.meta)
    assert {r.date for r in result.data} == {"202608"}
    assert sent_urls(releases) == [IMPORT_RELEASES_URL]
    assert sent_urls(data) == [CH_IMPORTS_URL]


def test_vintage_is_the_months_release_time_as_upstream_states_it(
    replay_fixture: ReplayFixture,
) -> None:
    """The month's release record carries ``2026-10-06T08:00:00`` without a time zone:
    ``vintage`` is that text, the naive time written back with ``isoformat()``, and
    ``published_at`` the time itself, naive, with ``published_at_naive`` set (ADR-0022,
    rule 2); the month itself is in ``meta.request``."""
    replay_fixture(EXPORT_RELEASES, "all")
    replay_fixture(EXPORTS, "CH_2026_8")
    result = tasks.get_census_exports("CH", 2026, 8)
    _published_naive(result.meta)
    assert (result.meta.request["year"], result.meta.request["month"]) == (2026, 8)
    releases = tasks.get_census_release_dates(ProductType.X)
    august = next(r for r in releases.data if r.statistical_year_month == "202608")
    assert august.release_time_stamp == datetime(2026, 10, 6, 8, 0)
    assert august.release_time_stamp.tzinfo is None
    assert result.meta.vintage == august.release_time_stamp.isoformat() == RELEASED_2026_08


@pytest.mark.parametrize("endpoint", [EXPORT_RELEASES, IMPORT_RELEASES])
def test_isoformat_gives_back_every_recorded_release_time(endpoint: str) -> None:
    """``vintage`` claims upstream's own text: for each of the 716 records of both lists,
    the parsed time written back with ``isoformat()`` is the text upstream sent."""
    records = _recorded(endpoint, "all")
    assert len(records) == 716
    for record in records:
        parsed = DataReleaseInfo.model_validate(record).release_time_stamp
        assert parsed.isoformat() == record["releaseTimeStamp"]


@pytest.mark.parametrize(
    ("hs10_code", "expected"),
    [("02", 26), ("0201", 3), ("0103910000", 1), ("99", 0)],
    ids=["chapter", "heading", "full_code", "no_match"],
)
def test_hs10_code_keeps_the_products_it_starts(
    replay_fixture: ReplayFixture, hs10_code: str, expected: int
) -> None:
    """A prefix keeps a chapter or a heading, a full ten-digit code one product; the
    filter applies after the one data request, which fetched every product."""
    replay_fixture(EXPORT_RELEASES, "all")
    data = replay_fixture(EXPORTS, "CH_2026_8")
    result = tasks.get_census_exports("CH", 2026, 8, hs10_code=hs10_code)
    assert len(result.data) == expected
    assert all(r.hs10_code.startswith(hs10_code) for r in result.data)
    recorded = [
        r for r in _recorded(EXPORTS, "CH_2026_8") if str(r["hS10Code"]).startswith(hs10_code)
    ]
    assert [r.hs10_code for r in result.data] == [r["hS10Code"] for r in recorded]
    assert result.meta.request["hs10_code"] == hs10_code
    assert result.meta.vintage == RELEASED_2026_08
    assert sent_urls(data) == [CH_EXPORTS_URL], "the filter is not sent upstream"


def test_hs10_code_filters_imports_too(replay_fixture: ReplayFixture) -> None:
    replay_fixture(IMPORT_RELEASES, "all")
    replay_fixture(IMPORTS, "CH_2026_8")
    result = tasks.get_census_imports("CH", 2026, 8, hs10_code="02")
    assert [r.hs10_code for r in result.data] == ["0208100000", "0208902500"]
    one = tasks.get_census_imports("CH", 2026, 8, hs10_code="0106199195")
    assert len(one.data) == 1
    assert one.data[0].value == Decimal("1111254.0")


def test_the_release_list_is_fetched_once_for_two_task_calls(
    replay_fixture: ReplayFixture,
) -> None:
    """The client caches the release list for an hour: the second call of the task sends
    only its data request."""
    releases = replay_fixture(EXPORT_RELEASES, "all")
    data = replay_fixture(EXPORTS, "CH_2026_8")
    first = tasks.get_census_exports("CH", 2026, 8)
    second = tasks.get_census_exports("CH", 2026, 8, hs10_code="02")
    assert releases.call_count == 1
    assert data.call_count == 2
    assert sent_urls(data) == [CH_EXPORTS_URL, CH_EXPORTS_URL]
    assert second.meta.retrieved_at >= first.meta.retrieved_at - CLOCK_SLACK, (
        "the data is fetched anew, so its time is a reading of this call"
    )
    entry = cache.get(cache_key("GET", httpx.URL(EXPORT_RELEASES_URL)))
    assert entry is not None
    assert second.meta.retrieved_at != datetime.fromtimestamp(entry.stored_at, UTC), (
        "the data's own time, not the time the cached release list was stored"
    )


def test_release_dates_from_the_cache_carry_the_time_they_were_stored(
    replay_fixture: ReplayFixture,
) -> None:
    """Conventions §4: on a cache hit ``retrieved_at`` is when the entry was stored."""
    releases = replay_fixture(EXPORT_RELEASES, "all")
    replay_fixture(EXPORTS, "CH_2026_8")
    tasks.get_census_exports("CH", 2026, 8)
    entry = cache.get(cache_key("GET", httpx.URL(EXPORT_RELEASES_URL)))
    assert entry is not None
    result = tasks.get_census_release_dates(ProductType.X)
    assert releases.call_count == 1
    assert result.meta.retrieved_at == datetime.fromtimestamp(entry.stored_at, UTC)


def test_a_listed_partner_without_trade_is_an_empty_result(
    replay_fixture: ReplayFixture,
) -> None:
    """Recorded: Bouvet Island (``BV``) in August 2026 answers 200 with ``[]``. The month
    is released and the code listed, so empty means empty, not an error."""
    replay_fixture(EXPORT_RELEASES, "all")
    data = replay_fixture(EXPORTS, "no_data_valid_partner")
    result = tasks.get_census_exports("BV", 2026, 8)
    assert result.data == []
    assert result.meta.vintage == RELEASED_2026_08, "the month's release, data or none"
    _published_naive(result.meta)
    assert result.meta.request == {
        "partner_code": "BV",
        "year": 2026,
        "month": 8,
    }
    assert sent_urls(data) == [
        f"{BASE_URL}/api/gats/censusExports/partnerCode/BV/year/2026/month/8"
    ]


def test_a_month_not_released_yet_is_not_found(replay_fixture: ReplayFixture) -> None:
    """GATS answers 2035-01 with 200 ``[]`` (``future_month.json``); the release list ends
    at 202608, so the task refuses it without the data request."""
    releases = replay_fixture(EXPORT_RELEASES, "all")
    data = replay_fixture(EXPORTS, "future_month")
    with pytest.raises(NotFoundError) as info:
        tasks.get_census_exports("CH", 2035, 1)
    message = info.value.message
    assert message.startswith("GATS has no Census exports for 203501: it is not released yet")
    assert "the latest exports month released is 202608" in message
    assert "716 months, 196701 to 202608" in message
    assert "The release list was fetched at " in message, "when it came from the wire"
    assert "api.fas.usda.gov" not in message
    assert (releases.call_count, data.call_count) == (1, 0)


def test_a_month_before_the_data_is_not_found(replay_fixture: ReplayFixture) -> None:
    replay_fixture(IMPORT_RELEASES, "all")
    with pytest.raises(NotFoundError, match="GATS has no Census imports for 196612") as info:
        tasks.get_census_imports("CH", 1966, 12)
    assert "the imports data starts at 196701" in info.value.message


def test_a_refusal_from_the_cached_list_says_when_it_was_fetched(
    replay_fixture: ReplayFixture,
) -> None:
    """Within the hour a cached list can lag a new release; the refusal says so."""
    replay_fixture(EXPORT_RELEASES, "all")
    replay_fixture(EXPORTS, "CH_2026_8")
    tasks.get_census_exports("CH", 2026, 8)
    with pytest.raises(NotFoundError) as info:
        tasks.get_census_exports("CH", 2026, 9)
    message = info.value.message
    assert "203501" not in message
    assert "for 202609: it is not released yet" in message
    assert " UTC and is kept for an hour" in message
    assert "The release list was fetched at " in message


def test_arguments_are_checked_before_any_request(respx_mock: respx.MockRouter) -> None:
    """respx is active with no routes mounted, so any upstream call would fail loudly."""
    with pytest.raises(UnknownCode, match="'ZZ' is not a partner_code") as unknown:
        tasks.get_census_exports("ZZ", 2026, 8)
    assert unknown.value.closest == ()
    assert 'e.g. "CH" (China), "MX" (Mexico)' in unknown.value.message
    assert "list_countries lists every one" in unknown.value.message
    with pytest.raises(UnknownCode, match=r"Did you mean CH \(China\)") as close:
        tasks.get_census_imports("ch", 2026, 8)
    assert close.value.closest[0] == ("CH", "China")
    for month in (0, 13):
        with pytest.raises(InvalidRequestError, match="month must be a whole number from 1"):
            tasks.get_census_exports("CH", 2026, month)
        with pytest.raises(InvalidRequestError, match="month must be a whole number from 1"):
            tasks.get_census_imports("CH", 2026, month)
    with pytest.raises(InvalidRequestError, match="four-digit year"):
        tasks.get_census_exports("CH", 26, 8)
    with pytest.raises(InvalidRequestError, match="hs10_code must be 1 to 10 digits"):
        tasks.get_census_exports("CH", 2026, 8, hs10_code="02.01")
    with pytest.raises(InvalidRequestError, match="hs10_code must be 1 to 10 digits"):
        tasks.get_census_imports("CH", 2026, 8, hs10_code="01039100001")
    with pytest.raises(InvalidRequestError, match='product_type must be "X" \\(exports\\)'):
        tasks.get_census_release_dates("Q")  # type: ignore[arg-type]
    for task in DATA_TASKS[2:]:  # get_census_reexports and the three district tasks
        with pytest.raises(UnknownCode, match="'ZZ' is not a partner_code"):
            task("ZZ", 2026, 8)
        with pytest.raises(InvalidRequestError, match="month must be a whole number from 1"):
            task("IC", 2026, 0)
        with pytest.raises(InvalidRequestError, match="hs10_code must be 1 to 10 digits"):
            task("IC", 2026, 8, hs10_code="03.04")
    assert respx_mock.calls.call_count == 0


DATA_TASKS: list[Callable[..., Any]] = [
    tasks.get_census_exports,
    tasks.get_census_imports,
    tasks.get_census_reexports,
    tasks.get_customs_district_exports,
    tasks.get_customs_district_imports,
    tasks.get_customs_district_reexports,
]
DISTRICT_TASKS = DATA_TASKS[3:]


@pytest.mark.parametrize("task", DATA_TASKS, ids=[t.__name__ for t in DATA_TASKS])
def test_a_discontinued_code_is_refused_after_its_month_before_any_request(
    respx_mock: respx.MockRouter, task: Callable[..., Any]
) -> None:
    """``SZ`` (Switzerland) was discontinued in 198712: 2026-08 is refused by every Census
    task without a request, naming ``SR``, the current code of the same name."""
    with pytest.raises(InvalidRequestError) as info:
        task("SZ", 2026, 8)
    assert not isinstance(info.value, UnknownCode)
    assert info.value.message.startswith(
        "partner_code 'SZ' (Switzerland) was discontinued in 198712"
    )
    assert info.value.message.endswith("Listed under the same name: SR.")
    assert respx_mock.calls.call_count == 0


def test_a_discontinued_code_passes_for_a_month_before_its_end(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """``SZ`` for 1987-06, before its 198712: the check passes, the recorded exports list
    (from 196701) has the month, and the data request goes out. NOT RECORDED: no answer
    for Switzerland in 1987 is recorded, so the data route answers ``[]`` and the test
    checks what was sent and the month's release time."""
    releases = replay_fixture(EXPORT_RELEASES, "all")
    url = f"{BASE_URL}/api/gats/censusExports/partnerCode/SZ/year/1987/month/6"
    data = respx_mock.get(url).mock(return_value=httpx.Response(200, json=[]))
    result = tasks.get_census_exports("SZ", 1987, 6)
    assert result.data == []
    assert result.meta.vintage == _release_time(EXPORT_RELEASES, "198706")
    assert sent_urls(releases) == [EXPORT_RELEASES_URL]
    assert sent_urls(data) == [url]


def test_an_iso_code_leads_to_the_partner_code_before_any_request(
    respx_mock: respx.MockRouter,
) -> None:
    """``CHN`` is China's ISO and GENC code: the refusal names ``CH`` first, before ``CN``
    (Comoros), which difflib finds close by its letters."""
    with pytest.raises(UnknownCode) as info:
        tasks.get_census_exports("CHN", 2026, 8)
    assert info.value.closest[:2] == (("CH", "China"), ("CN", "Comoros"))
    assert "Did you mean CH (China), CN (Comoros)?" in info.value.message
    with pytest.raises(UnknownCode, match=r"Did you mean IC \(Iceland\)"):
        tasks.get_customs_district_imports("ISL", 2026, 8)
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize("task", DISTRICT_TASKS, ids=[t.__name__ for t in DISTRICT_TASKS])
def test_an_unknown_customs_district_is_refused_before_any_request(
    respx_mock: respx.MockRouter, task: Callable[..., Any]
) -> None:
    with pytest.raises(UnknownCode) as info:
        task("IC", 2026, 8, customs_district_id=12)
    assert info.value.closest == (
        ("11", "PHILADELPHIA, PA."),
        ("13", "BALTIMORE, MD."),
        ("10", "NEW YORK, N.Y."),
    )
    assert info.value.message.startswith(
        "12 is not a customs_district_id in the packaged customsDistricts list"
    )
    with pytest.raises(InvalidRequestError, match="customs_district_id must be an integer"):
        task("IC", 2026, 8, customs_district_id=True)
    assert respx_mock.calls.call_count == 0


def test_get_census_reexports(replay_fixture: ReplayFixture) -> None:
    """Iceland in August 2026: 12 records. Only the exports release list is mounted: the
    re-exports have none of their own, and a request for the imports list would fail."""
    releases = replay_fixture(EXPORT_RELEASES, "all")
    data = replay_fixture(RE_EXPORTS, "IC_2026_8")
    result = tasks.get_census_reexports("IC", 2026, 8)
    assert len(result.data) == 12
    first = result.data[0]
    assert (first.hs10_code, first.value, first.census_uom_id1) == (
        "0709202000",
        Decimal("5439.0"),
        47,
    )
    assert [r.hs10_code for r in result.data] == [
        r["hS10Code"] for r in _recorded(RE_EXPORTS, "IC_2026_8")
    ], "every record, in upstream order"
    assert {(r.country_code, r.date) for r in result.data} == {("IC", "202608")}
    assert result.meta.endpoint == "GATSData_GetCensusReExports"
    assert result.meta.request == {
        "partner_code": "IC",
        "year": 2026,
        "month": 8,
    }
    assert result.meta.vintage == RELEASED_2026_08 == _release_time(EXPORT_RELEASES, "202608")
    _published_naive(result.meta)
    chapter = tasks.get_census_reexports("IC", 2026, 8, hs10_code="62")
    assert [r.hs10_code for r in chapter.data] == [
        "6201409000",
        "6203493000",
        "6208911000",
        "6210401000",
    ]
    assert chapter.meta.request["hs10_code"] == "62"
    assert sent_urls(releases) == [EXPORT_RELEASES_URL], "the list once, from the cache after"
    assert sent_urls(data) == [IC_RE_EXPORTS_URL, IC_RE_EXPORTS_URL]


def test_a_re_export_month_not_released_says_which_list_was_checked(
    replay_fixture: ReplayFixture,
) -> None:
    replay_fixture(EXPORT_RELEASES, "all")
    with pytest.raises(NotFoundError) as info:
        tasks.get_census_reexports("IC", 2035, 1)
    message = info.value.message
    assert message.startswith("GATS has no Census re-exports for 203501: it is not released yet")
    assert "the latest exports month released is 202608" in message
    assert "GATS publishes no release list for re-exports: the package checks the exports" in (
        message
    )


@pytest.mark.parametrize(
    ("task", "endpoint", "fixture", "release_list", "release_url", "url", "count", "in_ny"),
    [
        (
            tasks.get_customs_district_exports,
            "GATSData_GetCustomsDistrictsExports",
            DISTRICT_EXPORTS,
            EXPORT_RELEASES,
            EXPORT_RELEASES_URL,
            IC_DISTRICT_EXPORTS_URL,
            107,
            16,
        ),
        (
            tasks.get_customs_district_imports,
            "GATSData_GetCustomsDistrictsImports",
            DISTRICT_IMPORTS,
            IMPORT_RELEASES,
            IMPORT_RELEASES_URL,
            IC_DISTRICT_IMPORTS_URL,
            123,
            28,
        ),
        (
            tasks.get_customs_district_reexports,
            "GATSData_GetCustomsDistrictsReExports",
            DISTRICT_RE_EXPORTS,
            EXPORT_RELEASES,
            EXPORT_RELEASES_URL,
            IC_DISTRICT_RE_EXPORTS_URL,
            13,
            5,
        ),
    ],
    ids=["exports", "imports", "re_exports"],
)
def test_customs_district_tasks(
    replay_fixture: ReplayFixture,
    task: Callable[..., Any],
    endpoint: str,
    fixture: str,
    release_list: str,
    release_url: str,
    url: str,
    count: int,
    in_ny: int,
) -> None:
    """Iceland in August 2026, by customs district. Only the right release list is
    mounted: the imports list for imports, the exports list for exports and, by
    assumption, re-exports; a request for the other would fail. ``customs_district_id``
    keeps one district after the one data request."""
    releases = replay_fixture(release_list, "all")
    data = replay_fixture(fixture, "IC_2026_8")
    result = task("IC", 2026, 8)
    assert len(result.data) == count
    assert [(r.customs_district_id, r.hs10_code) for r in result.data] == [
        (r["customsDistrictId"], r["hS10Code"]) for r in _recorded(fixture, "IC_2026_8")
    ], "every record, in upstream order"
    assert result.meta.endpoint == endpoint
    assert result.meta.request == {
        "partner_code": "IC",
        "year": 2026,
        "month": 8,
    }
    assert result.meta.vintage == RELEASED_2026_08 == _release_time(release_list, "202608")
    _published_naive(result.meta)
    new_york = task("IC", 2026, 8, customs_district_id=10)
    assert len(new_york.data) == in_ny
    assert {r.customs_district_id for r in new_york.data} == {10}
    assert new_york.data == [r for r in result.data if r.customs_district_id == 10]
    assert new_york.meta.request["customs_district_id"] == 10
    assert sent_urls(releases) == [release_url]
    assert sent_urls(data) == [url, url], "the filter is not sent upstream"


def test_both_filters_narrow_the_district_imports(replay_fixture: ReplayFixture) -> None:
    """Fish fillets (``0304``) from Iceland: 51 records over every district, 13 through
    New York (district 10)."""
    replay_fixture(IMPORT_RELEASES, "all")
    replay_fixture(DISTRICT_IMPORTS, "IC_2026_8")
    fillets = tasks.get_customs_district_imports("IC", 2026, 8, hs10_code="0304")
    assert len(fillets.data) == 51
    both = tasks.get_customs_district_imports(
        "IC", 2026, 8, hs10_code="0304", customs_district_id=10
    )
    assert len(both.data) == 13
    assert all(r.customs_district_id == 10 and r.hs10_code.startswith("0304") for r in both.data)
    assert both.meta.request == {
        "partner_code": "IC",
        "year": 2026,
        "month": 8,
        "hs10_code": "0304",
        "customs_district_id": 10,
    }
    assert isinstance(both.data[0].consumption_cif_value, Decimal)
    empty = tasks.get_customs_district_imports("IC", 2026, 8, customs_district_id=99)
    assert empty.data == [], "a listed district without imports from Iceland"
    assert empty.meta.vintage == RELEASED_2026_08


def test_a_district_month_not_released_is_not_found(replay_fixture: ReplayFixture) -> None:
    replay_fixture(IMPORT_RELEASES, "all")
    with pytest.raises(
        NotFoundError, match="GATS has no Census customs-district imports for 203501"
    ) as info:
        tasks.get_customs_district_imports("IC", 2035, 1)
    assert "the package checks the imports list" in info.value.message


@pytest.mark.anyio
async def test_the_district_tools_name_both_filters_when_cut(
    replay_fixture: ReplayFixture,
) -> None:
    """Exports to China by district, 1,697 rows, over MCP: cut at the default cap with a
    note naming ``hs10_code`` and ``customs_district_id``; one district of Iceland's
    exports comes back whole."""
    replay_fixture(EXPORT_RELEASES, "all")
    replay_fixture(DISTRICT_EXPORTS, "CH_2026_8")
    payload = await mcp_call(
        server,
        "usda_gats_get_customs_district_exports",
        {"partner_code": "CH", "year": 2026, "month": 8},
    )
    shown = len(payload["data"])
    assert shown == 200
    assert payload["note"] == (
        f"showing {shown} of 1697 rows (cap: 200 rows or 65536 bytes); {DISTRICT_NOTE}"
    )
    assert payload["meta"]["vintage"] == RELEASED_2026_08
    assert "customs_district_id" not in payload["meta"]["request"], "not given, left out"


@pytest.mark.anyio
async def test_the_district_and_re_export_tools_end_to_end(
    replay_fixture: ReplayFixture,
) -> None:
    replay_fixture(EXPORT_RELEASES, "all")
    district = replay_fixture(DISTRICT_RE_EXPORTS, "IC_2026_8")
    re_exports = replay_fixture(RE_EXPORTS, "IC_2026_8")
    arguments: dict[str, object] = {"partner_code": "IC", "year": 2026, "month": 8}
    new_york = await mcp_call(
        server,
        "usda_gats_get_customs_district_reexports",
        {**arguments, "customs_district_id": 10},
    )
    assert len(new_york["data"]) == 5
    assert "note" not in new_york
    assert new_york["data"][0] == {
        "customs_district_id": 10,
        "date": "202608",
        "country_code": "IC",
        "hs10_code": "0709202000",
        "census_uom_id1": 47,
        "census_uom_id2": 47,
        "fas_converted_uom_id": 70,
        "fas_non_converted_uom_id": 70,
        "quantity1": 700.0,
        "quantity2": 0.0,
        "value": 5439.0,
    }, "Decimal values are JSON numbers (ADR-0008)"
    whole = await mcp_call(server, "usda_gats_get_census_reexports", arguments)
    assert len(whole["data"]) == 12
    assert whole["meta"]["endpoint"] == "GATSData_GetCensusReExports"
    assert whole["meta"]["vintage"] == RELEASED_2026_08
    assert sent_urls(district) == [IC_DISTRICT_RE_EXPORTS_URL]
    assert sent_urls(re_exports) == [IC_RE_EXPORTS_URL]
    with pytest.raises(AssertionError, match="error: UnknownCode: 12 is not a customs_district_id"):
        await mcp_call(
            server,
            "usda_gats_get_customs_district_reexports",
            {**arguments, "customs_district_id": 12},
        )
    with pytest.raises(AssertionError, match="error: InvalidRequestError: partner_code 'SZ'"):
        await mcp_call(
            server, "usda_gats_get_census_reexports", {**arguments, "partner_code": "SZ"}
        )


@pytest.mark.parametrize(
    ("product_type", "endpoint", "fixture", "url"),
    [
        (
            ProductType.X,
            "GATSData_GetCensusExportDataReleaseInfo",
            EXPORT_RELEASES,
            EXPORT_RELEASES_URL,
        ),
        (
            ProductType.M,
            "GATSData_GetCensusImportDataReleaseInfo",
            IMPORT_RELEASES,
            IMPORT_RELEASES_URL,
        ),
    ],
    ids=["X", "M"],
)
def test_get_census_release_dates(
    replay_fixture: ReplayFixture,
    product_type: ProductType,
    endpoint: str,
    fixture: str,
    url: str,
) -> None:
    route = replay_fixture(fixture, "all")
    before = datetime.now(UTC)
    result = tasks.get_census_release_dates(product_type)
    after = datetime.now(UTC)
    assert len(result.data) == 716
    assert result.data[0].statistical_year_month == "202608"
    assert result.data[-1].statistical_year_month == "196701"
    assert {r.product_type for r in result.data} == {product_type}
    assert result.meta.endpoint == endpoint
    assert result.meta.request == {"product_type": product_type.value}
    assert (result.meta.published_at, result.meta.vintage) == (None, None)
    # Fetched now, from the wire: the time the answer arrived, not the recording's.
    assert_time_between(result.meta.retrieved_at, before, after)
    assert sent_urls(route) == [url]


def test_a_plain_code_is_a_product_type(replay_fixture: ReplayFixture) -> None:
    replay_fixture(IMPORT_RELEASES, "all")
    result = tasks.get_census_release_dates("M")  # type: ignore[arg-type]
    assert result.meta.endpoint == "GATSData_GetCensusImportDataReleaseInfo"
    assert result.meta.request == {"product_type": "M"}


@pytest.mark.anyio
async def test_mcp_tool_call_end_to_end_names_the_filter_when_cut(
    replay_fixture: ReplayFixture,
) -> None:
    """Exports to China in August 2026, 777 rows, over MCP: cut at the default cap with a
    note that names ``hs10_code``, the one filter the tool has (ADR-0016); the chapter
    filter returns all 26 rows of chapter 02, without a note."""
    replay_fixture(EXPORT_RELEASES, "all")
    data = replay_fixture(EXPORTS, "CH_2026_8")
    arguments: dict[str, object] = {"partner_code": "CH", "year": 2026, "month": 8}
    payload = await mcp_call(server, "usda_gats_get_census_exports", arguments)
    shown = len(payload["data"])
    assert shown == 200
    assert payload["note"] == (
        f"showing {shown} of 777 rows (cap: 200 rows or 65536 bytes); {HS10_NOTE}"
    )
    assert payload["data"][0] == {
        "date": "202608",
        "country_code": "CH",
        "hs10_code": "0103910000",
        "census_uom_id1": 78,
        "census_uom_id2": 78,
        "fas_converted_uom_id": 78,
        "fas_non_converted_uom_id": 78,
        "quantity1": 394.0,
        "quantity2": 0.0,
        "value": 20672.0,
    }, "Decimal values are JSON numbers (ADR-0008)"
    assert payload["meta"]["endpoint"] == "GATSData_GetCensusExports"
    assert payload["meta"]["vintage"] == RELEASED_2026_08
    assert payload["meta"]["published_at"] == payload["meta"]["vintage"]
    assert payload["meta"]["published_at_naive"] is True
    chapter = await mcp_call(
        server, "usda_gats_get_census_exports", {**arguments, "hs10_code": "02"}
    )
    assert len(chapter["data"]) == 26
    assert "note" not in chapter
    assert sent_urls(data) == [CH_EXPORTS_URL, CH_EXPORTS_URL]
    with pytest.raises(AssertionError, match="error: UnknownCode: 'ZZ' is not a partner_code"):
        await mcp_call(server, "usda_gats_get_census_exports", {**arguments, "partner_code": "ZZ"})


@pytest.mark.anyio
async def test_the_imports_tool_names_the_filter_too(replay_fixture: ReplayFixture) -> None:
    replay_fixture(IMPORT_RELEASES, "all")
    replay_fixture(IMPORTS, "CH_2026_8")
    payload = await mcp_call(
        server, "usda_gats_get_census_imports", {"partner_code": "CH", "year": 2026, "month": 8}
    )
    assert len(payload["data"]) == 185, "the 64 KB cap cuts these wider rows before 200"
    assert payload["note"] == (
        f"showing 185 of 3294 rows (cap: 200 rows or 65536 bytes); {HS10_NOTE}"
    )


@pytest.mark.anyio
async def test_the_release_dates_tool_says_its_rows_are_the_newest_months(
    replay_fixture: ReplayFixture,
) -> None:
    """The exports release list, 716 months, over MCP: cut at the default 200 rows, with a
    note of its own that says the rows shown are the newest months and names no filter,
    since the tool has none (ADR-0016)."""
    route = replay_fixture(EXPORT_RELEASES, "all")
    payload = await mcp_call(server, "usda_gats_get_census_release_dates", {"product_type": "X"})
    assert len(payload["data"]) == 200
    assert payload["data"][0] == {
        "statistical_year_month": "202608",
        "product_type": "X",
        "reporter_code": "US",
        "release_time_stamp": RELEASED_2026_08,
    }
    assert payload["data"][-1]["statistical_year_month"] == "201001", "16 years and 8 months"
    assert payload["note"] == (
        f"showing 200 of 716 rows (cap: 200 rows or 65536 bytes); {RELEASE_DATES_NOTE}"
    )
    assert "filter" not in payload["note"]
    assert sent_urls(route) == [EXPORT_RELEASES_URL]


def test_values_are_json_numbers_over_http(replay_fixture: ReplayFixture) -> None:
    """ADR-0008 through the router: ``Decimal`` in Python, a JSON number on the wire; an
    unknown partner is a 422 problem."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.gats.http import router

    replay_fixture(EXPORT_RELEASES, "all")
    replay_fixture(EXPORTS, "CH_2026_8")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    params: dict[str, str | int] = {"partner_code": "CH", "year": 2026, "month": 8}
    response = http.get("/usda-gats/get_census_exports", params={**params, "hs10_code": "0201"})
    assert response.status_code == 200, response.text
    assert [row["value"] for row in response.json()["data"]] == [
        r["value"] for r in _recorded(EXPORTS, "CH_2026_8") if str(r["hS10Code"]).startswith("0201")
    ]
    assert all(isinstance(row["value"], float) for row in response.json()["data"])
    rejected = http.get("/usda-gats/get_census_exports", params={**params, "partner_code": "ZZ"})
    assert rejected.status_code == 422
    assert rejected.json()["title"] == "UnknownCode"
    releases = http.get("/usda-gats/get_census_release_dates", params={"product_type": "X"})
    assert releases.status_code == 200
    assert releases.json()["meta"]["request"] == {"product_type": "X"}
    replay_fixture(DISTRICT_EXPORTS, "IC_2026_8")
    district: dict[str, str | int] = {
        "partner_code": "IC",
        "year": 2026,
        "month": 8,
        "customs_district_id": 10,
    }
    new_york = http.get("/usda-gats/get_customs_district_exports", params=district)
    assert new_york.status_code == 200, new_york.text
    assert len(new_york.json()["data"]) == 16
    assert {row["customs_district_id"] for row in new_york.json()["data"]} == {10}
    unknown = http.get(
        "/usda-gats/get_customs_district_exports", params={**district, "customs_district_id": 12}
    )
    assert unknown.status_code == 422
    assert unknown.json()["title"] == "UnknownCode"
    discontinued = http.get(
        "/usda-gats/get_census_exports", params={**params, "partner_code": "SZ"}
    )
    assert discontinued.status_code == 422
    assert discontinued.json()["title"] == "InvalidRequestError"


SERIES_NOTE = (
    "the rows run month by month, oldest first; filter by hs10_code, a full code or a "
    "prefix such as the chapter '03', or ask for fewer months to see the rest"
)
RELEASED_2026_07 = "2026-09-03T08:00:00"
"""``releaseTimeStamp`` of ``"202607"`` in both recorded release lists, as upstream wrote it."""
IC_MONTHS = ("IC_2026_7", "IC_2026_8")
SERIES_TASKS: list[Callable[..., Any]] = [
    tasks.get_census_export_series,
    tasks.get_census_import_series,
    tasks.get_census_reexport_series,
]


def _ic_url(path: str, month: int) -> str:
    return f"{BASE_URL}/api/gats/{path}/partnerCode/IC/year/2026/month/{month}"


def _answering(
    respx_mock: respx.MockRouter, method: str, host: str, answers: dict[str, FixtureResponse]
) -> respx.Route:
    """One route for ``method`` on ``host`` that answers each path of ``answers`` with its
    recorded status, headers and body, as ``replay_fixture`` does; a path not in
    ``answers`` matches no route and fails the test."""

    def answer(request: httpx.Request) -> httpx.Response:
        response = answers[request.url.path]
        return httpx.Response(response.status, headers=response.headers, content=response.content)

    route = respx_mock.route(method=method, host=host, path__in=tuple(answers))
    return route.mock(side_effect=answer)


def _replay_months(respx_mock: respx.MockRouter, endpoint: str, *cases: str) -> respx.Route:
    """Mount the recorded months ``cases`` of ``endpoint`` on one route, so that
    ``sent_urls(route)`` lists a series' requests in the order they were sent.

    ``replay_fixture`` mounts one route per fixture, which shows what each route received
    but not the order across them. This route answers every request with the recorded
    exchange of its path, for the recorded method, as ``replay_fixture`` does; a path
    none of ``cases`` recorded matches no route and fails the test."""
    recorded = [load_fixture(FIXTURES / endpoint / f"{case}.json") for case in cases]
    answers = {httpx.URL(fixture.request.url).path: fixture.response for fixture in recorded}
    ((method, host),) = {
        (fixture.request.method, httpx.URL(fixture.request.url).host) for fixture in recorded
    }
    return _answering(respx_mock, method, host, answers)


def _answer_months(
    respx_mock: respx.MockRouter, endpoint: str, case: str, *urls: str
) -> respx.Route:
    """Mount ``urls`` on one route that answers each with the recorded exchange ``case``
    of ``endpoint``, its status, headers and body, for the recorded method: the variant of
    ``_replay_months`` for months nothing was recorded for.

    NOT RECORDED for ``urls``: each gets the answer recorded for another request, e.g. the
    empty list GATS sent for Bouvet Island (``BV``) in August 2026, so a test that uses it
    says so. ``urls`` share the recorded request's host."""
    fixture = load_fixture(FIXTURES / endpoint / f"{case}.json")
    (host,) = {httpx.URL(url).host for url in (fixture.request.url, *urls)}
    answers = {httpx.URL(url).path: fixture.response for url in urls}
    return _answering(respx_mock, fixture.request.method, host, answers)


def _months_recorded(endpoint: str, *cases: str) -> list[tuple[object, object]]:
    """``(date, hS10Code)`` of every recorded record of ``cases``, in the order given."""
    return [(r["date"], r["hS10Code"]) for case in cases for r in _recorded(endpoint, case)]


@pytest.mark.parametrize(
    ("task", "endpoint", "fixture", "release_list", "release_url", "path", "counts"),
    [
        (
            tasks.get_census_export_series,
            "GATSData_GetCensusExports",
            EXPORTS,
            EXPORT_RELEASES,
            EXPORT_RELEASES_URL,
            "censusExports",
            (105, 92),
        ),
        (
            tasks.get_census_import_series,
            "GATSData_GetCensusImport",
            IMPORTS,
            IMPORT_RELEASES,
            IMPORT_RELEASES_URL,
            "censusImports",
            (83, 74),
        ),
        (
            tasks.get_census_reexport_series,
            "GATSData_GetCensusReExports",
            RE_EXPORTS,
            EXPORT_RELEASES,
            EXPORT_RELEASES_URL,
            "censusReExports",
            (19, 12),
        ),
    ],
    ids=["exports", "imports", "re_exports"],
)
def test_census_series_tasks(
    replay_fixture: ReplayFixture,
    respx_mock: respx.MockRouter,
    task: Callable[..., Any],
    endpoint: str,
    fixture: str,
    release_list: str,
    release_url: str,
    path: str,
    counts: tuple[int, int],
) -> None:
    """Iceland over July and August 2026: the release list once, then one request per
    month, oldest first, and every record of both months in one list, in month order and
    upstream order within a month. Only the right release list is mounted: the imports
    list for imports, the exports list for exports and, by assumption, re-exports."""
    releases = replay_fixture(release_list, "all")
    data = _replay_months(respx_mock, fixture, *IC_MONTHS)
    result = task("IC", 2026, 7, 2026, 8)
    july, august = counts
    assert len(result.data) == july + august == len(_months_recorded(fixture, *IC_MONTHS))
    assert [(r.date, r.hs10_code) for r in result.data] == _months_recorded(fixture, *IC_MONTHS)
    assert [r.date for r in result.data] == ["202607"] * july + ["202608"] * august
    assert {r.country_code for r in result.data} == {"IC"}
    assert isinstance(result.data[0].value, Decimal)
    assert sent_urls(data) == [_ic_url(path, 7), _ic_url(path, 8)], "oldest month first"
    assert (releases.call_count, data.call_count) == (1, 2)
    assert sent_urls(releases) == [release_url]
    assert result.meta.source == "usda-gats"
    assert result.meta.endpoint == endpoint
    assert result.meta.request == {
        "partner_code": "IC",
        "start_year": 2026,
        "start_month": 7,
        "end_year": 2026,
        "end_month": 8,
    }
    newer = _release_time(release_list, "202608")
    older = _release_time(release_list, "202607")
    assert (older, newer) == (RELEASED_2026_07, RELEASED_2026_08)
    assert result.meta.vintage == RELEASED_2026_08, "the newer of the two months' releases"
    _published_naive(result.meta)
    assert result.meta.total is None


def test_hs10_code_filters_every_month_of_a_series(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """Fish (chapter 03) from Iceland: 42 records in July, 43 in August; fillets (0304) 25
    and 23. The filter applies to each month after its request and is never sent."""
    replay_fixture(IMPORT_RELEASES, "all")
    data = _replay_months(respx_mock, IMPORTS, *IC_MONTHS)
    for hs10_code, expected in [
        ("03", {"202607": 42, "202608": 43}),
        ("0304", {"202607": 25, "202608": 23}),
    ]:
        result = tasks.get_census_import_series("IC", 2026, 7, 2026, 8, hs10_code=hs10_code)
        assert [(r.date, r.hs10_code) for r in result.data] == [
            pair
            for pair in _months_recorded(IMPORTS, *IC_MONTHS)
            if str(pair[1]).startswith(hs10_code)
        ]
        assert Counter(r.date for r in result.data) == expected
        assert result.meta.request["hs10_code"] == hs10_code
        assert result.meta.vintage == RELEASED_2026_08
    none = tasks.get_census_import_series("IC", 2026, 7, 2026, 8, hs10_code="99")
    assert none.data == []
    assert none.meta.vintage == RELEASED_2026_08, "the months' releases, data or none"
    sent = [_ic_url("censusImports", 7), _ic_url("censusImports", 8)]
    assert sent_urls(data) == sent * 3, "the filter is not sent upstream"


def test_a_one_month_series_answers_what_the_month_task_answers(
    replay_fixture: ReplayFixture,
) -> None:
    """A range of one month is the month task's records, endpoint and vintage; only
    ``meta.request`` differs, by its parameters."""
    cases: list[tuple[Callable[..., Any], Callable[..., Any], str, str, str, str]] = [
        (
            tasks.get_census_export_series,
            tasks.get_census_exports,
            "GATSData_GetCensusExports",
            EXPORTS,
            EXPORT_RELEASES,
            "CH",
        ),
        (
            tasks.get_census_import_series,
            tasks.get_census_imports,
            "GATSData_GetCensusImport",
            IMPORTS,
            IMPORT_RELEASES,
            "CH",
        ),
        (
            tasks.get_census_reexport_series,
            tasks.get_census_reexports,
            "GATSData_GetCensusReExports",
            RE_EXPORTS,
            EXPORT_RELEASES,
            "IC",
        ),
    ]
    replay_fixture(EXPORT_RELEASES, "all")
    replay_fixture(IMPORT_RELEASES, "all")
    for series_task, month_task, endpoint, fixture, release_list, partner in cases:
        data = replay_fixture(fixture, f"{partner}_2026_8")
        series = series_task(partner, 2026, 8, 2026, 8)
        month = month_task(partner, 2026, 8)
        assert series.data == month.data
        assert len(series.data) == len(_recorded(fixture, f"{partner}_2026_8"))
        assert series.meta.endpoint == month.meta.endpoint == endpoint
        assert series.meta.vintage == month.meta.vintage == _release_time(release_list, "202608")
        _published_naive(series.meta)
        assert series.meta.request == {
            "partner_code": partner,
            "start_year": 2026,
            "start_month": 8,
            "end_year": 2026,
            "end_month": 8,
        }
        assert data.call_count == 2


def test_a_series_vintage_is_the_newest_release_among_its_months(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """The annual revision re-released 2025-12 on 2026-06-24, after January's and
    February's releases, so 2025-12 to 2026-02 carries the revision's time, not the end
    month's; a month without trade adds nothing and is no error. NOT RECORDED: no answer
    for Iceland in those months is recorded, so the data route serves each the recorded
    empty answer of a listed partner without trade, Bouvet Island (``BV``) in August
    2026, and the test checks what was sent, across the year's end, and the vintage."""
    replay_fixture(EXPORT_RELEASES, "all")
    urls = [
        f"{BASE_URL}/api/gats/censusExports/partnerCode/IC/year/2025/month/12",
        f"{BASE_URL}/api/gats/censusExports/partnerCode/IC/year/2026/month/1",
        f"{BASE_URL}/api/gats/censusExports/partnerCode/IC/year/2026/month/2",
    ]
    months = _answer_months(respx_mock, EXPORTS, "no_data_valid_partner", *urls)
    result = tasks.get_census_export_series("IC", 2025, 12, 2026, 2)
    assert result.data == []
    december = _release_time(EXPORT_RELEASES, "202512")
    assert december == "2026-06-24T08:00:00"
    assert _release_time(EXPORT_RELEASES, "202601") == "2026-03-12T08:00:00"
    assert _release_time(EXPORT_RELEASES, "202602") == "2026-04-02T08:00:00"
    assert result.meta.vintage == december
    assert sent_urls(months) == urls


@pytest.mark.parametrize("task", SERIES_TASKS, ids=[t.__name__ for t in SERIES_TASKS])
def test_series_arguments_are_checked_before_any_request(
    respx_mock: respx.MockRouter, task: Callable[..., Any]
) -> None:
    """respx is active with no routes mounted, so any upstream call would fail loudly."""
    with pytest.raises(InvalidRequestError) as after:
        task("IC", 2026, 8, 2026, 7)
    assert after.value.message == (
        "the range starts at 2026-08, after its end 2026-07: pass the earlier month as "
        "start_year and start_month, e.g. start_year=2026, start_month=6, end_year=2026, "
        "end_month=8."
    )
    with pytest.raises(InvalidRequestError) as span:
        task("IC", 2021, 8, 2026, 8)
    assert span.value.message.startswith(
        "2021-08 to 2026-08 is 61 months, one request each; a series spans at most 60 months."
    )
    for start_month, end_month in [(0, 8), (6, 13)]:
        with pytest.raises(InvalidRequestError, match="month must be a whole number from 1"):
            task("IC", 2026, start_month, 2026, end_month)
    with pytest.raises(InvalidRequestError, match="four-digit year such as 2026, got 26"):
        task("IC", 26, 6, 2026, 8)
    with pytest.raises(InvalidRequestError, match="four-digit year such as 2026, got 20260"):
        task("IC", 2026, 6, 20260, 8)
    with pytest.raises(InvalidRequestError) as inside:
        task("SZ", 1987, 6, 1988, 1)
    assert not isinstance(inside.value, UnknownCode)
    assert inside.value.message.startswith(
        "partner_code 'SZ' (Switzerland) was discontinued in 198712"
    )
    assert "so 1988-01 (198801) is refused" in inside.value.message
    assert inside.value.message.endswith("Listed under the same name: SR.")
    with pytest.raises(InvalidRequestError, match="so 2026-06 \\(202606\\) is refused"):
        task("SZ", 2026, 6, 2026, 8)
    with pytest.raises(UnknownCode, match="'ZZ' is not a partner_code") as unknown:
        task("ZZ", 2026, 6, 2026, 8)
    assert unknown.value.closest == ()
    with pytest.raises(UnknownCode, match=r"Did you mean IC \(Iceland\)"):
        task("ISL", 2026, 6, 2026, 8)
    with pytest.raises(InvalidRequestError, match="hs10_code must be 1 to 10 digits"):
        task("IC", 2026, 6, 2026, 8, hs10_code="03.04")
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize(
    ("task", "endpoint", "release_list", "asked", "flow"),
    [
        (tasks.get_census_export_series, EXPORTS, EXPORT_RELEASES, "exports", "exports"),
        (tasks.get_census_import_series, IMPORTS, IMPORT_RELEASES, "imports", "imports"),
        (tasks.get_census_reexport_series, RE_EXPORTS, EXPORT_RELEASES, "re-exports", "exports"),
    ],
    ids=["exports", "imports", "re_exports"],
)
def test_a_series_with_a_month_not_released_is_refused_whole(
    replay_fixture: ReplayFixture,
    respx_mock: respx.MockRouter,
    task: Callable[..., Any],
    endpoint: str,
    release_list: str,
    asked: str,
    flow: str,
) -> None:
    """The release lists end at 202608, so a range ending 2026-09 is refused before any
    data request, naming 202609 and 202608, rather than trimmed to the months released.
    The longest range, 60 months, passes the span check and meets the same refusal. A
    range with several months missing is refused at the first: 2026-08 to 2026-10 at
    202609, not its end 202610, and 1966-11 to 1967-02 at 196611, its start, since the
    lists begin at 196701."""
    releases = replay_fixture(release_list, "all")
    data = _replay_months(respx_mock, endpoint, *IC_MONTHS)
    with pytest.raises(NotFoundError) as info:
        task("IC", 2026, 7, 2026, 9)
    message = info.value.message
    assert message.startswith(
        f"GATS has no Census {asked} for 202609, in the requested range 202607 to 202609: it "
        f"is not released yet: the latest {flow} month released is 202608"
    )
    assert "A series is refused whole, never trimmed to the months released" in message
    assert ("GATS publishes no release list for re-exports" in message) is (asked != flow)
    assert "api.fas.usda.gov" not in message
    with pytest.raises(NotFoundError) as longest:
        task("IC", 2021, 10, 2026, 9)
    assert "for 202609, in the requested range 202110 to 202609" in longest.value.message
    assert "The release list was fetched at " in longest.value.message, "from the cache"
    with pytest.raises(NotFoundError) as beyond:
        task("IC", 2026, 8, 2026, 10)
    assert beyond.value.message.startswith(
        f"GATS has no Census {asked} for 202609, in the requested range 202608 to 202610: "
        f"it is not released yet: the latest {flow} month released is 202608"
    ), "the first month missing, not the end month"
    with pytest.raises(NotFoundError) as before:
        task("IC", 1966, 11, 1967, 2)
    assert before.value.message.startswith(
        f"GATS has no Census {asked} for 196611, in the requested range 196611 to 196702: "
        f"the {flow} data starts at 196701"
    ), "the first month missing, the start"
    assert (releases.call_count, data.call_count) == (1, 0)
    assert respx_mock.calls.call_count == 1, "the release list, then no data request"


OVER_RATE_LIMIT = {
    "error": {
        "code": "OVER_RATE_LIMIT",
        "message": (
            "You have exceeded your rate limit. Try again later or contact us for "
            "assistance: https://api.fas.usda.gov:443"
        ),
    }
}
"""NOT RECORDED here: the 429 body sdk-usda-psd recorded from the same gateway
(``PSDData_GetCommodities/over_rate_limit.json``, 2026-10-23), as ``test_client.py``
builds it."""
SPENT = {"Retry-After": "3151", "x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
"""NOT RECORDED here: the quota headers of sdk-usda-psd's recorded 429."""


def test_a_quota_spent_mid_series_returns_none_of_its_months(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """Iceland's exports over July and August 2026: July answers as recorded, August with
    a 429, and the series raises ``RateLimitError`` with the gateway's wait and returns
    nothing, not July's 105 records. The wait is read through the client, so it is the
    snapshot's from now, ``Retry-After``'s 3151 s give or take ``CLOCK_SLACK``: a fraction
    under, or over where this host's clock steps back. NOT RECORDED here: GATS has no
    recorded 429, so August's answer is psd's, built as ``test_client.py`` builds it. Not
    marked ``rate_limited``: the error is ``classify``'s reading of the 429 itself, which
    the plugin leaves on, not the quota policy's pause, which it turns off."""
    releases = replay_fixture(EXPORT_RELEASES, "all")
    july = _replay_months(respx_mock, EXPORTS, "IC_2026_7")
    august = respx_mock.get(_ic_url("censusExports", 8)).mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=SPENT)
    )
    with pytest.raises(RateLimitError) as info:
        tasks.get_census_export_series("IC", 2026, 7, 2026, 8)
    assert info.value.retry_after is not None
    slack = CLOCK_SLACK.total_seconds()
    assert 3151 - slack <= info.value.retry_after <= 3151 + slack
    assert "OVER_RATE_LIMIT: You have exceeded your rate limit" in info.value.message
    assert sent_urls(july) == [_ic_url("censusExports", 7)]
    assert sent_urls(august) == [_ic_url("censusExports", 8)], "sent once, not retried"
    assert releases.call_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "endpoint", "fixture", "release_list", "total", "cut"),
    [
        (
            "usda_gats_get_census_export_series",
            "GATSData_GetCensusExports",
            EXPORTS,
            EXPORT_RELEASES,
            777,
            200,
        ),
        (
            "usda_gats_get_census_import_series",
            "GATSData_GetCensusImport",
            IMPORTS,
            IMPORT_RELEASES,
            3294,
            185,
        ),
    ],
    ids=["exports", "imports"],
)
async def test_the_series_tools_name_the_filter_and_a_shorter_range_when_cut(
    replay_fixture: ReplayFixture,
    tool: str,
    endpoint: str,
    fixture: str,
    release_list: str,
    total: int,
    cut: int,
) -> None:
    """China in August 2026 alone over MCP: cut at the default cap with a note that says
    the rows run oldest first and names ``hs10_code`` and fewer months (ADR-0016), at 200
    exports rows and at 185 imports rows, where the 64 KB cap cuts the wider rows first,
    as the month tools are cut; the chapter filter comes back whole."""
    replay_fixture(release_list, "all")
    data = replay_fixture(fixture, "CH_2026_8")
    arguments: dict[str, object] = {
        "partner_code": "CH",
        "start_year": 2026,
        "start_month": 8,
        "end_year": 2026,
        "end_month": 8,
    }
    payload = await mcp_call(server, tool, arguments)
    shown = len(payload["data"])
    assert shown == cut
    assert payload["note"] == (
        f"showing {shown} of {total} rows (cap: 200 rows or 65536 bytes); {SERIES_NOTE}"
    )
    assert payload["meta"]["endpoint"] == endpoint
    assert payload["meta"]["vintage"] == RELEASED_2026_08
    assert payload["meta"]["published_at"] == payload["meta"]["vintage"]
    assert payload["meta"]["published_at_naive"] is True
    assert payload["meta"]["request"] == arguments
    chapter = await mcp_call(server, tool, {**arguments, "hs10_code": "02"})
    assert "note" not in chapter
    assert {row["hs10_code"][:2] for row in chapter["data"]} == {"02"}
    assert data.call_count == 2
    with pytest.raises(
        AssertionError, match="error: InvalidRequestError: 2021-08 to 2026-08 is 61"
    ):
        await mcp_call(server, tool, {**arguments, "start_year": 2021})


@pytest.mark.anyio
async def test_the_reexport_series_tool_end_to_end(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """Iceland's re-exports over July and August 2026, 31 rows, arrive whole and in month
    order. No recorded re-export slice reaches the cap, so the cut is shown on the other
    two series tools; this tool carries the same note."""
    replay_fixture(EXPORT_RELEASES, "all")
    data = _replay_months(respx_mock, RE_EXPORTS, *IC_MONTHS)
    arguments: dict[str, object] = {
        "partner_code": "IC",
        "start_year": 2026,
        "start_month": 7,
        "end_year": 2026,
        "end_month": 8,
    }
    payload = await mcp_call(server, "usda_gats_get_census_reexport_series", arguments)
    assert len(payload["data"]) == 31
    assert "note" not in payload
    assert [row["date"] for row in payload["data"]] == ["202607"] * 19 + ["202608"] * 12
    first = _recorded(RE_EXPORTS, "IC_2026_7")[0]
    assert payload["data"][0] == {
        "date": "202607",
        "country_code": "IC",
        "hs10_code": first["hS10Code"],
        "census_uom_id1": first["censusUOMId1"],
        "census_uom_id2": first["censusUOMId2"],
        "fas_converted_uom_id": first["fasConvertedUOMId"],
        "fas_non_converted_uom_id": first["fasNonConvertedUOMId"],
        "quantity1": first["quantity1"],
        "quantity2": first["quantity2"],
        "value": first["value"],
    }, "Decimal values are JSON numbers (ADR-0008)"
    assert isinstance(payload["data"][0]["value"], float)
    assert payload["meta"]["endpoint"] == "GATSData_GetCensusReExports"
    assert payload["meta"]["vintage"] == RELEASED_2026_08
    assert sent_urls(data) == [_ic_url("censusReExports", 7), _ic_url("censusReExports", 8)]
    for name in (
        "get_census_export_series",
        "get_census_import_series",
        "get_census_reexport_series",
    ):
        cap = tasks.MCP_CAPS[name]
        assert (cap.max_rows, cap.max_bytes, cap.note) == (200, 65536, SERIES_NOTE)
    with pytest.raises(AssertionError, match="error: NotFoundError: GATS has no Census re-exports"):
        await mcp_call(
            server, "usda_gats_get_census_reexport_series", {**arguments, "end_month": 9}
        )


def test_the_series_over_http(replay_fixture: ReplayFixture, respx_mock: respx.MockRouter) -> None:
    """The router serves a series as a GET route with its six parameters: values are JSON
    numbers, a 61-month range is a 422 problem, an unreleased month a 404."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.gats.http import router

    replay_fixture(EXPORT_RELEASES, "all")
    _replay_months(respx_mock, EXPORTS, *IC_MONTHS)
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    params: dict[str, str | int] = {
        "partner_code": "IC",
        "start_year": 2026,
        "start_month": 7,
        "end_year": 2026,
        "end_month": 8,
    }
    response = http.get("/usda-gats/get_census_export_series", params={**params, "hs10_code": "03"})
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert [(row["date"], row["hs10_code"]) for row in rows] == [
        pair for pair in _months_recorded(EXPORTS, *IC_MONTHS) if str(pair[1]).startswith("03")
    ]
    assert all(isinstance(row["value"], float) for row in rows)
    assert response.json()["meta"]["vintage"] == RELEASED_2026_08
    span = http.get("/usda-gats/get_census_export_series", params={**params, "start_year": 2021})
    assert span.status_code == 422
    assert span.json()["title"] == "InvalidRequestError"
    unreleased = http.get("/usda-gats/get_census_export_series", params={**params, "end_month": 9})
    assert unreleased.status_code == 404
    assert unreleased.json()["title"] == "NotFoundError"


SERIES_TOOLS = [
    "usda_gats_get_census_export_series",
    "usda_gats_get_census_import_series",
    "usda_gats_get_census_reexport_series",
]
CEILING_REFUSAL = (
    "the series ceiling, --series-months on the MCP server, must be a whole number of "
    "months from 1 to 60, got {!r}."
)


def _ic_export_urls(start_year: int, start_month: int, count: int) -> list[str]:
    """The exports URLs of ``count`` months for Iceland from the start month on, in order."""
    first = start_year * 12 + start_month - 1
    months = [(index // 12, index % 12 + 1) for index in range(first, first + count)]
    return [
        f"{BASE_URL}/api/gats/censusExports/partnerCode/IC/year/{year}/month/{month}"
        for year, month in months
    ]


@pytest.fixture
def restore_series_ceiling() -> Iterator[None]:
    """The series ceiling is process-wide: a test that sets it leaves the Python API's,
    ``SERIES_MAX_MONTHS``, for the tests after it."""
    yield
    tasks.set_series_ceiling(tasks.SERIES_MAX_MONTHS)


def test_the_series_ceilings_and_the_option() -> None:
    """60 months for the Python API and the HTTP router, the ceiling in force while no MCP
    server applied its options; ``--series-months`` on core's parser, 24 by default."""
    assert (tasks.SERIES_MAX_MONTHS, tasks.MCP_SERIES_MAX_MONTHS) == (60, 24)
    assert tasks.series_ceiling() == 60
    parser = build_parser(server.name, add_options=tasks.mcp_add_options)
    assert parser.parse_args([]).series_months == 24
    assert parser.parse_args(["--series-months", "36"]).series_months == 36
    assert parser.parse_args(["--series-months", "61"]).series_months == 61, (
        "the range is checked when the option is applied, then exit status 2"
    )
    assert (
        "--series-months MONTHS most months one series tool call spans, 1 to 60 (default 24); "
        "one request per month, so 60 months take about a minute of calls"
    ) in " ".join(parser.format_help().split())


@pytest.mark.usefixtures("restore_series_ceiling")
@pytest.mark.parametrize("months", [1, 24, 60])
def test_set_series_ceiling_takes_1_to_60(months: int) -> None:
    tasks.set_series_ceiling(months)
    assert tasks.series_ceiling() == months


@pytest.mark.usefixtures("restore_series_ceiling")
@pytest.mark.parametrize("months", [0, 61, -24, True, "24", 24.0, None])
def test_set_series_ceiling_refuses_anything_else(months: object) -> None:
    """Never above 60, never below 1, never a bool, a text or a float; the ceiling in
    force stays."""
    tasks.set_series_ceiling(36)
    with pytest.raises(InvalidRequestError) as info:
        tasks.set_series_ceiling(months)  # type: ignore[arg-type]
    assert info.value.message == CEILING_REFUSAL.format(months)
    assert info.value.source == "usda-gats"
    assert tasks.series_ceiling() == 36


@pytest.mark.anyio
@pytest.mark.usefixtures("restore_series_ceiling")
async def test_the_mcp_server_refuses_a_series_beyond_its_ceiling_before_any_request(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """``mcp_apply_options`` with the default, 24, returns the server itself and sets the
    ceiling: a 25-month call to each series tool is refused before any request (respx is
    active with no route mounted), naming 24 and ``--series-months``; the ceiling is
    process-wide, so a Python call in the same process meets it too. 24 months pass.
    NOT RECORDED: no answer for Iceland in those 24 months is recorded, so each is served
    the recorded empty answer of a listed partner without trade, Bouvet Island (``BV``)
    in August 2026; the test checks the span check and what was sent."""
    assert tasks.mcp_apply_options(argparse.Namespace(series_months=24), server) is server
    assert tasks.series_ceiling() == 24
    arguments: dict[str, object] = {
        "partner_code": "IC",
        "start_year": 2024,
        "start_month": 8,
        "end_year": 2026,
        "end_month": 8,
    }
    refusal = (
        "2024-08 to 2026-08 is 25 months, one request each; a series spans at most 24 months, "
        "the ceiling set for this process (the MCP server starts with 24 by default; "
        "--series-months raises it, up to 60). Ask for a shorter range, or for consecutive "
        "ranges of at most 24 months one after another."
    )
    for tool in SERIES_TOOLS:
        with pytest.raises(AssertionError) as info:
            await mcp_call(server, tool, arguments)
        assert str(info.value) == f"error: InvalidRequestError: {refusal}", tool
    with pytest.raises(InvalidRequestError) as python:
        await tasks.get_census_export_series.async_fn("IC", 2024, 8, 2026, 8)
    assert python.value.message == refusal
    assert respx_mock.calls.call_count == 0, "refused before any request"
    releases = replay_fixture(EXPORT_RELEASES, "all")
    urls = _ic_export_urls(2024, 9, 24)
    months = _answer_months(respx_mock, EXPORTS, "no_data_valid_partner", *urls)
    payload = await mcp_call(
        server, "usda_gats_get_census_export_series", {**arguments, "start_month": 9}
    )
    assert payload["data"] == []
    assert (releases.call_count, sent_urls(months)) == (1, urls)


@pytest.mark.usefixtures("restore_series_ceiling")
def test_a_ceiling_set_from_python_is_refused_in_the_same_words(
    respx_mock: respx.MockRouter,
) -> None:
    """A Python caller that calls ``set_series_ceiling(12)``, with no MCP server in the
    process, meets the refusal the MCP server gives: the ceiling set for this process, the
    MCP server's default and ``--series-months``, each true for that caller too. Refused
    before any request (respx is active with no route mounted)."""
    tasks.set_series_ceiling(12)
    with pytest.raises(InvalidRequestError) as info:
        tasks.get_census_import_series("IC", 2025, 8, 2026, 8)
    assert info.value.message == (
        "2025-08 to 2026-08 is 13 months, one request each; a series spans at most 12 months, "
        "the ceiling set for this process (the MCP server starts with 24 by default; "
        "--series-months raises it, up to 60). Ask for a shorter range, or for consecutive "
        "ranges of at most 12 months one after another."
    )
    assert respx_mock.calls.call_count == 0, "refused before any request"


@pytest.mark.usefixtures("restore_series_ceiling")
def test_the_python_api_spans_60_months(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """With no MCP options applied, and with ``--series-months 60``, a 60-month Python call
    passes the span check and sends one request per month, oldest first, and 61 months
    are refused with the Python API's message, which names no MCP server. NOT RECORDED:
    the months are served the recorded empty answer of ``BV`` in August 2026, as above."""
    replay_fixture(EXPORT_RELEASES, "all")
    urls = _ic_export_urls(2021, 9, 60)
    months = _answer_months(respx_mock, EXPORTS, "no_data_valid_partner", *urls)
    for namespace in (None, argparse.Namespace(series_months=60)):
        if namespace is not None:
            assert tasks.mcp_apply_options(namespace, server) is server
        assert tasks.series_ceiling() == 60
        result = tasks.get_census_export_series("IC", 2021, 9, 2026, 8)
        assert result.data == []
        assert result.meta.vintage == RELEASED_2026_08
        with pytest.raises(InvalidRequestError) as longer:
            tasks.get_census_export_series("IC", 2021, 8, 2026, 8)
        assert longer.value.message == (
            "2021-08 to 2026-08 is 61 months, one request each; a series spans at most 60 "
            "months. Ask for a shorter range, or for consecutive ranges of at most 60 months "
            "one after another."
        )
    assert sent_urls(months) == urls * 2


@pytest.mark.usefixtures("restore_series_ceiling")
def test_the_entry_point_applies_series_months_or_exits_with_status_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``mcp.run`` hands the hooks to core's ``main``: ``--series-months 36`` sets the
    ceiling before the server runs, on stdio; 61 or 0 ends the process with exit status 2
    and the refusal on stderr, before anything is served, the ceiling unchanged; a value
    that is no integer is argparse's own exit status 2. The server's ``run`` is replaced,
    so nothing is served. The direct call to ``main`` lets mypy check the hooks against
    its signature."""
    served: list[dict[str, object]] = []
    monkeypatch.setattr(server, "run", lambda **kwargs: served.append(kwargs))
    monkeypatch.setattr(sys, "argv", ["xippios-usda-gats-mcp", "--series-months", "36"])
    run()
    assert served == [{"transport": "stdio"}]
    assert tasks.series_ceiling() == 36
    for value in ("61", "0"):
        monkeypatch.setattr(sys, "argv", ["xippios-usda-gats-mcp", "--series-months", value])
        with pytest.raises(SystemExit) as exit_info:
            run()
        assert exit_info.value.code == 2
        assert capsys.readouterr().err.endswith(f"error: {CEILING_REFUSAL.format(int(value))}\n")
    monkeypatch.setattr(sys, "argv", ["xippios-usda-gats-mcp", "--series-months", "two"])
    with pytest.raises(SystemExit) as not_int:
        run()
    assert not_int.value.code == 2
    assert "--series-months: invalid int value: 'two'" in capsys.readouterr().err
    with pytest.raises(SystemExit) as direct:
        main(
            server,
            ["--series-months", "61"],
            add_options=tasks.mcp_add_options,
            apply_options=tasks.mcp_apply_options,
        )
    assert direct.value.code == 2
    assert capsys.readouterr().err.endswith(f"error: {CEILING_REFUSAL.format(61)}\n")
    assert served == [{"transport": "stdio"}], "nothing served after a refusal"
    assert tasks.series_ceiling() == 36
    with pytest.raises(InvalidRequestError, match="got 61"):
        tasks.mcp_apply_options(argparse.Namespace(series_months=61), server)


UN_EXPORTS = "get_un_trade_exports"
UN_IMPORTS = "get_un_trade_imports"
UN_RE_EXPORTS = "get_un_trade_re_exports"
UN_EXPORT_RELEASES = "get_un_trade_export_data_release_info"
UN_IMPORT_RELEASES = "get_un_trade_import_data_release_info"
UN_EXPORT_RELEASES_URL = f"{BASE_URL}/api/gats/UNTrade/data/exports/dataReleaseDates"
UN_IMPORT_RELEASES_URL = f"{BASE_URL}/api/gats/UNTrade/data/imports/dataReleaseDates"
IC_UN_EXPORTS_URL = f"{BASE_URL}/api/gats/UNTradeExports/reporterCode/IC/year/2019"
TP_UN_IMPORTS_URL = f"{BASE_URL}/api/gats/UNTradeImports/reporterCode/TP/year/2019"
MC_UN_RE_EXPORTS_URL = f"{BASE_URL}/api/gats/UNTradeReExports/reporterCode/MC/year/2019"
UN_DATA_NOTE = (
    "filter by partner_code, e.g. 'US' (United States), or by hs6_code, a full code or a "
    "prefix such as the chapter '03', to see the rest"
)
UN_RELEASE_DATES_NOTE = (
    "the list runs newest year first, one row per reporter and year; filter by "
    "reporter_code, e.g. 'IC' (Iceland), or by year, e.g. 2019, to see the rest"
)
IC_2019_EXPORTS_RELEASED = "2020-06-03T05:50:46"
"""``releaseTimeStamp`` of Iceland's 2019 in the recorded UN exports list, as upstream wrote it."""
UN_TASKS: list[Callable[..., Any]] = [
    tasks.get_un_exports,
    tasks.get_un_imports,
    tasks.get_un_reexports,
]


def _un_release_time(endpoint: str, reporter_code: str, year: str) -> object:
    """The reporter-year's ``releaseTimeStamp`` in a recorded UN list, the text upstream sent."""
    (record,) = [
        r
        for r in _recorded(endpoint, "all")
        if (r["reporterCode"], r["statisticalYear"]) == (reporter_code, year)
    ]
    return record["releaseTimeStamp"]


def _partners_and_codes(records: list[Any]) -> list[tuple[str, str]]:
    return [(r.partner_country_code, r.hs6_code) for r in records]


@pytest.mark.parametrize(
    ("task", "endpoint", "fixture", "case", "release_list", "release_url", "url", "count", "first"),
    [
        (
            tasks.get_un_exports,
            "GATSData_GetUNTradeExports",
            UN_EXPORTS,
            "IC_2019",
            UN_EXPORT_RELEASES,
            UN_EXPORT_RELEASES_URL,
            IC_UN_EXPORTS_URL,
            3980,
            ("15", "070700", Decimal("73524.0"), Decimal("29051.0")),
        ),
        (
            tasks.get_un_imports,
            "GATSData_GetUNTradeImports",
            UN_IMPORTS,
            "TP_2019",
            UN_IMPORT_RELEASES,
            UN_IMPORT_RELEASES_URL,
            TP_UN_IMPORTS_URL,
            2377,
            ("15", "100630", Decimal("31.0"), Decimal("15.0")),
        ),
        (
            tasks.get_un_reexports,
            "GATSData_GetUNTradeReExports",
            UN_RE_EXPORTS,
            "MC_2019",
            UN_EXPORT_RELEASES,
            UN_EXPORT_RELEASES_URL,
            MC_UN_RE_EXPORTS_URL,
            421,
            ("AS", "220421", Decimal("114863.0"), Decimal("0.0")),
        ),
    ],
    ids=["exports_IC", "imports_TP", "re_exports_MC"],
)
def test_un_data_tasks(
    replay_fixture: ReplayFixture,
    task: Callable[..., Any],
    endpoint: str,
    fixture: str,
    case: str,
    release_list: str,
    release_url: str,
    url: str,
    count: int,
    first: tuple[str, str, Decimal, Decimal],
) -> None:
    """One reporter-year across every partner and HS6 code, whole and in upstream order.
    Only the right release list is mounted: the imports list for imports, the exports list
    for exports and, by assumption, re-exports; a request for the other would fail."""
    reporter_code = case[:2]
    releases = replay_fixture(release_list, "all")
    data = replay_fixture(fixture, case)
    result = task(reporter_code, 2019)
    assert len(result.data) == count
    head = result.data[0]
    assert (head.partner_country_code, head.hs6_code, head.value, head.quantity1) == first
    assert isinstance(head.value, Decimal)
    assert _partners_and_codes(result.data) == [
        (r["partnerCountryCode"], r["hS6Code"]) for r in _recorded(fixture, case)
    ], "every record, in upstream order"
    assert {(r.year, r.reporter_country_code) for r in result.data} == {("2019", reporter_code)}
    assert result.meta.source == "usda-gats"
    assert result.meta.endpoint == endpoint
    assert result.meta.request == {
        "reporter_code": reporter_code,
        "year": 2019,
    }
    assert result.meta.vintage == _un_release_time(release_list, reporter_code, "2019")
    _published_naive(result.meta)
    assert result.meta.total is None
    assert sent_urls(releases) == [release_url]
    assert sent_urls(data) == [url]


def test_the_un_vintages_are_the_recorded_release_times() -> None:
    """The three reporter-years' ``releaseTimeStamp`` texts, from the recorded lists: the
    re-exports' is the exports list's, the only list they have."""
    assert _un_release_time(UN_EXPORT_RELEASES, "IC", "2019") == IC_2019_EXPORTS_RELEASED
    assert _un_release_time(UN_IMPORT_RELEASES, "TP", "2019") == "2020-07-16T01:15:37"
    assert _un_release_time(UN_EXPORT_RELEASES, "MC", "2019") == "2020-06-03T05:51:31"
    assert _un_release_time(UN_IMPORT_RELEASES, "MC", "2019") == "2020-06-05T01:25:43", (
        "not the re-exports' vintage"
    )


@pytest.mark.parametrize("endpoint", [UN_EXPORT_RELEASES, UN_IMPORT_RELEASES])
def test_isoformat_gives_back_every_recorded_un_release_time(endpoint: str) -> None:
    """``vintage`` claims upstream's own text for the UN lists too: every record's parsed
    time written back with ``isoformat()`` is the text upstream sent."""
    records = _recorded(endpoint, "all")
    assert len(records) in (3796, 3832)
    for record in records:
        parsed = UNTradeDataReleaseInfo.model_validate(record).release_time_stamp
        assert parsed.tzinfo is None
        assert parsed.isoformat() == record["releaseTimeStamp"]


@pytest.mark.parametrize(
    ("partner_code", "hs6_code", "expected"),
    [
        ("US", None, 298),
        ("NO", None, 142),
        (None, "03", 1024),
        (None, "0304", 304),
        (None, "030444", 26),
        ("US", "0304", 16),
        ("US", "030444", 1),
        ("US", "99", 0),
    ],
    ids=[
        "partner",
        "discontinued_partner",
        "chapter",
        "heading",
        "full_code",
        "partner_and_heading",
        "partner_and_code",
        "no_match",
    ],
)
def test_partner_code_and_hs6_code_select_after_the_one_request(
    replay_fixture: ReplayFixture,
    partner_code: str | None,
    hs6_code: str | None,
    expected: int,
) -> None:
    """Iceland's 2019 exports: ``partner_code`` keeps one partner, ``hs6_code`` the codes it
    starts (a chapter, a heading, a full code); neither is sent upstream. ``NO`` (Norway)
    was discontinued in 198712 by the countries list and is a partner of 2019 here."""
    replay_fixture(UN_EXPORT_RELEASES, "all")
    data = replay_fixture(UN_EXPORTS, "IC_2019")
    result = tasks.get_un_exports("IC", 2019, partner_code=partner_code, hs6_code=hs6_code)
    recorded = [
        r
        for r in _recorded(UN_EXPORTS, "IC_2019")
        if (partner_code is None or r["partnerCountryCode"] == partner_code)
        and (hs6_code is None or str(r["hS6Code"]).startswith(hs6_code))
    ]
    assert len(result.data) == len(recorded) == expected
    assert _partners_and_codes(result.data) == [
        (r["partnerCountryCode"], r["hS6Code"]) for r in recorded
    ]
    assert (result.meta.request.get("partner_code"), result.meta.request.get("hs6_code")) == (
        partner_code,
        hs6_code,
    ), "a filter not given is left out (ADR-0022, rule 3)"
    assert result.meta.vintage == IC_2019_EXPORTS_RELEASED
    assert sent_urls(data) == [IC_UN_EXPORTS_URL], "the filters are not sent upstream"


def test_the_un_release_list_is_fetched_once_for_two_task_calls(
    replay_fixture: ReplayFixture,
) -> None:
    """The client caches the UN lists like the Census ones: the second call sends only its
    data request, and the re-exports task reads the exports list from the same entry."""
    releases = replay_fixture(UN_EXPORT_RELEASES, "all")
    exports = replay_fixture(UN_EXPORTS, "IC_2019")
    re_exports = replay_fixture(UN_RE_EXPORTS, "MC_2019")
    tasks.get_un_exports("IC", 2019)
    tasks.get_un_exports("IC", 2019, hs6_code="03")
    tasks.get_un_reexports("MC", 2019)
    assert releases.call_count == 1
    assert sent_urls(exports) == [IC_UN_EXPORTS_URL, IC_UN_EXPORTS_URL]
    assert sent_urls(re_exports) == [MC_UN_RE_EXPORTS_URL]


def test_a_listed_reporter_year_without_re_exports_is_an_empty_result(
    replay_fixture: ReplayFixture,
) -> None:
    """Recorded: Iceland's 2019 re-exports answer 200 with ``[]``. The exports list has
    Iceland's 2019 and the code is listed, so empty means empty, with the exports'
    release time as ``vintage``."""
    replay_fixture(UN_EXPORT_RELEASES, "all")
    data = replay_fixture(UN_RE_EXPORTS, "IC_2019")
    result = tasks.get_un_reexports("IC", 2019)
    assert result.data == []
    assert result.meta.vintage == IC_2019_EXPORTS_RELEASED
    _published_naive(result.meta)
    assert result.meta.endpoint == "GATSData_GetUNTradeReExports"
    assert sent_urls(data) == [f"{BASE_URL}/api/gats/UNTradeReExports/reporterCode/IC/year/2019"]


def test_a_reporter_year_the_list_lacks_is_not_found(replay_fixture: ReplayFixture) -> None:
    """GATS answers Iceland's 2020 with 200 ``[]`` (``unreleased_year.json``); the exports
    list holds Iceland's 1989 to 2019 and no year after 2019 for anyone, so the task refuses
    it without the data request, naming both."""
    releases = replay_fixture(UN_EXPORT_RELEASES, "all")
    data = replay_fixture(UN_EXPORTS, "unreleased_year")
    with pytest.raises(NotFoundError) as info:
        tasks.get_un_exports("IC", 2020)
    message = info.value.message
    assert message.startswith(
        "GATS has no UN Trade exports for reporter IC in 2020: "
        "GATSData_GetUNTradeExportDataReleaseInfo lists 31 years of exports for reporter IC, "
        "1989 to 2019; the latest year it lists for any reporter is 2019, and its newest "
        "release time is 2021-01-18T01:25:58. GATS answers a reporter-year it has not "
        "released with an empty list, so the package checks the release list first. The "
        "release list was fetched at "
    )
    assert "api.fas.usda.gov" not in message
    assert (releases.call_count, data.call_count) == (1, 0)


def test_the_refusal_names_gaps_a_reporter_without_years_and_the_stand_in_list(
    replay_fixture: ReplayFixture,
) -> None:
    """Macau's exports skip 2000 to 2014, 2017 and 2018; Chad (``CD``) is only in the
    imports list; the re-exports' refusal says which list stood in; a refusal from the
    cached list says when it was fetched."""
    replay_fixture(UN_EXPORT_RELEASES, "all")
    future = replay_fixture(UN_EXPORTS, "future_year")
    with pytest.raises(NotFoundError) as gap:
        tasks.get_un_exports("MC", 2017)
    assert "lists 12 years of exports for reporter MC, 1991 to 1999, 2015, 2016, 2019;" in (
        gap.value.message
    )
    assert "The release list was fetched at " in gap.value.message, "from the wire"
    with pytest.raises(NotFoundError) as none:
        tasks.get_un_reexports("CD", 2019)
    message = none.value.message
    assert message.startswith(
        "GATS has no UN Trade re-exports for reporter CD in 2019: "
        "GATSData_GetUNTradeExportDataReleaseInfo lists no year of exports for reporter CD; "
        "the latest year it lists for any reporter is 2019"
    )
    assert "GATS publishes no UN Trade release list for re-exports: the package checks the " in (
        message
    )
    assert "The release list was fetched at " in message, "and from the cache"
    assert " UTC and is kept for an hour" in message
    with pytest.raises(NotFoundError, match="UN Trade exports for reporter IC in 2035"):
        tasks.get_un_exports("IC", 2035)
    assert future.call_count == 0, "GATS's 200 [] for 2035 is never asked for"


def test_an_imports_reporter_year_is_checked_against_the_imports_list(
    replay_fixture: ReplayFixture,
) -> None:
    """Haiti (``HA``) is in the exports list only; Chad (``CD``) lists one year of imports."""
    replay_fixture(UN_IMPORT_RELEASES, "all")
    with pytest.raises(NotFoundError) as info:
        tasks.get_un_imports("HA", 2019)
    assert info.value.message.startswith(
        "GATS has no UN Trade imports for reporter HA in 2019: "
        "GATSData_GetUNTradeImportDataReleaseInfo lists no year of imports for reporter HA;"
    )
    assert "publishes no" not in info.value.message
    with pytest.raises(NotFoundError, match="lists 1 year of imports for reporter CD, 1995;"):
        tasks.get_un_imports("CD", 2019)


def test_a_discontinued_code_is_accepted_on_the_un_side(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """The countries list marks ``AS`` (Australia) discontinued in 198712, and the Census
    tasks refuse it for 2019; the UN Trade data keeps it. As a partner it selects Macau's
    27 re-export records of 2019 (recorded); as a reporter it passes the check and meets
    the release list, which lists its imports to 2018 and its exports to 2016. NOT
    RECORDED: no answer for Australia's 2018 imports is recorded, so the data route answers
    ``[]`` and the test checks what was sent and the reporter-year's release time."""
    with pytest.raises(InvalidRequestError, match="partner_code 'AS' \\(Australia\\) was disc"):
        tasks.get_census_exports("AS", 2019, 1)
    replay_fixture(UN_EXPORT_RELEASES, "all")
    replay_fixture(UN_RE_EXPORTS, "MC_2019")
    australia = tasks.get_un_reexports("MC", 2019, partner_code="AS")
    assert len(australia.data) == 27
    assert {r.partner_country_code for r in australia.data} == {"AS"}
    assert australia.data[0].hs6_code == "220421"
    releases = replay_fixture(UN_IMPORT_RELEASES, "all")
    url = f"{BASE_URL}/api/gats/UNTradeImports/reporterCode/AS/year/2018"
    data = respx_mock.get(url).mock(return_value=httpx.Response(200, json=[]))
    reported = tasks.get_un_imports("AS", 2018)
    assert reported.data == []
    assert reported.meta.vintage == _un_release_time(UN_IMPORT_RELEASES, "AS", "2018")
    assert reported.meta.vintage == "2020-06-04T13:12:54"
    assert sent_urls(releases) == [UN_IMPORT_RELEASES_URL]
    assert sent_urls(data) == [url]
    with pytest.raises(NotFoundError, match="lists 28 years of exports for reporter AS, 1989 to"):
        tasks.get_un_exports("AS", 2019)


def test_un_arguments_are_checked_before_any_request(respx_mock: respx.MockRouter) -> None:
    """respx is active with no routes mounted, so any upstream call would fail loudly."""
    for task in UN_TASKS:
        with pytest.raises(UnknownCode, match="'ZZ' is not a reporter_code") as unknown:
            task("ZZ", 2019)
        assert unknown.value.closest == ()
        assert 'e.g. "CH" (China), "MX" (Mexico)' in unknown.value.message
        assert "GATS answers an unknown reporter code with an empty result" in (
            unknown.value.message
        )
        with pytest.raises(UnknownCode, match=r"Did you mean IC \(Iceland\)"):
            task("ISL", 2019)
        with pytest.raises(UnknownCode, match="'ZZ' is not a partner_code") as partner:
            task("IC", 2019, partner_code="ZZ")
        assert "The UN Trade operations take no partner" in partner.value.message
        with pytest.raises(InvalidRequestError, match="four-digit year such as 2026, got 19"):
            task("IC", 19)
        with pytest.raises(InvalidRequestError, match="four-digit year such as 2026, got '2019'"):
            task("IC", "2019")
        with pytest.raises(InvalidRequestError, match="hs6_code must be 1 to 6 digits") as seven:
            task("IC", 2019, hs6_code="0304441")
        assert not isinstance(seven.value, UnknownCode)
        with pytest.raises(UnknownCode) as absent:
            task("IC", 2019, hs6_code="020119")
        assert absent.value.closest[0] == ("020110", "Bovine Carcass Fr/Ch")
        assert absent.value.message.startswith(
            "'020119' is not a hs6_code in the packaged HS6Commodities list"
        )
    with pytest.raises(InvalidRequestError, match='product_type must be "X" \\(exports\\)'):
        tasks.get_un_release_dates("R")  # type: ignore[arg-type]
    with pytest.raises(UnknownCode, match="'ZZ' is not a reporter_code"):
        tasks.get_un_release_dates(ProductType.X, reporter_code="ZZ")
    with pytest.raises(InvalidRequestError, match="four-digit year"):
        tasks.get_un_release_dates(ProductType.M, year=19)
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize(
    ("product_type", "endpoint", "fixture", "url", "count", "reporters", "first"),
    [
        (
            ProductType.X,
            "GATSData_GetUNTradeExportDataReleaseInfo",
            UN_EXPORT_RELEASES,
            UN_EXPORT_RELEASES_URL,
            3796,
            206,
            ("2019", "AC", datetime(2020, 10, 11, 1, 15, 48)),
        ),
        (
            ProductType.M,
            "GATSData_GetUNTradeImportDataReleaseInfo",
            UN_IMPORT_RELEASES,
            UN_IMPORT_RELEASES_URL,
            3832,
            207,
            ("2019", "AC", datetime(2020, 10, 11, 1, 15, 44)),
        ),
    ],
    ids=["X", "M"],
)
def test_get_un_release_dates(
    replay_fixture: ReplayFixture,
    product_type: ProductType,
    endpoint: str,
    fixture: str,
    url: str,
    count: int,
    reporters: int,
    first: tuple[str, str, datetime],
) -> None:
    """The whole list from the wire, then from the cache with the entry's stored time as
    ``retrieved_at`` (conventions §4), proved by the route's call count."""
    route = replay_fixture(fixture, "all")
    result = tasks.get_un_release_dates(product_type)
    assert len(result.data) == count
    head = result.data[0]
    assert (head.statistical_year, head.reporter_code, head.release_time_stamp) == first
    assert {r.product_type for r in result.data} == {product_type}
    assert len({r.reporter_code for r in result.data}) == reporters
    assert {r.statistical_year for r in result.data} == {str(y) for y in range(1989, 2020)}
    assert max(r.release_time_stamp for r in result.data).date().isoformat() == "2021-01-18"
    assert result.meta.endpoint == endpoint
    assert result.meta.request == {
        "product_type": product_type.value,
    }
    assert (result.meta.published_at, result.meta.vintage) == (None, None)
    assert result.meta.retrieved_at.tzinfo is not None
    entry = cache.get(cache_key("GET", httpx.URL(url)))
    assert entry is not None
    again = tasks.get_un_release_dates(product_type, year=2019)
    assert route.call_count == 1
    assert again.meta.retrieved_at == datetime.fromtimestamp(entry.stored_at, UTC)
    assert len(again.data) == 32
    assert sent_urls(route) == [url]


def test_un_release_dates_filter_by_reporter_and_year(replay_fixture: ReplayFixture) -> None:
    """``reporter_code`` keeps one reporter's years, newest first, ``year`` one year's
    reporters in code order; a listed reporter and a year it lacks selects nothing."""
    replay_fixture(UN_EXPORT_RELEASES, "all")
    replay_fixture(UN_IMPORT_RELEASES, "all")
    iceland = tasks.get_un_release_dates(ProductType.X, reporter_code="IC")
    assert [r.statistical_year for r in iceland.data] == [str(y) for y in range(2019, 1988, -1)]
    assert {r.reporter_code for r in iceland.data} == {"IC"}
    assert iceland.data[0].release_time_stamp.isoformat() == IC_2019_EXPORTS_RELEASED
    assert iceland.meta.request == {"product_type": "X", "reporter_code": "IC"}
    latest = tasks.get_un_release_dates(ProductType.M, year=2019)
    codes = [r.reporter_code for r in latest.data]
    assert len(codes) == 32
    assert codes == sorted(codes)
    assert "TP" in codes
    assert latest.meta.request == {"product_type": "M", "year": 2019}
    (one,) = tasks.get_un_release_dates("M", reporter_code="TP", year=2019).data  # type: ignore[arg-type]
    assert one.release_time_stamp.isoformat() == "2020-07-16T01:15:37"
    assert tasks.get_un_release_dates(ProductType.X, reporter_code="AS", year=2018).data == []
    assert len(tasks.get_un_release_dates(ProductType.M, reporter_code="AS", year=2018).data) == 1
    assert tasks.get_un_release_dates(ProductType.X, reporter_code="CD").data == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "endpoint", "fixture", "case", "release_list", "count", "narrow", "narrowed"),
    [
        (
            "usda_gats_get_un_exports",
            "GATSData_GetUNTradeExports",
            UN_EXPORTS,
            "IC_2019",
            UN_EXPORT_RELEASES,
            3980,
            {"partner_code": "US", "hs6_code": "0304"},
            16,
        ),
        (
            "usda_gats_get_un_imports",
            "GATSData_GetUNTradeImports",
            UN_IMPORTS,
            "TP_2019",
            UN_IMPORT_RELEASES,
            2377,
            {"hs6_code": "1006"},
            20,
        ),
        (
            "usda_gats_get_un_reexports",
            "GATSData_GetUNTradeReExports",
            UN_RE_EXPORTS,
            "MC_2019",
            UN_EXPORT_RELEASES,
            421,
            {"partner_code": "AS"},
            27,
        ),
    ],
    ids=["exports", "imports", "re_exports"],
)
async def test_the_un_data_tools_name_both_filters_when_cut(
    replay_fixture: ReplayFixture,
    tool: str,
    endpoint: str,
    fixture: str,
    case: str,
    release_list: str,
    count: int,
    narrow: dict[str, str],
    narrowed: int,
) -> None:
    """Over MCP each reporter-year is cut at the default cap with a note naming
    ``partner_code`` and ``hs6_code`` (ADR-0016); a filtered call comes back whole."""
    replay_fixture(release_list, "all")
    data = replay_fixture(fixture, case)
    url = {
        UN_EXPORTS: IC_UN_EXPORTS_URL,
        UN_IMPORTS: TP_UN_IMPORTS_URL,
        UN_RE_EXPORTS: MC_UN_RE_EXPORTS_URL,
    }[fixture]
    arguments: dict[str, object] = {"reporter_code": case[:2], "year": 2019}
    payload = await mcp_call(server, tool, arguments)
    shown = len(payload["data"])
    assert shown == 200
    assert payload["note"] == (
        f"showing {shown} of {count} rows (cap: 200 rows or 65536 bytes); {UN_DATA_NOTE}"
    )
    first = _recorded(fixture, case)[0]
    assert payload["data"][0] == {
        "year": "2019",
        "reporter_country_code": case[:2],
        "partner_country_code": first["partnerCountryCode"],
        "hs6_code": first["hS6Code"],
        "census_uom_id1": 0,
        "census_uom_id2": 0,
        "fas_converted_uom_id": 47,
        "fas_non_converted_uom_id": first["fasNonConvertedUOMId"],
        "quantity1": first["quantity1"],
        "quantity2": first["quantity2"],
        "value": first["value"],
    }, "Decimal values are JSON numbers (ADR-0008)"
    assert isinstance(payload["data"][0]["value"], float)
    assert payload["meta"]["endpoint"] == endpoint
    assert payload["meta"]["vintage"] == _un_release_time(release_list, case[:2], "2019")
    assert payload["meta"]["published_at"] == payload["meta"]["vintage"]
    assert payload["meta"]["published_at_naive"] is True
    whole = await mcp_call(server, tool, {**arguments, **narrow})
    assert len(whole["data"]) == narrowed
    assert "note" not in whole
    assert whole["meta"]["request"] == {"reporter_code": case[:2], "year": 2019, **narrow}
    assert sent_urls(data) == [url, url], "the filters are not sent upstream"
    with pytest.raises(AssertionError, match="error: UnknownCode: 'ZZ' is not a reporter_code"):
        await mcp_call(server, tool, {**arguments, "reporter_code": "ZZ"})
    with pytest.raises(AssertionError, match="error: NotFoundError: GATS has no UN Trade"):
        await mcp_call(server, tool, {**arguments, "year": 2020})


@pytest.mark.anyio
async def test_the_un_release_dates_tool_names_its_filters_when_cut(
    replay_fixture: ReplayFixture,
) -> None:
    """3,796 reporter-years over MCP: cut at 200 rows, 2019's 32, 2018's 80 and 88 of
    2017's, with a note naming ``reporter_code`` and ``year``; one reporter comes back
    whole."""
    route = replay_fixture(UN_EXPORT_RELEASES, "all")
    payload = await mcp_call(server, "usda_gats_get_un_release_dates", {"product_type": "X"})
    assert len(payload["data"]) == 200
    assert payload["data"][0] == {
        "statistical_year": "2019",
        "product_type": "X",
        "reporter_code": "AC",
        "release_time_stamp": "2020-10-11T01:15:48",
    }
    assert payload["data"][-1]["statistical_year"] == "2017"
    assert payload["note"] == (
        f"showing 200 of 3796 rows (cap: 200 rows or 65536 bytes); {UN_RELEASE_DATES_NOTE}"
    )
    iceland = await mcp_call(
        server, "usda_gats_get_un_release_dates", {"product_type": "X", "reporter_code": "IC"}
    )
    assert len(iceland["data"]) == 31
    assert "note" not in iceland
    assert iceland["meta"]["request"] == {"product_type": "X", "reporter_code": "IC"}
    assert sent_urls(route) == [UN_EXPORT_RELEASES_URL]


def test_the_un_tasks_over_http(replay_fixture: ReplayFixture) -> None:
    """The router serves the UN tasks as GET routes: values are JSON numbers, an unknown
    reporter is a 422 problem, an unlisted reporter-year a 404."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.gats.http import router

    replay_fixture(UN_EXPORT_RELEASES, "all")
    replay_fixture(UN_EXPORTS, "IC_2019")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    params: dict[str, str | int] = {"reporter_code": "IC", "year": 2019, "partner_code": "US"}
    response = http.get("/usda-gats/get_un_exports", params={**params, "hs6_code": "030444"})
    assert response.status_code == 200, response.text
    (row,) = response.json()["data"]
    assert (row["hs6_code"], row["value"]) == ("030444", 104692323.0)
    assert response.json()["meta"]["vintage"] == IC_2019_EXPORTS_RELEASED
    rejected = http.get("/usda-gats/get_un_exports", params={**params, "reporter_code": "ZZ"})
    assert rejected.status_code == 422
    assert rejected.json()["title"] == "UnknownCode"
    unlisted = http.get("/usda-gats/get_un_exports", params={**params, "year": 2020})
    assert unlisted.status_code == 404
    assert unlisted.json()["title"] == "NotFoundError"
    releases = http.get(
        "/usda-gats/get_un_release_dates", params={"product_type": "X", "year": 2019}
    )
    assert releases.status_code == 200
    assert len(releases.json()["data"]) == 32
