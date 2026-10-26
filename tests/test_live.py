"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

One live smoke test per task function, thirteen tasks in all, fourteen keyed calls. Each
data task spends one call for its month, and its release list once per flow: the tests
share the client's cache, so ``get_census_exports`` fetches the exports list and
``get_census_imports`` the imports list, and ``get_census_release_dates``, the re-export
tasks and the customs-district tasks answer their check from the cache. The data tasks
ask for Iceland (``"IC"``), a listed partner with modest trade, so the nightly run stays
light, in August 2026, released on 2026-10-06; ``vintage`` is that month's release time
as upstream writes it, a date and a time without a zone. The five packaged lists answer
without a call, so their test fetches each list through its endpoint wrapper, one call
each, and checks that the packaged records equal it: the freshness check
``reference/README.md`` promises. A difference fails the test naming what is gone and
what is new; ``/refresh-reference-data`` then refreshes the package. ``list_commodities``
fetches the HS10 list live, one call of about 7.6 MB. The tests record what they answered
as test properties (``--junitxml`` shows them), never a key. Next to them, the template's
reachability check, ``test_upstream_answers``, sends no key: a plain request to
``BASE_URL`` that spends no quota call.
"""

import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from xippios.core import UpstreamModel

from xippios.usda.gats import api, tasks
from xippios.usda.gats._client import BASE_URL, config, policy
from xippios.usda.gats.models import ProductType
from xippios.usda.gats.params import packaged_values, validate_partner_code

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


def _quota_is_the_gateways() -> None:
    snapshot = policy.snapshot()
    assert snapshot is not None
    assert snapshot.limit == 1000


async def test_get_census_exports_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_census_exports_async(PARTNER, YEAR, MONTH)
    assert result.data
    assert {(r.country_code, r.date) for r in result.data} == {(PARTNER, "202608")}
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.published_at is None
    _quota_is_the_gateways()
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


async def test_get_census_imports_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_census_imports_async(PARTNER, YEAR, MONTH)
    assert result.data
    assert {(r.country_code, r.date) for r in result.data} == {(PARTNER, "202608")}
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.published_at is None
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
    assert result.meta.published_at is None
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


def _districts() -> set[int]:
    packaged = packaged_values("customsDistricts")
    assert packaged is not None
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
    assert result.meta.published_at is None
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
        f"{task} is behind upstream (packaged {packaged.meta.vintage}): {len(stale)} packaged "
        f"records upstream no longer sends, {len(new)} upstream records the package lacks; "
        f"first of each: {stale[:5]}, {new[:5]}. Refresh with /refresh-reference-data."
    )
    assert ours == theirs, f"{task}: the same records in another order"
    assert packaged.meta.endpoint == endpoint
