"""Replay tests for the endpoint wrappers (layer 1), against recorded answers.

What was sent is compared through ``sent_urls(route)``, the URLs with credentials redacted,
never a request kept from ``route.calls``.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import NotFoundError, UpstreamModel
from xippios.core.testing import ReplayFixture, load_fixture, sent_urls

from xippios.usda.gats import api
from xippios.usda.gats._client import BASE_URL, cache, classify
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

pytestmark = pytest.mark.anyio

SNAPSHOT = Path(__file__).parents[1] / "docs" / "upstream" / "openapi" / "portal-document.json"
EXPORTS = "GATSData_GetCensusExports"
RE_EXPORTS = "GATSData_GetCensusReExports"
DISTRICT_EXPORTS = "GATSData_GetCustomsDistrictsExports"
DISTRICT_IMPORTS = "GATSData_GetCustomsDistrictsImports"
DISTRICT_RE_EXPORTS = "GATSData_GetCustomsDistrictsReExports"


def recorded_keys(fixtures_dir: Path, endpoint: str, case: str) -> set[tuple[str, ...]]:
    """The key orders of a recorded answer's records, as upstream sent them."""
    fixture = load_fixture(fixtures_dir / endpoint / f"{case}.json")
    return {tuple(record) for record in json.loads(fixture.response.content)}


def aliases(model: type[UpstreamModel]) -> tuple[str, ...]:
    """A model's upstream field names, in its field order."""
    return tuple(str(field.validation_alias) for field in model.model_fields.values())


def units(record: CensusExport | CustomsDistrictExport) -> tuple[int, int, int, int]:
    """A record's four unit-of-measure ids."""
    return (
        record.census_uom_id1,
        record.census_uom_id2,
        record.fas_converted_uom_id,
        record.fas_non_converted_uom_id,
    )


@pytest.fixture(autouse=True)
def empty_cache() -> Iterator[None]:
    """The client caches the release-date lists for an hour and the commodities list for
    a day (``_client.cache``): each test starts and ends without an entry, so a list one
    test fetched never answers the route the next test mounted."""
    cache.clear()
    yield
    cache.clear()


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


async def test_get_regions(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetRegions", "all")
    replay_fixture("GATSData_GetCountries", "all")
    regions = await api.GATSData_GetRegions()
    assert len(regions) == 15
    assert regions[0] == Region(region_code="R05", region_name="North America")
    by_code = {r.region_code: r.region_name for r in regions}
    assert len(by_code) == 15, "no code twice"
    assert [r.region_code for r in regions] == sorted(by_code), "in code order"
    assert by_code["R40"] == "East Asia"
    countries = await api.GATSData_GetCountries()
    assert {c.region_code for c in countries} <= set(by_code), "every country's region"
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/regions"]


async def test_get_commodities(replay_fixture: ReplayFixture) -> None:
    """The HS10 list whole: 24,936 records, 8,383,278 bytes as a fixture file, the largest
    in the family. Product types ``T`` and ``B`` carry seven digits padded with three
    spaces, kept as sent; code, product type and start month are unique together."""
    route = replay_fixture("GATSData_GetCommodities", "all")
    records, stored = await api.GATSData_GetCommodities()
    assert stored is None, "from the wire, not from the cache"
    assert len(records) == 24936
    by_key = {(r.hs10_code, r.product_type, r.start_date): r for r in records}
    assert len(by_key) == 24936, "code, product type and start month are unique together"
    assert by_key[("0103910000", "X", "198901")] == Commodity(
        hs10_code="0103910000",
        start_date="198901",
        end_dtate=None,
        product_type="X",
        commodity_name="SWINE,<50KG EACH",
        commodity_description="SWINE, LIVE, NESOI, WEIGHING LESS THAN 50 KG EACH  (NO)",
        is_ag_commodity=False,
        census_uom_id1=78,
        census_uom_id2=78,
        fas_converted_uom_id=78,
        fas_non_converted_uom_id=78,
    )
    assert records[0] == Commodity(
        hs10_code="0011010   ",
        start_date="196701",
        end_dtate=None,
        product_type="B",
        commodity_name="CTL,DAIRY,BREDNG",
        commodity_description=None,
        is_ag_commodity=False,
        census_uom_id1=78,
        census_uom_id2=78,
        fas_converted_uom_id=78,
        fas_non_converted_uom_id=78,
    ), "a padded code, kept as sent"
    assert Counter(r.product_type for r in records) == {
        "X": 5919,
        "M": 14469,
        "T": 2704,
        "B": 1844,
    }
    padded = [r for r in records if r.product_type in {"T", "B"}]
    assert {(r.hs10_code[7:], r.hs10_code[:7].isdigit()) for r in padded} == {("   ", True)}
    assert {r.commodity_description for r in padded} == {None}
    assert all(
        len(r.hs10_code) == 10 and r.hs10_code.isdigit()
        for r in records
        if r.product_type in {"X", "M"}
    )
    assert {r.end_dtate for r in records} == {None}, "upstream's endDtate, null throughout"
    assert sum(r.is_ag_commodity for r in records) == 13870
    assert isinstance(records[0].census_uom_id1, int)
    assert len({r.hs10_code for r in records}) == 20702, "a code repeats across product types"
    ducks = by_key[("0207410000", "M", "201201")]
    assert ducks.commodity_description == "DUCKS, WHOLE, FRESH OR CHILLED"
    assert by_key[("0207410000", "M", "198901")].commodity_name == "CCTS&EDOF(XL)FRZ"
    codes = [r.hs10_code for r in records]
    assert codes == sorted(codes), "in code order"
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/commodities"]


async def test_get_hs6_commodities(replay_fixture: ReplayFixture) -> None:
    """The HS6 list whole: 2,909 records, 720,749 bytes as a fixture file."""
    route = replay_fixture("GATSData_GetHS6Commodities", "all")
    records = await api.GATSData_GetHS6Commodities()
    assert len(records) == 2909
    assert records[0] == HS6Commodity(
        hs6_code="010110",
        commodity_name="Purebred Breeding Animal",
        commodity_description="Purebred Breeding Animal",
        census_uom_id1=78,
        census_uom_id2=78,
        fas_converted_uom_id=78,
        fas_non_converted_uom_id=78,
    )
    codes = [r.hs6_code for r in records]
    assert codes == sorted(set(codes)), "in code order, no code twice"
    assert all(len(c) == 6 and c.isdigit() for c in codes)
    assert sum(r.commodity_name == r.commodity_description for r in records) == 1376
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/HS6Commodities"]


async def test_get_units_of_measure(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetUnitsOfMeasure", "all")
    records = await api.GATSData_GetUnitsOfMeasure()
    assert [u.unit_of_measure_id for u in records] == list(range(108)), "0 to 107, no gap"
    by_id = {u.unit_of_measure_id: u for u in records}
    assert by_id[47] == UnitOfMeasure(
        unit_of_measure_id=47,
        unit_of_measure_code="KG",
        unit_of_measure_name="Kilograms",
        unit_of_measure_description="Kilograms",
    )
    assert by_id[0].unit_of_measure_code == "NONE"
    crates = [u.unit_of_measure_id for u in records if u.unit_of_measure_code == "CRT"]
    assert crates == [33, 105], "an id is unique, a code is not"
    assert all(u.unit_of_measure_name == u.unit_of_measure_description for u in records)
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/unitsOfMeasure"]


async def test_get_customs_districts(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCustomsDistricts", "all")
    records = await api.GATSData_GetCustomsDistricts()
    assert len(records) == 53
    ids = [d.customs_district_id for d in records]
    assert ids == sorted(set(ids)), "in id order, no id twice"
    assert (ids[0], ids[-1]) == (0, 99)
    by_id = {d.customs_district_id: d for d in records}
    assert by_id[10] == CustomsDistrict(
        customs_district_id=10,
        customs_district_name="NEW YORK, N.Y.",
        customs_district_region_code="EC",
        customs_district_region_name="EAST COAST DISTRICTS",
    )
    assert by_id[0].customs_district_name == "Z UNKNOW CDIST CODES"
    regions = {(d.customs_district_region_code, d.customs_district_region_name) for d in records}
    assert {code for code, _ in regions} == {"EC", "GL", "GP", "WC", "OP"}
    assert len(regions) == 5, "one name per region code"
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/customsDistricts"]


async def test_get_census_export_release_dates(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    releases, stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert stored is None, "from the wire, not from the cache"
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
    imports, _ = await api.GATSData_GetCensusImportDataReleaseInfo()
    exports, _ = await api.GATSData_GetCensusExportDataReleaseInfo()
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


async def test_the_census_and_district_answers_carry_the_models_fields_in_order(
    fixtures_dir: Path,
) -> None:
    """Why the models are shared as they are: re-exports answer the exports' ten fields, in
    their order; a customs-district answer puts ``customsDistrictId`` before the exports'
    or the imports' fields, re-exports again like exports."""
    exports = aliases(CensusExport)
    assert recorded_keys(fixtures_dir, EXPORTS, "CH_2026_8") == {exports}
    assert recorded_keys(fixtures_dir, RE_EXPORTS, "IC_2026_8") == {exports}
    assert aliases(CustomsDistrictExport) == ("customsDistrictId", *exports)
    for endpoint, case in [
        (DISTRICT_EXPORTS, "IC_2026_8"),
        (DISTRICT_EXPORTS, "CH_2026_8"),
        (DISTRICT_RE_EXPORTS, "IC_2026_8"),
    ]:
        assert recorded_keys(fixtures_dir, endpoint, case) == {aliases(CustomsDistrictExport)}
    assert aliases(CustomsDistrictImport) == ("customsDistrictId", *aliases(CensusImport))
    assert recorded_keys(fixtures_dir, DISTRICT_IMPORTS, "IC_2026_8") == {
        aliases(CustomsDistrictImport)
    }


async def test_get_census_re_exports(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(RE_EXPORTS, "IC_2026_8")
    records = await api.GATSData_GetCensusReExports("IC", 2026, 8)
    assert len(records) == 12
    assert records[0] == CensusExport(
        date="202608",
        country_code="IC",
        hs10_code="0709202000",
        census_uom_id1=47,
        census_uom_id2=47,
        fas_converted_uom_id=70,
        fas_non_converted_uom_id=70,
        quantity1=Decimal("700.0"),
        quantity2=Decimal("0.0"),
        value=Decimal("5439.0"),
    )
    assert {(r.date, r.country_code) for r in records} == {("202608", "IC")}
    assert len({r.hs10_code for r in records}) == 12, "one record per HS10 code"
    assert sum(r.value for r in records) == Decimal("169933.0")
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/censusReExports/partnerCode/IC/year/2026/month/8"
    ]


async def test_get_customs_districts_exports(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(DISTRICT_EXPORTS, "IC_2026_8")
    records = await api.GATSData_GetCustomsDistrictsExports("IC", 2026, 8)
    assert len(records) == 107
    assert records[0] == CustomsDistrictExport(
        customs_district_id=1,
        date="202608",
        country_code="IC",
        hs10_code="0713202000",
        census_uom_id1=47,
        census_uom_id2=47,
        fas_converted_uom_id=70,
        fas_non_converted_uom_id=70,
        quantity1=Decimal("1162.0"),
        quantity2=Decimal("0.0"),
        value=Decimal("6905.0"),
    )
    assert {(r.date, r.country_code) for r in records} == {("202608", "IC")}
    assert len({r.customs_district_id for r in records}) == 14, "several districts"
    pairs = {(r.customs_district_id, r.hs10_code) for r in records}
    assert len(pairs) == 107, "one record per district and HS10 code"
    assert len({r.hs10_code for r in records}) == 92
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/customsDistrictExports/partnerCode/IC/year/2026/month/8"
    ]


@pytest.mark.parametrize(
    ("wrapper", "district_endpoint", "national", "national_endpoint", "partner_code", "count"),
    [
        (
            api.GATSData_GetCustomsDistrictsExports,
            DISTRICT_EXPORTS,
            api.GATSData_GetCensusExports,
            EXPORTS,
            "CH",
            1697,
        ),
        (
            api.GATSData_GetCustomsDistrictsReExports,
            DISTRICT_RE_EXPORTS,
            api.GATSData_GetCensusReExports,
            RE_EXPORTS,
            "IC",
            13,
        ),
    ],
    ids=["exports_CH", "re_exports_IC"],
)
async def test_district_records_add_up_to_the_census_record_of_their_code(
    replay_fixture: ReplayFixture,
    wrapper: Callable[[str, int, int], Awaitable[list[CustomsDistrictExport]]],
    district_endpoint: str,
    national: Callable[[str, int, int], Awaitable[list[CensusExport]]],
    national_endpoint: str,
    partner_code: str,
    count: int,
) -> None:
    """As recorded for August 2026: over the districts, an HS10 code's records add up to
    its record in the answer without districts, with the same unit ids. China's
    customs-district exports are the size probe: 1,697 records in 31 districts, 422,882
    bytes as a fixture file."""
    case = f"{partner_code}_2026_8"
    route = replay_fixture(district_endpoint, case)
    replay_fixture(national_endpoint, case)
    by_district = await wrapper(partner_code, 2026, 8)
    by_code = {r.hs10_code: r for r in await national(partner_code, 2026, 8)}
    assert len(by_district) == count
    totals: defaultdict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0)] * 3)
    for r in by_district:
        total = totals[r.hs10_code]
        total[0] += r.quantity1
        total[1] += r.quantity2
        total[2] += r.value
        assert units(r) == units(by_code[r.hs10_code]), r.hs10_code
    assert totals == {code: [r.quantity1, r.quantity2, r.value] for code, r in by_code.items()}
    assert len(sent_urls(route)) == 1


async def test_get_customs_districts_exports_for_china(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(DISTRICT_EXPORTS, "CH_2026_8")
    records = await api.GATSData_GetCustomsDistrictsExports("CH", 2026, 8)
    assert len(records) == 1697
    assert len({r.customs_district_id for r in records}) == 31
    assert len({r.hs10_code for r in records}) == 777, "the codes of the Census exports"
    assert sum(r.value for r in records) == Decimal("781424244.0")
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/customsDistrictExports/partnerCode/CH/year/2026/month/8"
    ]


async def test_get_customs_districts_imports(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(DISTRICT_IMPORTS, "IC_2026_8")
    records = await api.GATSData_GetCustomsDistrictsImports("IC", 2026, 8)
    assert len(records) == 123
    assert records[0] == CustomsDistrictImport(
        customs_district_id=1,
        consumption_quantity1=Decimal("571053.0"),
        consumption_quantity2=Decimal("0.0"),
        consumption_value=Decimal("4814084.0"),
        consumption_cif_value=Decimal("4985562.0"),
        cif_value=Decimal("171478.0"),
        date="202608",
        country_code="IC",
        hs10_code="0302140003",
        census_uom_id1=47,
        census_uom_id2=47,
        fas_converted_uom_id=70,
        fas_non_converted_uom_id=70,
        quantity1=Decimal("571053.0"),
        quantity2=Decimal("0.0"),
        value=Decimal("4814084.0"),
    )
    assert {(r.date, r.country_code) for r in records} == {("202608", "IC")}
    assert len({r.customs_district_id for r in records}) == 21, "several districts"
    pairs = {(r.customs_district_id, r.hs10_code) for r in records}
    assert len(pairs) == 123, "one record per district and HS10 code"
    assert len({r.hs10_code for r in records}) == 74
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/customsDistrictImports/partnerCode/IC/year/2026/month/8"
    ]


async def test_get_customs_districts_re_exports(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(DISTRICT_RE_EXPORTS, "IC_2026_8")
    records = await api.GATSData_GetCustomsDistrictsReExports("IC", 2026, 8)
    assert len(records) == 13
    assert records[0] == CustomsDistrictExport(
        customs_district_id=1,
        date="202608",
        country_code="IC",
        hs10_code="1905901049",
        census_uom_id1=47,
        census_uom_id2=47,
        fas_converted_uom_id=70,
        fas_non_converted_uom_id=70,
        quantity1=Decimal("18018.0"),
        quantity2=Decimal("0.0"),
        value=Decimal("34257.0"),
    )
    assert {(r.date, r.country_code) for r in records} == {("202608", "IC")}
    assert len({r.customs_district_id for r in records}) == 5, "several districts"
    assert len({(r.customs_district_id, r.hs10_code) for r in records}) == 13
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/customsDistrictReExports/partnerCode/IC/year/2026/month/8"
    ]


async def test_the_lists_name_every_unit_district_and_hs6_code_the_answers_carry(
    replay_fixture: ReplayFixture,
) -> None:
    """Every unit-of-measure id and customs district in the recorded Census answers is
    listed, and the first six digits of every HS10 code are a listed HS6 code."""
    for endpoint in ("GATSData_GetUnitsOfMeasure", "GATSData_GetCustomsDistricts"):
        replay_fixture(endpoint, "all")
    replay_fixture("GATSData_GetHS6Commodities", "all")
    for endpoint, case in [
        (EXPORTS, "CH_2026_8"),
        ("GATSData_GetCensusImport", "CH_2026_8"),
        (RE_EXPORTS, "IC_2026_8"),
        (DISTRICT_EXPORTS, "IC_2026_8"),
        (DISTRICT_IMPORTS, "IC_2026_8"),
        (DISTRICT_RE_EXPORTS, "IC_2026_8"),
    ]:
        replay_fixture(endpoint, case)
    unit_ids = {u.unit_of_measure_id for u in await api.GATSData_GetUnitsOfMeasure()}
    district_ids = {d.customs_district_id for d in await api.GATSData_GetCustomsDistricts()}
    hs6_codes = {c.hs6_code for c in await api.GATSData_GetHS6Commodities()}
    census: list[CensusExport | CensusImport] = [
        *await api.GATSData_GetCensusExports("CH", 2026, 8),
        *await api.GATSData_GetCensusImport("CH", 2026, 8),
        *await api.GATSData_GetCensusReExports("IC", 2026, 8),
    ]
    districts: list[CustomsDistrictExport | CustomsDistrictImport] = [
        *await api.GATSData_GetCustomsDistrictsExports("IC", 2026, 8),
        *await api.GATSData_GetCustomsDistrictsImports("IC", 2026, 8),
        *await api.GATSData_GetCustomsDistrictsReExports("IC", 2026, 8),
    ]
    records = [*census, *districts]
    assert {
        unit
        for r in records
        for unit in (
            r.census_uom_id1,
            r.census_uom_id2,
            r.fas_converted_uom_id,
            r.fas_non_converted_uom_id,
        )
    } <= unit_ids
    assert {r.customs_district_id for r in districts} <= district_ids
    assert {r.hs10_code[:6] for r in records} <= hs6_codes


@pytest.mark.parametrize(
    ("wrapper", "path"),
    [
        (api.GATSData_GetCensusExports, "censusExports"),
        (api.GATSData_GetCensusImport, "censusImports"),
        (api.GATSData_GetCensusReExports, "censusReExports"),
        (api.GATSData_GetCustomsDistrictsExports, "customsDistrictExports"),
        (api.GATSData_GetCustomsDistrictsImports, "customsDistrictImports"),
        (api.GATSData_GetCustomsDistrictsReExports, "customsDistrictReExports"),
    ],
    ids=[
        "exports",
        "imports",
        "re_exports",
        "district_exports",
        "district_imports",
        "district_re_exports",
    ],
)
async def test_the_partner_code_is_quoted_into_the_path(
    respx_mock: respx.MockRouter,
    wrapper: Callable[[str, int, int], Awaitable[object]],
    path: str,
) -> None:
    """A slash in the partner code is sent as ``%2F``, so it stays one path segment.

    No GATS code holds a slash, and a task refuses one before any call
    (``params.validate_partner_code``); this checks the wrapper alone, so the route answers
    ``[]`` and no fixture is needed. respx matches the decoded path, which an unquoted
    slash would match too: ``sent_urls`` is what shows the quoting.
    """
    url = f"{BASE_URL}/api/gats/{path}/partnerCode/C%2FH/year/2026/month/8"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=[]))
    assert await wrapper("C/H", 2026, 8) == []
    assert sent_urls(route) == [url]


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


async def test_product_type_members_are_the_release_records_codes(
    replay_fixture: ReplayFixture,
) -> None:
    """The members are upstream's ``productType`` codes, equal to the records' own: ``X``
    throughout the exports list, ``M`` throughout the imports list."""
    replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    replay_fixture("GATSData_GetCensusImportDataReleaseInfo", "all")
    exports, _ = await api.GATSData_GetCensusExportDataReleaseInfo()
    imports, _ = await api.GATSData_GetCensusImportDataReleaseInfo()
    assert [m.value for m in ProductType] == ["X", "M"]
    assert {r.product_type for r in exports} == {ProductType.X}
    assert {r.product_type for r in imports} == {ProductType.M}
    assert ProductType("X") is ProductType.X, "a plain code is a member"


async def test_an_unknown_product_type_code_still_parses() -> None:
    """``product_type`` stays text: a code the enum does not name never fails an answer."""
    record = DataReleaseInfo.model_validate(
        {
            "statisticalYearMonth": "202608",
            "productType": "R",
            "reporterCode": "US",
            "releaseTimeStamp": "2026-10-06T08:00:00",
        }
    )
    assert record.product_type == "R"
    assert record.product_type not in {m.value for m in ProductType}


async def test_the_snapshot_has_two_release_date_operations_per_program() -> None:
    """Exports and imports have release-date operations, Census and UN Trade alike;
    re-exports have none, so ``ProductType`` has no member for them."""
    paths = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    for flow in ("exports", "imports"):
        assert f"/api/gats/census/data/{flow}/dataReleaseDates" in paths
        assert f"/api/gats/UNTrade/data/{flow}/dataReleaseDates" in paths
    release_paths = {p for p in paths if p.endswith("/dataReleaseDates")}
    assert len(release_paths) == 4
    assert not any("reexport" in p.lower() for p in release_paths)
