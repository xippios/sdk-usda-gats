"""Replay tests for the endpoint wrappers (layer 1), against recorded answers.

What was sent is compared through ``sent_urls(route)``, the URLs with credentials redacted,
never a request kept from ``route.calls``.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import NotFoundError, UpstreamModel
from xippios.core.testing import ReplayFixture, load_fixture, sent_urls

from xippios.usda.gats import api
from xippios.usda.gats._client import BASE_URL, classify
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

pytestmark = pytest.mark.anyio

SNAPSHOT = Path(__file__).parents[1] / "docs" / "upstream" / "openapi" / "portal-document.json"
EXPORTS = "GATSData_GetCensusExports"
RE_EXPORTS = "GATSData_GetCensusReExports"
DISTRICT_EXPORTS = "GATSData_GetCustomsDistrictsExports"
DISTRICT_IMPORTS = "GATSData_GetCustomsDistrictsImports"
DISTRICT_RE_EXPORTS = "GATSData_GetCustomsDistrictsReExports"
UN_EXPORTS = "GATSData_GetUNTradeExports"
UN_IMPORTS = "GATSData_GetUNTradeImports"
UN_RE_EXPORTS = "GATSData_GetUNTradeReExports"
UN_EXPORT_RELEASES = "GATSData_GetUNTradeExportDataReleaseInfo"
UN_IMPORT_RELEASES = "GATSData_GetUNTradeImportDataReleaseInfo"


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


async def test_get_countries(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCountries", "all")
    countries = await api.get_countries()
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
    country = (await api.get_countries())[0]
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
    regions = await api.get_regions()
    assert len(regions) == 15
    assert regions[0] == Region(region_code="R05", region_name="North America")
    by_code = {r.region_code: r.region_name for r in regions}
    assert len(by_code) == 15, "no code twice"
    assert [r.region_code for r in regions] == sorted(by_code), "in code order"
    assert by_code["R40"] == "East Asia"
    countries = await api.get_countries()
    assert {c.region_code for c in countries} <= set(by_code), "every country's region"
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/regions"]


async def test_get_commodities(replay_fixture: ReplayFixture) -> None:
    """The HS10 list whole: 24,936 records, 8,383,278 bytes as a fixture file, the largest
    in the family. Product types ``T`` and ``B`` carry seven digits padded with three
    spaces, kept as sent; code, product type and start month are unique together."""
    route = replay_fixture("GATSData_GetCommodities", "all")
    records, retrieved_at = await api.get_commodities()
    assert route.call_count == 1, "from the wire, not from the cache"
    assert retrieved_at.tzinfo is UTC
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
    records = await api.get_hs6_commodities()
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
    records = await api.get_units_of_measure()
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
    records = await api.get_customs_districts()
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
    releases, retrieved_at = await api.get_census_export_data_release_info()
    assert route.call_count == 1, "from the wire, not from the cache"
    assert retrieved_at.tzinfo is UTC
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
    imports, _ = await api.get_census_import_data_release_info()
    exports, _ = await api.get_census_export_data_release_info()
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
    records = await api.get_census_exports("CH", 2026, 8)
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
    records = await api.get_census_import("CH", 2026, 8)
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
    records = await api.get_census_re_exports("IC", 2026, 8)
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
    records = await api.get_customs_districts_exports("IC", 2026, 8)
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
            api.get_customs_districts_exports,
            DISTRICT_EXPORTS,
            api.get_census_exports,
            EXPORTS,
            "CH",
            1697,
        ),
        (
            api.get_customs_districts_re_exports,
            DISTRICT_RE_EXPORTS,
            api.get_census_re_exports,
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
    records = await api.get_customs_districts_exports("CH", 2026, 8)
    assert len(records) == 1697
    assert len({r.customs_district_id for r in records}) == 31
    assert len({r.hs10_code for r in records}) == 777, "the codes of the Census exports"
    assert sum(r.value for r in records) == Decimal("781424244.0")
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/customsDistrictExports/partnerCode/CH/year/2026/month/8"
    ]


async def test_get_customs_districts_imports(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture(DISTRICT_IMPORTS, "IC_2026_8")
    records = await api.get_customs_districts_imports("IC", 2026, 8)
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
    records = await api.get_customs_districts_re_exports("IC", 2026, 8)
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
    unit_ids = {u.unit_of_measure_id for u in await api.get_units_of_measure()}
    district_ids = {d.customs_district_id for d in await api.get_customs_districts()}
    hs6_codes = {c.hs6_code for c in await api.get_hs6_commodities()}
    census: list[CensusExport | CensusImport] = [
        *await api.get_census_exports("CH", 2026, 8),
        *await api.get_census_import("CH", 2026, 8),
        *await api.get_census_re_exports("IC", 2026, 8),
    ]
    districts: list[CustomsDistrictExport | CustomsDistrictImport] = [
        *await api.get_customs_districts_exports("IC", 2026, 8),
        *await api.get_customs_districts_imports("IC", 2026, 8),
        *await api.get_customs_districts_re_exports("IC", 2026, 8),
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
        (api.get_census_exports, "censusExports"),
        (api.get_census_import, "censusImports"),
        (api.get_census_re_exports, "censusReExports"),
        (api.get_customs_districts_exports, "customsDistrictExports"),
        (api.get_customs_districts_imports, "customsDistrictImports"),
        (api.get_customs_districts_re_exports, "customsDistrictReExports"),
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
    assert await api.get_census_exports(partner_code, year, month) == []
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
        await api.get_census_exports("CH", 2026, month)
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
    exports, _ = await api.get_census_export_data_release_info()
    imports, _ = await api.get_census_import_data_release_info()
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


async def test_get_un_trade_export_release_dates(replay_fixture: ReplayFixture) -> None:
    """One record per reporter and statistical year, 1989 to 2019, the newest released
    on 2021-01-18: 3,796 records, 464,555 bytes as a fixture file."""
    route = replay_fixture(UN_EXPORT_RELEASES, "all")
    releases, retrieved_at = await api.get_un_trade_export_data_release_info()
    assert route.call_count == 1, "from the wire, not from the cache"
    assert retrieved_at.tzinfo is UTC
    assert len(releases) == 3796
    assert releases[0] == UNTradeDataReleaseInfo(
        statistical_year="2019",
        product_type="X",
        reporter_code="AC",
        release_time_stamp=datetime(2020, 10, 11, 1, 15, 48),
    )
    assert releases[0].release_time_stamp.tzinfo is None, "upstream sends no time zone"
    assert releases[-1].statistical_year == "1989"
    order = [(-int(r.statistical_year), r.reporter_code) for r in releases]
    assert order == sorted(order), "newest year first, reporters in code order"
    pairs = {(r.reporter_code, r.statistical_year) for r in releases}
    assert len(pairs) == 3796, "one record per reporter and year"
    assert {r.statistical_year for r in releases} == {str(y) for y in range(1989, 2020)}
    assert {r.product_type for r in releases} == {"X"}
    assert len({r.reporter_code for r in releases}) == 206
    assert max(r.release_time_stamp for r in releases) == datetime(2021, 1, 18, 1, 25, 58)
    assert sum(r.statistical_year == "2019" for r in releases) == 32
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/UNTrade/data/exports/dataReleaseDates"]


async def test_get_un_trade_import_release_dates(replay_fixture: ReplayFixture) -> None:
    """The imports list answers the same record; its reporter-years are not the exports
    list's: 32 pairs are only in the exports list, 68 only in this one."""
    route = replay_fixture(UN_IMPORT_RELEASES, "all")
    replay_fixture(UN_EXPORT_RELEASES, "all")
    imports, _ = await api.get_un_trade_import_data_release_info()
    exports, _ = await api.get_un_trade_export_data_release_info()
    assert route.call_count == 1
    assert len(imports) == 3832
    assert imports[0] == UNTradeDataReleaseInfo(
        statistical_year="2019",
        product_type="M",
        reporter_code="AC",
        release_time_stamp=datetime(2020, 10, 11, 1, 15, 44),
    )
    assert {r.product_type for r in imports} == {"M"}
    assert len({r.reporter_code for r in imports}) == 207
    assert max(r.release_time_stamp for r in imports) == datetime(2021, 1, 18, 1, 27, 44)
    in_imports = {(r.reporter_code, r.statistical_year) for r in imports}
    in_exports = {(r.reporter_code, r.statistical_year) for r in exports}
    assert len(in_imports) == 3832, "one record per reporter and year"
    assert (len(in_exports - in_imports), len(in_imports - in_exports)) == (32, 68)
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/UNTrade/data/imports/dataReleaseDates"]


async def test_each_recorded_reporter_year_has_its_flows_release_record(
    replay_fixture: ReplayFixture,
) -> None:
    """A reporter-year's release record is the one with its reporter code and year in
    its flow's list: Iceland, Sao Tome and Principe and Macau have one for 2019 in both
    lists, India's latest is 2016, and no reporter has one after 2019."""
    replay_fixture(UN_EXPORT_RELEASES, "all")
    replay_fixture(UN_IMPORT_RELEASES, "all")
    exports, _ = await api.get_un_trade_export_data_release_info()
    imports, _ = await api.get_un_trade_import_data_release_info()
    x = {(r.reporter_code, r.statistical_year): r.release_time_stamp for r in exports}
    m = {(r.reporter_code, r.statistical_year): r.release_time_stamp for r in imports}
    assert x[("IC", "2019")] == datetime(2020, 6, 3, 5, 50, 46)
    assert m[("IC", "2019")] == datetime(2020, 6, 5, 1, 22, 30)
    assert m[("TP", "2019")] == datetime(2020, 7, 16, 1, 15, 37)
    assert ("MC", "2019") in x
    assert ("MC", "2019") in m
    for listed in (x, m):
        assert max(year for code, year in listed if code == "IN") == "2016"
        assert ("IC", "2020") not in listed, "the unreleased_year probe's reporter-year"
        assert max(year for _, year in listed) == "2019"


async def test_the_un_release_lists_name_reporters_by_gats_country_code(
    replay_fixture: ReplayFixture,
) -> None:
    """Every reporter is a code of the countries list, GATS's own vocabulary. Nine codes
    the list marks discontinued are listed for years after their ``discontinuedOn``
    (Norway's ``NO``, discontinued 198712, has 2018), and their same-name successors
    (``N3``) never: the codes are not the countries list's current ones."""
    replay_fixture("GATSData_GetCountries", "all")
    replay_fixture(UN_EXPORT_RELEASES, "all")
    replay_fixture(UN_IMPORT_RELEASES, "all")
    countries = {c.country_code: c for c in await api.get_countries()}
    exports, _ = await api.get_un_trade_export_data_release_info()
    imports, _ = await api.get_un_trade_import_data_release_info()
    releases = [*exports, *imports]
    reporters = {r.reporter_code for r in releases}
    assert reporters <= set(countries)
    discontinued = {code for code in reporters if countries[code].discontinued_on}
    assert discontinued == {"AS", "BE", "DA", "GE", "IS", "IT", "NO", "NT", "NZ", "RB", "SU"}
    after = {
        r.reporter_code
        for r in releases
        if r.reporter_code in discontinued
        and r.statistical_year > str(countries[r.reporter_code].discontinued_on)[:4]
    }
    assert after == discontinued - {"GE", "SU"}
    assert countries["NO"].discontinued_on == "198712"
    assert ("NO", "2018") in {(r.reporter_code, r.statistical_year) for r in exports}
    assert not {"A2", "D1", "9U", "I1", "I2", "N1", "N3"} & reporters, "no successor"


async def test_get_un_trade_exports(replay_fixture: ReplayFixture) -> None:
    """One reporter-year across all partners and HS6 codes, whole: 3,980 records,
    1,005,809 bytes as a fixture file, for Iceland in 2019."""
    route = replay_fixture(UN_EXPORTS, "IC_2019")
    records = await api.get_un_trade_exports("IC", "2019")
    assert len(records) == 3980
    assert records[0] == UNTradeRecord(
        year="2019",
        reporter_country_code="IC",
        partner_country_code="15",
        hs6_code="070700",
        census_uom_id1=0,
        census_uom_id2=0,
        fas_converted_uom_id=47,
        fas_non_converted_uom_id=47,
        quantity1=Decimal("29051.0"),
        quantity2=Decimal("29051.0"),
        value=Decimal("73524.0"),
    )
    assert {(r.year, r.reporter_country_code) for r in records} == {("2019", "IC")}
    pairs = [(r.partner_country_code, r.hs6_code) for r in records]
    assert pairs == sorted(set(pairs)), "one record per partner and HS6 code, in that order"
    assert len({r.partner_country_code for r in records}) == 115
    assert len({r.hs6_code for r in records}) == 646
    assert all(len(r.hs6_code) == 6 and r.hs6_code.isdigit() for r in records)
    assert {(r.census_uom_id1, r.census_uom_id2, r.fas_converted_uom_id) for r in records} == {
        (0, 0, 47)
    }
    assert Decimal("582.3") in {r.quantity1 for r in records}, "fractions occur"
    assert sum(r.value for r in records) == Decimal("2582465259.0")
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/UNTradeExports/reporterCode/IC/year/2019"]


async def test_get_un_trade_imports(replay_fixture: ReplayFixture) -> None:
    """Sao Tome and Principe in 2019: 2,377 records, 597,815 bytes as a fixture file.
    Iceland's 2019 imports, 23,396 records and 5,180,537 bytes of JSON, are not kept."""
    route = replay_fixture(UN_IMPORTS, "TP_2019")
    records = await api.get_un_trade_imports("TP", "2019")
    assert len(records) == 2377
    assert records[0] == UNTradeRecord(
        year="2019",
        reporter_country_code="TP",
        partner_country_code="15",
        hs6_code="100630",
        census_uom_id1=0,
        census_uom_id2=0,
        fas_converted_uom_id=47,
        fas_non_converted_uom_id=47,
        quantity1=Decimal("15.0"),
        quantity2=Decimal("15.0"),
        value=Decimal("31.0"),
    )
    assert {(r.year, r.reporter_country_code) for r in records} == {("2019", "TP")}
    pairs = [(r.partner_country_code, r.hs6_code) for r in records]
    assert pairs == sorted(set(pairs)), "one record per partner and HS6 code, in that order"
    assert len({r.partner_country_code for r in records}) == 58
    assert len({r.hs6_code for r in records}) == 1026
    assert sum(r.value for r in records) == Decimal("56394979.0")
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/UNTradeImports/reporterCode/TP/year/2019"]


async def test_get_un_trade_re_exports(replay_fixture: ReplayFixture) -> None:
    """Macau in 2019: 421 records, 106,083 bytes as a fixture file, every quantity 0."""
    route = replay_fixture(UN_RE_EXPORTS, "MC_2019")
    records = await api.get_un_trade_re_exports("MC", "2019")
    assert len(records) == 421
    assert records[0] == UNTradeRecord(
        year="2019",
        reporter_country_code="MC",
        partner_country_code="AS",
        hs6_code="220421",
        census_uom_id1=0,
        census_uom_id2=0,
        fas_converted_uom_id=47,
        fas_non_converted_uom_id=95,
        quantity1=Decimal("0.0"),
        quantity2=Decimal("0.0"),
        value=Decimal("114863.0"),
    )
    assert {(r.year, r.reporter_country_code) for r in records} == {("2019", "MC")}
    assert len({(r.partner_country_code, r.hs6_code) for r in records}) == 421
    assert {(r.quantity1, r.quantity2) for r in records} == {(Decimal("0.0"), Decimal("0.0"))}
    assert sum(r.value for r in records) == Decimal("134297794.0")
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/UNTradeReExports/reporterCode/MC/year/2019"]


async def test_iceland_has_no_un_re_exports_for_2019(replay_fixture: ReplayFixture) -> None:
    """As recorded: a reporter with 2019 exports and imports answers HTTP 200 with ``[]``
    for its 2019 re-exports; re-exports have no release list to tell."""
    route = replay_fixture(UN_RE_EXPORTS, "IC_2019")
    assert await api.get_un_trade_re_exports("IC", "2019") == []
    assert sent_urls(route) == [f"{BASE_URL}/api/gats/UNTradeReExports/reporterCode/IC/year/2019"]


async def test_the_un_trade_answers_carry_one_shape(fixtures_dir: Path) -> None:
    """Why one model serves all three: exports, imports and re-exports answer the same
    eleven fields in the same order."""
    shape = aliases(UNTradeRecord)
    assert len(shape) == 11
    for endpoint, case in [
        (UN_EXPORTS, "IC_2019"),
        (UN_IMPORTS, "TP_2019"),
        (UN_RE_EXPORTS, "MC_2019"),
    ]:
        assert recorded_keys(fixtures_dir, endpoint, case) == {shape}, endpoint
    for endpoint in (UN_EXPORT_RELEASES, UN_IMPORT_RELEASES):
        assert recorded_keys(fixtures_dir, endpoint, "all") == {aliases(UNTradeDataReleaseInfo)}
    assert aliases(UNTradeDataReleaseInfo)[0] == "statisticalYear"
    assert aliases(DataReleaseInfo)[0] == "statisticalYearMonth", "not the Census record"


async def test_the_lists_name_every_code_and_unit_the_un_answers_carry(
    replay_fixture: ReplayFixture,
) -> None:
    """GATS's vocabulary, not UN Comtrade's: every reporter and partner is a code of the
    countries list, every HS6 code one of the HS6 list and every unit id one of the units
    list. Partners include codes the countries list marks discontinued (``NO``, Norway,
    198712) and never their same-name successors."""
    replay_fixture("GATSData_GetCountries", "all")
    replay_fixture("GATSData_GetHS6Commodities", "all")
    replay_fixture("GATSData_GetUnitsOfMeasure", "all")
    replay_fixture(UN_EXPORTS, "IC_2019")
    replay_fixture(UN_IMPORTS, "TP_2019")
    replay_fixture(UN_RE_EXPORTS, "MC_2019")
    countries = {c.country_code: c for c in await api.get_countries()}
    hs6_codes = {c.hs6_code for c in await api.get_hs6_commodities()}
    unit_ids = {u.unit_of_measure_id for u in await api.get_units_of_measure()}
    exports = await api.get_un_trade_exports("IC", "2019")
    records = [
        *exports,
        *await api.get_un_trade_imports("TP", "2019"),
        *await api.get_un_trade_re_exports("MC", "2019"),
    ]
    codes = {r.reporter_country_code for r in records} | {r.partner_country_code for r in records}
    assert codes <= set(countries)
    assert {r.hs6_code for r in records} <= hs6_codes
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
    partners = {r.partner_country_code for r in exports}
    discontinued = {code for code in partners if countries[code].discontinued_on}
    assert discontinued == {"AS", "DA", "IS", "IT", "NO", "NZ", "RB"}
    assert countries["NO"].discontinued_on == "198712"
    assert not {"A2", "D1", "9U", "I1", "I2", "N1", "N3"} & codes, "no successor"
    assert "611011" in {r.hs6_code for r in exports}, "beyond HS chapters 01 to 24"


@pytest.mark.parametrize(
    ("wrapper", "path"),
    [
        (api.get_un_trade_exports, "UNTradeExports"),
        (api.get_un_trade_imports, "UNTradeImports"),
        (api.get_un_trade_re_exports, "UNTradeReExports"),
    ],
    ids=["exports", "imports", "re_exports"],
)
async def test_the_reporter_code_and_year_are_quoted_into_the_path(
    respx_mock: respx.MockRouter,
    wrapper: Callable[[str, str], Awaitable[object]],
    path: str,
) -> None:
    """A slash in the reporter code or in the year, both text, is sent as ``%2F``, so each
    stays one path segment; the route answers ``[]`` and no fixture is needed. respx
    matches the decoded path: ``sent_urls`` is what shows the quoting."""
    url = f"{BASE_URL}/api/gats/{path}/reporterCode/I%2FC/year/20%2F19"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=[]))
    assert await wrapper("I/C", "20/19") == []
    assert sent_urls(route) == [url]


@pytest.mark.parametrize(
    ("case", "reporter_code", "year"),
    [
        ("unknown_reporter", "ZZ", "2019"),
        ("future_year", "IC", "2035"),
        ("unreleased_year", "IC", "2020"),
    ],
)
async def test_unknown_reporter_future_and_unreleased_years_answer_an_empty_list(
    replay_fixture: ReplayFixture, case: str, reporter_code: str, year: str
) -> None:
    """As recorded: a code the countries list lacks (``ZZ``), a year far ahead and the
    year after the release lists' latest (Iceland, 2020, no release record) answer alike,
    HTTP 200 with ``[]``, as Iceland's 2019 re-exports do; nothing in the answer tells them
    apart."""
    route = replay_fixture(UN_EXPORTS, case)
    assert await api.get_un_trade_exports(reporter_code, year) == []
    assert sent_urls(route) == [
        f"{BASE_URL}/api/gats/UNTradeExports/reporterCode/{reporter_code}/year/{year}"
    ]


async def test_a_year_that_is_not_a_number_is_an_empty_404_and_a_not_found_error(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    """As recorded: the snapshot types ``year`` as a string, yet ``abc`` answers HTTP 404
    with an empty ``text/plain`` body, like the Census data's month 13. ``classify``
    leaves it to core's status mapping, a ``NotFoundError`` naming the method and path."""
    raw = json.loads((fixtures_dir / UN_EXPORTS / "year_text.json").read_text(encoding="utf-8"))
    headers = dict(raw["response"]["headers"])
    assert (raw["response"]["status"], raw["response"]["body"]) == (404, "")
    assert headers["content-type"] == "text/plain; charset=utf-8"
    route = replay_fixture(UN_EXPORTS, "year_text")
    path = "/api/gats/UNTradeExports/reporterCode/IC/year/abc"
    with pytest.raises(NotFoundError) as info:
        await api.get_un_trade_exports("IC", "abc")
    assert info.value.message == f"404 from GET {path}: Not Found"
    assert "api.fas.usda.gov" not in info.value.message, "host-free (conventions §5)"
    assert route.call_count == 1, "a 404 is never retried"
    assert sent_urls(route) == [f"{BASE_URL}{path}"]


async def test_classify_leaves_every_un_probe_to_core(fixtures_dir: Path) -> None:
    """No GATS-specific mapping for the UN Trade answers either."""
    for case in ("unknown_reporter", "future_year", "unreleased_year", "year_text"):
        fixture = load_fixture(fixtures_dir / UN_EXPORTS / f"{case}.json")
        response = httpx.Response(
            fixture.response.status,
            headers=fixture.response.headers,
            content=fixture.response.content,
            request=httpx.Request(fixture.request.method, fixture.request.url),
        )
        assert classify(response) is None, case


async def test_the_un_release_lists_carry_the_product_type_codes_too(
    replay_fixture: ReplayFixture,
) -> None:
    """The UN Trade lists use the Census lists' ``productType`` codes: ``X`` throughout
    the exports list, ``M`` throughout the imports list."""
    replay_fixture(UN_EXPORT_RELEASES, "all")
    replay_fixture(UN_IMPORT_RELEASES, "all")
    exports, _ = await api.get_un_trade_export_data_release_info()
    imports, _ = await api.get_un_trade_import_data_release_info()
    assert {r.product_type for r in exports} == {ProductType.X}
    assert {r.product_type for r in imports} == {ProductType.M}


async def test_an_unknown_un_product_type_code_still_parses() -> None:
    """``UNTradeDataReleaseInfo.product_type`` stays text, as the Census record's does."""
    record = UNTradeDataReleaseInfo.model_validate(
        {
            "statisticalYear": "2019",
            "productType": "R",
            "reporterCode": "IC",
            "releaseTimeStamp": "2020-06-03T05:50:46",
        }
    )
    assert record.product_type == "R"
    assert record.release_time_stamp == datetime(2020, 6, 3, 5, 50, 46)
