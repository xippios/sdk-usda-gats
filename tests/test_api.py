"""Replay tests for the endpoint wrappers (layer 1), against recorded answers.

What was sent is compared through ``sent_urls(route)``, the URLs with credentials redacted,
never a request kept from ``route.calls``.
"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from xippios.core import NotFoundError
from xippios.core.testing import ReplayFixture, load_fixture, sent_urls

from xippios.usda.gats import api
from xippios.usda.gats._client import BASE_URL, classify
from xippios.usda.gats.models import (
    CensusExport,
    CensusImport,
    Country,
    DataReleaseInfo,
    ProductType,
)

pytestmark = pytest.mark.anyio

SNAPSHOT = Path(__file__).parents[1] / "docs" / "upstream" / "openapi" / "portal-document.json"
EXPORTS = "GATSData_GetCensusExports"


async def test_get_countries(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCountries", "all")
    countries = await api.GATSData_GetCountries()
    assert len(countries) == 322
    by_code = {c.country_code: c for c in countries}
    assert len(by_code) == 322, "no code twice"
    assert by_code["CH"] == Country(
        country_code="CH",
        region_code="R40",
        country_parent_code="CH",
        country_name="China",
        description=None,
        iso3_code="CHN",
        discontinued_on=None,
        genc_code="CHN",
    )
    assert by_code["HM"].country_parent_code == "AS"
    assert by_code["GE"].discontinued_on == "199009"
    assert "ZZ" not in by_code, "the unknown_partner probe's code"
    assert sum(c.discontinued_on is not None for c in countries) == 26
    assert sum(c.genc_code is None for c in countries) == 79
    assert {c.description for c in countries} == {None}
    assert all(len(c.country_code) == 2 for c in countries)
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/countries"]


async def test_models_serialise_snake_case(replay_fixture: ReplayFixture) -> None:
    replay_fixture("GATSData_GetCountries", "all")
    country = (await api.GATSData_GetCountries())[0]
    assert country.model_dump(mode="json") == {
        "country_code": "01",
        "region_code": "R99",
        "country_parent_code": "01",
        "country_name": "Caribbean,nes",
        "description": None,
        "iso3_code": "X21",
        "discontinued_on": None,
        "genc_code": None,
    }


async def test_get_census_export_release_dates(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    releases = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert len(releases) == 716
    assert releases[0] == DataReleaseInfo(
        statistical_year_month="202608",
        product_type="X",
        reporter_code="US",
        release_time_stamp=datetime(2026, 10, 6, 8, 0),
    )
    assert releases[0].release_time_stamp.tzinfo is None, "upstream sends no time zone"
    assert releases[-1].statistical_year_month == "196701"
    months = [r.statistical_year_month for r in releases]
    assert months == sorted(months, reverse=True), "newest first, one record per month"
    assert len(set(months)) == 716
    assert {(r.product_type, r.reporter_code) for r in releases} == {("X", "US")}
    by_month = {r.statistical_year_month: r.release_time_stamp for r in releases}
    assert by_month["202512"] == by_month["202305"] == datetime(2026, 6, 24, 8, 0), (
        "the last release of a month: the annual revision re-released 2023 to 2025"
    )
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/census/data/exports/dataReleaseDates"]


async def test_get_census_import_release_dates(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCensusImportDataReleaseInfo", "all")
    replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    imports = await api.GATSData_GetCensusImportDataReleaseInfo()
    exports = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert len(imports) == 716
    assert imports[0] == DataReleaseInfo(
        statistical_year_month="202608",
        product_type="M",
        reporter_code="US",
        release_time_stamp=datetime(2026, 10, 6, 8, 0),
    )
    assert {(r.product_type, r.reporter_code) for r in imports} == {("M", "US")}
    assert [r.statistical_year_month for r in imports] == [
        r.statistical_year_month for r in exports
    ]
    differ = [
        i.statistical_year_month
        for i, x in zip(imports, exports, strict=True)
        if i.release_time_stamp != x.release_time_stamp
    ]
    assert differ == ["200811", "200809", "200808", "200804", "200802", "200801"]
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/census/data/imports/dataReleaseDates"]


async def test_get_census_exports(replay_fixture: ReplayFixture) -> None:
    """One partner-month across all products, whole: 777 records, 153,835 bytes."""
    route = replay_fixture(EXPORTS, "CH_2026_8")
    records = await api.GATSData_GetCensusExports("CH", 2026, 8)
    assert len(records) == 777
    assert records[0] == CensusExport(
        date="202608",
        country_code="CH",
        hs10_code="0103910000",
        census_uom_id1=78,
        census_uom_id2=78,
        fas_converted_uom_id=78,
        fas_non_converted_uom_id=78,
        quantity1=Decimal("394.0"),
        quantity2=Decimal("0.0"),
        value=Decimal("20672.0"),
    )
    assert {(r.date, r.country_code) for r in records} == {("202608", "CH")}
    assert len({r.hs10_code for r in records}) == 777, "one record per HS10 code"
    assert all(len(r.hs10_code) == 10 and r.hs10_code.isdigit() for r in records)
    assert sum(r.value for r in records) == Decimal("781424244.0")
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/censusExports/partnerCode/CH/year/2026/month/8"
    ]


async def test_get_census_import(replay_fixture: ReplayFixture) -> None:
    """The largest answer in the family so far: 3,294 records, 1,099,638 bytes."""
    route = replay_fixture("GATSData_GetCensusImport", "CH_2026_8")
    records = await api.GATSData_GetCensusImport("CH", 2026, 8)
    assert len(records) == 3294
    assert records[0] == CensusImport(
        consumption_quantity1=Decimal("9640.0"),
        consumption_quantity2=Decimal("0.0"),
        consumption_value=Decimal("1111254.0"),
        consumption_cif_value=Decimal("1166564.0"),
        cif_value=Decimal("55310.0"),
        date="202608",
        country_code="CH",
        hs10_code="0106199195",
        census_uom_id1=78,
        census_uom_id2=78,
        fas_converted_uom_id=78,
        fas_non_converted_uom_id=78,
        quantity1=Decimal("9640.0"),
        quantity2=Decimal("0.0"),
        value=Decimal("1111254.0"),
    )
    assert {(r.date, r.country_code) for r in records} == {("202608", "CH")}
    assert len({r.hs10_code for r in records}) == 3294, "one record per HS10 code"
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/censusImports/partnerCode/CH/year/2026/month/8"
    ]


async def test_imports_carry_every_export_field_and_five_more() -> None:
    assert set(CensusImport.model_fields) - set(CensusExport.model_fields) == {
        "consumption_quantity1",
        "consumption_quantity2",
        "consumption_value",
        "consumption_cif_value",
        "cif_value",
    }
    assert set(CensusExport.model_fields) < set(CensusImport.model_fields)


async def test_the_partner_code_is_quoted_into_the_path(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(EXPORTS, "unknown_partner")
    assert await api.GATSData_GetCensusExports("ZZ", 2026, 8) == []
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/censusExports/partnerCode/ZZ/year/2026/month/8"
    ]


@pytest.mark.parametrize(
    ("case", "partner_code", "year", "month"),
    [
        ("unknown_partner", "ZZ", 2026, 8),
        ("future_month", "CH", 2035, 1),
        ("no_data_valid_partner", "BV", 2026, 8),
    ],
)
async def test_unknown_partner_future_month_and_no_trade_all_answer_an_empty_list(
    replay_fixture: ReplayFixture, case: str, partner_code: str, year: int, month: int
) -> None:
    """As recorded: a code the countries list lacks (``ZZ``), a month after the latest
    release and a listed partner without trade (Bouvet Island) answer alike, HTTP 200 with
    ``[]``; nothing in the answer tells them apart."""
    route = replay_fixture(EXPORTS, case)
    assert await api.GATSData_GetCensusExports(partner_code, year, month) == []
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/censusExports/partnerCode/{partner_code}/year/{year}/month/{month}"
    ]


@pytest.mark.parametrize(("case", "month"), [("month_0", 0), ("month_13", 13)])
async def test_a_month_out_of_range_is_an_empty_404_and_a_not_found_error(
    replay_fixture: ReplayFixture, fixtures_dir: Path, case: str, month: int
) -> None:
    """As recorded: month 0 (no whole year) and month 13 answer HTTP 404 with an empty
    ``text/plain`` body. ``classify`` leaves it to core's status mapping, a
    ``NotFoundError`` naming the method and path."""
    fixture = json.loads((fixtures_dir / EXPORTS / f"{case}.json").read_text(encoding="utf-8"))
    headers = dict(fixture["response"]["headers"])
    assert (fixture["response"]["status"], fixture["response"]["body"]) == (404, "")
    assert headers["content-type"] == "text/plain; charset=utf-8"
    route = replay_fixture(EXPORTS, case)
    path = f"/api/gats/censusExports/partnerCode/CH/year/2026/month/{month}"
    with pytest.raises(NotFoundError) as info:
        await api.GATSData_GetCensusExports("CH", 2026, month)
    assert info.value.message == f"404 from GET {path}: Not Found"
    assert "api.fas.usda.gov" not in info.value.message, "host-free (conventions §5)"
    assert route.call_count == 1, "a 404 is never retried"
    assert sent_urls(route) == [f"{BASE_URL}{path}"]


async def test_classify_leaves_every_census_probe_to_core(fixtures_dir: Path) -> None:
    """No GATS-specific mapping yet: the Census answers fall through ``classify``."""
    for case in ("month_0", "month_13", "unknown_partner", "future_month"):
        fixture = load_fixture(fixtures_dir / EXPORTS / f"{case}.json")
        response = httpx.Response(
            fixture.response.status,
            headers=fixture.response.headers,
            content=fixture.response.content,
            request=httpx.Request(fixture.request.method, fixture.request.url),
        )
        assert classify(response) is None, case


async def test_product_type_members_are_the_snapshots_path_words() -> None:
    """The members spell the path segments of the four release-date operations; the
    snapshot has no release-date operation for re-exports."""
    paths = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    assert [m.value for m in ProductType] == ["exports", "imports"]
    for member in ProductType:
        assert f"/api/gats/census/data/{member}/dataReleaseDates" in paths
        assert f"/api/gats/UNTrade/data/{member}/dataReleaseDates" in paths
    release_paths = {p for p in paths if p.endswith("/dataReleaseDates")}
    assert len(release_paths) == 4
    assert not any("reexport" in p.lower() for p in release_paths)
