"""Structural checks every task must satisfy. Per-task tests with recorded fixtures go below.

A replay test that checks what was sent compares ``xippios.core.testing.sent_urls(route)``,
the URLs the route received with credentials redacted, rather than keep a request from
``route.calls`` in its frame, where a failure or ``pytest -l`` would print it.
"""

import inspect
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import InvalidRequestError, NotFoundError
from xippios.core.client import cache_key
from xippios.core.testing import ReplayFixture, load_fixture, mcp_call, sent_urls

from xippios.usda.gats import __version__, tasks
from xippios.usda.gats._client import BASE_URL, cache
from xippios.usda.gats.errors import UnknownCode
from xippios.usda.gats.mcp import server
from xippios.usda.gats.models import DataReleaseInfo, ProductType

TASKS = [getattr(tasks, name) for name in tasks.__all__]


def test_package_has_a_version() -> None:
    assert __version__


@pytest.mark.parametrize("task", TASKS, ids=tasks.__all__)
def test_task_is_a_sync_facade_with_an_agent_docstring(task: object) -> None:
    assert callable(task)
    assert hasattr(task, "async_fn"), "write the async function and derive the sync one with sync()"
    doc = inspect.getdoc(task) or ""
    assert doc, "task functions need a docstring: agents read it"
    assert doc.splitlines()[0].endswith("."), "the first line is one sentence"
    if inspect.signature(task).parameters:
        assert "Args:" in doc, "explain every parameter under Args: with valid-value examples"


FIXTURES = Path(__file__).parent / "fixtures"
EXPORTS = "GATSData_GetCensusExports"
IMPORTS = "GATSData_GetCensusImport"
EXPORT_RELEASES = "GATSData_GetCensusExportDataReleaseInfo"
IMPORT_RELEASES = "GATSData_GetCensusImportDataReleaseInfo"
EXPORT_RELEASES_URL = f"{BASE_URL}/api/gats/census/data/exports/dataReleaseDates"
IMPORT_RELEASES_URL = f"{BASE_URL}/api/gats/census/data/imports/dataReleaseDates"
CH_EXPORTS_URL = f"{BASE_URL}/api/gats/censusExports/partnerCode/CH/year/2026/month/8"
CH_IMPORTS_URL = f"{BASE_URL}/api/gats/censusImports/partnerCode/CH/year/2026/month/8"
HS10_NOTE = "filter by hs10_code, a full code or a prefix such as the chapter '02', to see the rest"
RELEASE_DATES_NOTE = (
    "the list runs newest first, so the rows shown are the latest released months; "
    "200 months reach back more than sixteen years"
)
RELEASED_2026_08 = "2026-10-06T08:00:00"
"""``releaseTimeStamp`` of ``"202608"`` in both recorded release lists, as upstream wrote it."""


@pytest.fixture(autouse=True)
def empty_cache() -> Iterator[None]:
    """The client caches the release-date lists for an hour and the commodities list for
    a day (``_client.cache``): each test starts and ends without an entry, so a list one
    test fetched never answers the route the next test mounted."""
    cache.clear()
    yield
    cache.clear()


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
        "hs10_code": None,
    }
    assert result.meta.vintage == RELEASED_2026_08 == _release_time(EXPORT_RELEASES, "202608")
    assert result.meta.published_at is None
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
        "hs10_code": None,
    }
    assert result.meta.vintage == RELEASED_2026_08 == _release_time(IMPORT_RELEASES, "202608")
    assert result.meta.published_at is None
    assert {r.date for r in result.data} == {"202608"}
    assert sent_urls(releases) == [IMPORT_RELEASES_URL]
    assert sent_urls(data) == [CH_IMPORTS_URL]


def test_vintage_is_the_months_release_time_as_upstream_states_it(
    replay_fixture: ReplayFixture,
) -> None:
    """The month's release record carries ``2026-10-06T08:00:00`` without a time zone:
    ``vintage`` is that text, the naive time written back with ``isoformat()``, and
    ``published_at`` stays ``None``, since ``ResultMeta`` takes only an aware time; the
    month itself is in ``meta.request``."""
    replay_fixture(EXPORT_RELEASES, "all")
    replay_fixture(EXPORTS, "CH_2026_8")
    result = tasks.get_census_exports("CH", 2026, 8)
    assert result.meta.published_at is None
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
    assert second.meta.retrieved_at >= first.meta.retrieved_at, "the data is fetched anew"


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
    assert result.meta.published_at is None
    assert result.meta.request == {
        "partner_code": "BV",
        "year": 2026,
        "month": 8,
        "hs10_code": None,
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
    assert "fetched at" not in message, "the list came from the wire"
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
    assert unknown.value.closest == []
    assert 'e.g. "CH" (China), "MX" (Mexico)' in unknown.value.message
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
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize(
    ("product_type", "endpoint", "fixture", "url"),
    [
        (ProductType.X, EXPORT_RELEASES, EXPORT_RELEASES, EXPORT_RELEASES_URL),
        (ProductType.M, IMPORT_RELEASES, IMPORT_RELEASES, IMPORT_RELEASES_URL),
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
    assert len(result.data) == 716
    assert result.data[0].statistical_year_month == "202608"
    assert result.data[-1].statistical_year_month == "196701"
    assert {r.product_type for r in result.data} == {product_type}
    assert result.meta.endpoint == endpoint
    assert result.meta.request == {"product_type": product_type.value}
    assert (result.meta.published_at, result.meta.vintage) == (None, None)
    assert result.meta.retrieved_at >= before, "fetched now, from the wire"
    assert sent_urls(route) == [url]


def test_a_plain_code_is_a_product_type(replay_fixture: ReplayFixture) -> None:
    replay_fixture(IMPORT_RELEASES, "all")
    result = tasks.get_census_release_dates("M")  # type: ignore[arg-type]
    assert result.meta.endpoint == IMPORT_RELEASES
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
    assert 0 < shown <= 200
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
    assert payload["meta"]["published_at"] is None
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
    assert payload["note"].endswith(f"of 3294 rows (cap: 200 rows or 65536 bytes); {HS10_NOTE}")


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
