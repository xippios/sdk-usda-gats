"""The list tasks: five answer from the packaged lists without a call, one fetches live.

The packaged files were written from the answers recorded in
``tests/fixtures/<operation>/all.json``, so a task returning exactly what the endpoint
wrapper parses from that recording proves the package answers what upstream answered.
Every test here runs with ``respx`` active: a request no route matches fails loudly, and
each packaged-list test checks that the tasks sent none. ``list_commodities`` replays the
HS10 recording through the client, whose cache keeps it for a day; core's plugin
empties every ``MemoryCache`` around each offline test (ADR-0013).
"""

import json
from collections import Counter
from datetime import UTC, datetime
from importlib import resources
from typing import Any

import httpx
import pytest
import respx
from xippios.core import InvalidRequestError, PackagedList
from xippios.core.client import cache_key
from xippios.core.testing import ReplayFixture, mcp_call, sent_urls

from xippios.usda.gats import api, tasks
from xippios.usda.gats._client import BASE_URL, cache
from xippios.usda.gats.enums import UnitOfMeasureId
from xippios.usda.gats.mcp import server
from xippios.usda.gats.models import CustomsDistrict, Region, UnitOfMeasure
from xippios.usda.gats.params import PACKAGE

LISTS: list[tuple[str, str, str, str, int, dict[str, Any]]] = [
    # task, packaged list, its wrapper, operation it came from, records, meta.request
    # without filters, which leaves out a filter not given (ADR-0022, rule 3)
    ("list_regions", "regions", "get_regions", "GATSData_GetRegions", 15, {}),
    ("list_countries", "countries", "get_countries", "GATSData_GetCountries", 322, {}),
    (
        "list_hs6_commodities",
        "HS6Commodities",
        "get_hs6_commodities",
        "GATSData_GetHS6Commodities",
        2909,
        {},
    ),
    (
        "list_units_of_measure",
        "unitsOfMeasure",
        "get_units_of_measure",
        "GATSData_GetUnitsOfMeasure",
        108,
        {},
    ),
    (
        "list_customs_districts",
        "customsDistricts",
        "get_customs_districts",
        "GATSData_GetCustomsDistricts",
        53,
        {},
    ),
]
IDS = [task for task, *_ in LISTS]
WHOLE = ["list_regions", "list_countries", "list_units_of_measure", "list_customs_districts"]
"""The lists that reach an agent whole over MCP: three within the default cap, the
countries through a cap of their own (``tasks.MCP_CAPS``, ADR-0016)."""
CAP = 200
"""The family's default MCP result cap in rows (conventions §8)."""
COMMODITIES_URL = f"{BASE_URL}/api/gats/commodities"
HS6_NOTE = (
    "filter by search, on the code, the name and the description, e.g. '0201' or "
    "'wheat', to see the rest"
)
COMMODITIES_NOTE = (
    "filter by search (name or description, e.g. 'wheat'), by hs10_code (a code or a "
    "prefix such as '0201') or by product_type ('X' exports, 'M' imports) to see the rest"
)


def _fetched(name: str) -> datetime:
    """``fetched`` as the packaged file stores it, read from the file itself: a bare day,
    which core reads as its 00:00 UTC (ADR-0022, amendment 2026-10-27)."""
    path = resources.files("xippios.usda.gats").joinpath("reference", f"{name}.json")
    fetched = json.loads(path.read_text(encoding="utf-8"))["fetched"]
    assert isinstance(fetched, str)
    return datetime.fromisoformat(f"{fetched}T00:00:00+00:00")


def test_every_list_task_is_exported() -> None:
    import xippios.usda.gats as package

    for task in [*IDS, "list_commodities"]:
        assert task in tasks.__all__
        assert task in package.__all__
        assert getattr(package, task) is getattr(tasks, task)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("task", "name", "wrapper", "endpoint", "count", "request_"), LISTS, ids=IDS
)
async def test_list_answers_the_recorded_records_without_a_call(
    replay_fixture: ReplayFixture,
    respx_mock: respx.MockRouter,
    task: str,
    name: str,
    wrapper: str,
    endpoint: str,
    count: int,
    request_: dict[str, Any],
) -> None:
    """The recording is mounted, so a call would succeed silently; none is made."""
    route = replay_fixture(endpoint, "all")
    result = await getattr(tasks, f"{task}_async")()
    assert not respx_mock.calls, f"{task} called upstream"
    recorded = await getattr(api, wrapper)()
    assert route.call_count == 1, "the one call is the wrapper's"
    assert result.data == recorded, "same records, same values, upstream order"
    assert len(result.data) == count
    assert result.meta.source == "usda-gats"
    assert result.meta.endpoint == endpoint
    assert result.meta.retrieved_at == _fetched(name), "when the package fetched the list"
    assert result.meta.retrieved_at == PackagedList.load(PACKAGE, name).fetched
    day = 25 if name == "countries" else 26
    assert result.meta.retrieved_at == datetime(2026, 10, day, tzinfo=UTC)
    assert result.meta.vintage is None, "upstream gives the list no version; a day is none"
    assert result.meta.published_at is None
    assert result.meta.total is None
    assert result.meta.request == request_


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("task", "name", "endpoint", "request_"),
    [
        (task, name, endpoint, request_)
        for task, name, _, endpoint, _, request_ in LISTS
        if task in WHOLE
    ],
    ids=WHOLE,
)
async def test_list_tool_end_to_end_is_whole(
    respx_mock: respx.MockRouter,
    task: str,
    name: str,
    endpoint: str,
    request_: dict[str, Any],
) -> None:
    """Regions, countries, units and districts reach an agent whole, without a note."""
    payload = await mcp_call(server, f"usda_gats_{task}", {})
    rows = [record.model_dump(mode="json") for record in getattr(tasks, task)().data]
    assert payload["data"] == rows
    assert "note" not in payload
    assert payload["meta"]["source"] == "usda-gats"
    assert payload["meta"]["endpoint"] == endpoint
    assert datetime.fromisoformat(payload["meta"]["retrieved_at"]) == _fetched(name)
    assert payload["meta"]["vintage"] is None
    assert payload["meta"]["published_at"] is None
    assert payload["meta"]["request"] == request_
    assert not respx_mock.calls


@pytest.mark.anyio
async def test_countries_over_mcp_are_whole_without_a_filter_and_with_one(
    respx_mock: respx.MockRouter,
) -> None:
    """More countries than the default cap of 200 rows: ``list_countries``'s own cap of
    400 rows or 100,000 bytes lets all 322 through, about 57 KB, the last code
    included; every region and a search come back whole as well."""
    every = await mcp_call(server, "usda_gats_list_countries", {})
    countries = tasks.list_countries().data
    assert every["data"] == [country.model_dump(mode="json") for country in countries]
    assert len(every["data"]) == 322 > CAP, "past the default cap"
    assert "note" not in every
    assert every["data"][-1]["country_code"] == countries[-1].country_code
    compact = json.dumps(every["data"], separators=(",", ":")).encode()
    assert 64 * 1024 > len(compact) > 50_000
    regions = Counter(country.region_code for country in countries)
    for region_code, count in regions.items():
        payload = await mcp_call(server, "usda_gats_list_countries", {"region_code": region_code})
        assert len(payload["data"]) == count, region_code
        assert "note" not in payload, region_code
        assert payload["meta"]["request"] == {"region_code": region_code}
    united = await mcp_call(server, "usda_gats_list_countries", {"search": "united"})
    assert [row["country_code"] for row in united["data"]] == ["AE", "U0", "UK", "US"]
    assert not respx_mock.calls


def test_every_country_region_is_listed(respx_mock: respx.MockRouter) -> None:
    regions = tasks.list_regions().data
    assert regions[0] == Region(region_code="R05", region_name="North America")
    codes = {r.region_code for r in regions}
    assert {c.region_code for c in tasks.list_countries().data} <= codes
    by_region = {code: tasks.list_countries(region_code=code).data for code in codes}
    assert sum(len(countries) for countries in by_region.values()) == 322
    assert not respx_mock.calls


def test_list_countries_by_region(respx_mock: respx.MockRouter) -> None:
    every = tasks.list_countries().data
    north_america = tasks.list_countries(region_code="R05")
    assert [c.country_code for c in north_america.data] == ["CA", "GL", "MX", "SB", "US"]
    assert north_america.data == [c for c in every if c.region_code == "R05"], "upstream order"
    assert north_america.meta.request == {"region_code": "R05"}
    assert len(tasks.list_countries(region_code="R40").data) == 9
    assert len(tasks.list_countries(region_code="R55").data) == 67
    assert not respx_mock.calls


def test_an_unknown_region_is_an_empty_list(respx_mock: respx.MockRouter) -> None:
    """No validation: a region no country carries has no countries, a correct answer."""
    unknown = tasks.list_countries(region_code="R00")
    assert unknown.data == []
    assert unknown.meta.request == {"region_code": "R00"}
    assert unknown.meta.retrieved_at == datetime(2026, 10, 25, tzinfo=UTC)
    assert tasks.list_countries(region_code="r05").data == [], "exact, as list_regions spells it"
    assert not respx_mock.calls


def test_list_countries_search_matches_code_name_iso_and_genc(
    respx_mock: respx.MockRouter,
) -> None:
    united = tasks.list_countries(search="united")
    assert [c.country_code for c in united.data] == ["AE", "U0", "UK", "US"]
    assert united.meta.request == {"search": "united"}
    assert tasks.list_countries(search="UNITED").data == united.data
    china = tasks.list_countries(search="CHN").data
    assert [(c.country_code, c.iso3_code, c.genc_code) for c in china] == [("CH", "CHN", "CHN")]
    assert tasks.list_countries(search="chn").data == china
    assert [c.country_code for c in tasks.list_countries(search="che").data] == [
        "SE",  # Seychelles, by its name
        "SZ",  # Switzerland, by its ISO code CHE; discontinued in 198712
        "SR",  # Switzerland, by its ISO and GENC code CHE
        "V5",  # Seychelles and Dependents, by its name
    ]
    caribbean = tasks.list_countries(search="x21").data
    assert [(c.country_code, c.genc_code) for c in caribbean] == [("01", None)], "an ISO-only code"
    both = tasks.list_countries(region_code="R05", search="united")
    assert [c.country_code for c in both.data] == ["US"]
    assert both.meta.request == {"region_code": "R05", "search": "united"}
    assert tasks.list_countries(search="atlantis").data == []
    assert not respx_mock.calls


def test_list_countries_search_skips_a_null_genc_code(respx_mock: respx.MockRouter) -> None:
    """Upstream sends ``gencCode: null`` for 79 codes; a search passes over the null
    without raising and still finds them by code, name or ISO code."""
    every = tasks.list_countries().data
    assert sum(c.genc_code is None for c in every) == 79
    assert tasks.list_countries(search="none").data == [], "a null is not the text 'None'"
    nulls = [c for c in tasks.list_countries(search="").data if c.genc_code is None]
    assert len(nulls) == 79, "an empty search keeps every country, nulls included"
    assert not respx_mock.calls


def test_a_search_that_is_not_text_is_refused(respx_mock: respx.MockRouter) -> None:
    for task in (tasks.list_countries, tasks.list_hs6_commodities, tasks.list_commodities):
        with pytest.raises(InvalidRequestError, match="search must be text, got 2"):
            task(search=2)  # type: ignore[arg-type]
    assert not respx_mock.calls


def test_list_hs6_commodities_search(respx_mock: respx.MockRouter) -> None:
    wheat = tasks.list_hs6_commodities(search="wheat")
    assert len(wheat.data) == 15
    assert [c.hs6_code for c in wheat.data][:4] == ["100110", "100111", "100119", "100190"]
    assert wheat.meta.request == {"search": "wheat"}
    assert tasks.list_hs6_commodities(search="WHEAT").data == wheat.data
    heading = tasks.list_hs6_commodities(search="0201").data
    assert [(c.hs6_code, c.commodity_name) for c in heading] == [
        ("020110", "Bovine Carcass Fr/Ch"),
        ("020120", "Bovine Bone In Fr/Ch"),
        ("020130", "Bovine Boneless Fr/Ch"),
    ]
    assert len(tasks.list_hs6_commodities(search="bovine").data) == 42
    assert tasks.list_hs6_commodities(search="unobtainium").data == []
    assert not respx_mock.calls


@pytest.mark.anyio
async def test_hs6_commodities_over_mcp_are_cut_with_a_note_naming_search(
    respx_mock: respx.MockRouter,
) -> None:
    """2,909 codes keep the default cap: 200 rows or 64 KB, with a note naming ``search``,
    the one filter the tool has; a search comes back whole."""
    payload = await mcp_call(server, "usda_gats_list_hs6_commodities", {})
    shown = len(payload["data"])
    assert 0 < shown <= CAP
    assert payload["note"] == (
        f"showing {shown} of 2909 rows (cap: 200 rows or 65536 bytes); {HS6_NOTE}"
    )
    assert payload["data"][0]["hs6_code"] == "010110"
    wheat = await mcp_call(server, "usda_gats_list_hs6_commodities", {"search": "wheat"})
    assert len(wheat["data"]) == 15
    assert "note" not in wheat
    assert not respx_mock.calls


def test_units_name_the_ids_of_the_enum(respx_mock: respx.MockRouter) -> None:
    units = tasks.list_units_of_measure().data
    assert units[47] == UnitOfMeasure(
        unit_of_measure_id=47,
        unit_of_measure_code="KG",
        unit_of_measure_name="Kilograms",
        unit_of_measure_description="Kilograms",
    )
    assert units[47].unit_of_measure_id == UnitOfMeasureId.KILOGRAMS
    assert [u.unit_of_measure_id for u in units] == [m.value for m in UnitOfMeasureId]
    crates = [u.unit_of_measure_id for u in units if u.unit_of_measure_code == "CRT"]
    assert crates == [UnitOfMeasureId.CRATES_33, UnitOfMeasureId.CRATES_105]
    assert not respx_mock.calls


def test_customs_districts(respx_mock: respx.MockRouter) -> None:
    districts = tasks.list_customs_districts().data
    by_id = {d.customs_district_id: d for d in districts}
    assert by_id[10] == CustomsDistrict(
        customs_district_id=10,
        customs_district_name="NEW YORK, N.Y.",
        customs_district_region_code="EC",
        customs_district_region_name="EAST COAST DISTRICTS",
    )
    assert [d.customs_district_id for d in districts][:3] == [0, 1, 2]
    assert not respx_mock.calls


def test_list_commodities_fetches_live_once_and_answers_from_the_cache(
    replay_fixture: ReplayFixture,
) -> None:
    """One request for the HS10 list, which the client keeps for a day: the second call,
    with a filter, sends nothing, and its ``retrieved_at`` is when the list was stored."""
    route = replay_fixture("GATSData_GetCommodities", "all")
    every = tasks.list_commodities()
    assert route.call_count == 1, "the first call went to the wire"
    assert len(every.data) == 24936
    assert Counter(c.product_type for c in every.data) == {
        "X": 5919,
        "M": 14469,
        "T": 2704,
        "B": 1844,
    }
    assert every.meta.endpoint == "GATSData_GetCommodities"
    assert every.meta.request == {}
    assert (every.meta.vintage, every.meta.published_at, every.meta.total) == (None, None, None)
    swine = tasks.list_commodities(search="swine")
    assert route.call_count == 1, "the second call is answered from the cache"
    assert sent_urls(route) == [COMMODITIES_URL]
    entry = cache.get(cache_key("GET", httpx.URL(COMMODITIES_URL)))
    assert entry is not None
    assert swine.meta.retrieved_at == datetime.fromtimestamp(entry.stored_at, UTC)
    assert len(swine.data) == 91
    assert swine.meta.request == {"search": "swine"}


def test_list_commodities_filters(replay_fixture: ReplayFixture) -> None:
    """``search`` on the name and the description, ``hs10_code`` a prefix of the code,
    ``product_type`` exact; together they narrow, after the one request."""
    route = replay_fixture("GATSData_GetCommodities", "all")
    assert len(tasks.list_commodities(search="wheat").data) == 168
    assert (
        tasks.list_commodities(search="WHEAT").data == tasks.list_commodities(search="wheat").data
    )
    fillets = tasks.list_commodities(hs10_code="0304")
    assert len(fillets.data) == 548
    assert all(c.hs10_code.startswith("0304") for c in fillets.data)
    exports = tasks.list_commodities(hs10_code="0304", product_type="X")
    assert len(exports.data) == 114
    both = tasks.list_commodities(search="fish fillets", hs10_code="0304", product_type="X")
    assert len(both.data) == 24
    assert both.meta.request == {
        "search": "fish fillets",
        "hs10_code": "0304",
        "product_type": "X",
    }
    swine = tasks.list_commodities(hs10_code="0103910000")
    assert [(c.product_type, c.start_date) for c in swine.data] == [
        ("M", "198901"),
        ("X", "198901"),
    ]
    padded = tasks.list_commodities(hs10_code="0011010")
    assert [(c.hs10_code, c.product_type) for c in padded.data] == [("0011010   ", "B")]
    assert tasks.list_commodities(hs10_code="0011010000").data == [], (
        "a padded code is seven digits"
    )
    assert len(tasks.list_commodities(product_type="X").data) == 5919
    assert tasks.list_commodities(product_type="x").data == [], "exact, as upstream writes it"
    assert tasks.list_commodities(product_type="R").data == []
    secretions = tasks.list_commodities(search="secretions").data
    assert [(c.hs10_code, c.product_type) for c in secretions] == [
        ("0510004020", "M"),
        ("3001200000", "M"),
        ("3001200000", "X"),
    ], "upstream text the fixture's key grep matches"
    assert route.call_count == 1


def test_list_commodities_checks_hs10_code_before_the_request(
    respx_mock: respx.MockRouter,
) -> None:
    with pytest.raises(InvalidRequestError, match="hs10_code must be 1 to 10 digits"):
        tasks.list_commodities(hs10_code="03.04")
    assert not respx_mock.calls


@pytest.mark.anyio
async def test_commodities_over_mcp_are_cut_with_a_note_naming_the_filters(
    replay_fixture: ReplayFixture,
) -> None:
    """24,936 records keep the default cap with a note naming the three filters; a
    narrow query comes back whole, from the cache."""
    route = replay_fixture("GATSData_GetCommodities", "all")
    payload = await mcp_call(server, "usda_gats_list_commodities", {})
    shown = len(payload["data"])
    assert 0 < shown <= CAP
    assert payload["note"] == (
        f"showing {shown} of 24936 rows (cap: 200 rows or 65536 bytes); {COMMODITIES_NOTE}"
    )
    assert payload["data"][0]["hs10_code"] == "0011010   ", "kept as sent"
    assert payload["meta"]["vintage"] is None
    narrow = await mcp_call(
        server,
        "usda_gats_list_commodities",
        {"search": "fish fillets", "hs10_code": "0304", "product_type": "X"},
    )
    assert len(narrow["data"]) == 24
    assert "note" not in narrow
    assert route.call_count == 1


def test_list_routes_over_http(replay_fixture: ReplayFixture) -> None:
    """The cap is the MCP server's; HTTP answers every record."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.usda.gats.http import router

    replay_fixture("GATSData_GetCommodities", "all")
    app = FastAPI()
    app.include_router(router)
    http = TestClient(app)
    countries = http.get("/usda-gats/list_countries")
    assert countries.status_code == 200, countries.text
    assert len(countries.json()["data"]) == 322
    east_asia = http.get("/usda-gats/list_countries", params={"region_code": "R40"}).json()
    assert len(east_asia["data"]) == 9
    assert east_asia["meta"]["vintage"] is None
    assert datetime.fromisoformat(east_asia["meta"]["retrieved_at"]) == _fetched("countries")
    hs6 = http.get("/usda-gats/list_hs6_commodities").json()
    assert len(hs6["data"]) == 2909
    fillets = http.get(
        "/usda-gats/list_commodities", params={"hs10_code": "0304", "product_type": "X"}
    ).json()
    assert len(fillets["data"]) == 114
    rejected = http.get("/usda-gats/list_commodities", params={"hs10_code": "03.04"})
    assert rejected.status_code == 422
