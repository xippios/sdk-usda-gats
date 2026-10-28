"""The packaged lists, the enum rendered from them and the argument checks of the data tasks."""

import json
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path

import pytest
from xippios.core import InvalidRequestError, PackagedList, UnknownCode, parse
from xippios.core.http import status_for
from xippios.core.testing import load_fixture

from xippios.usda.gats import enums, params
from xippios.usda.gats.errors import REPORTER_REASON, UN_PARTNER_REASON
from xippios.usda.gats.models import Country, UnitOfMeasure
from xippios.usda.gats.params import (
    PACKAGE,
    PACKAGED_LISTS,
    validate_country_code,
    validate_customs_district_id,
    validate_hs6_code,
    validate_hs6_prefix,
    validate_hs10_code,
    validate_month,
    validate_partner_code,
    validate_partner_month,
    validate_reporter_code,
    validate_year,
)

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED_COUNTRIES = datetime(2026, 10, 25, tzinfo=UTC)
FETCHED_OTHERS = datetime(2026, 10, 26, tzinfo=UTC)
"""When the packaged lists were fetched: each file's bare date, which core reads as 00:00
UTC of that day until the next refresh writes the time (ADR-0022, amendment 2026-10-27)."""


PACKAGED = [
    ("regions", "GATSData_GetRegions", "get_regions", "2026-10-26", 15),
    ("countries", "GATSData_GetCountries", "get_countries", "2026-10-25", 322),
    ("HS6Commodities", "GATSData_GetHS6Commodities", "get_hs6_commodities", "2026-10-26", 2909),
    ("unitsOfMeasure", "GATSData_GetUnitsOfMeasure", "get_units_of_measure", "2026-10-26", 108),
    ("customsDistricts", "GATSData_GetCustomsDistricts", "get_customs_districts", "2026-10-26", 53),
]


def test_five_lists_are_packaged_under_upstreams_names() -> None:
    """In the snapshot's order; the HS10 list is not packaged, ``list_commodities`` fetches
    it live."""
    assert PACKAGED_LISTS == (
        "regions",
        "countries",
        "HS6Commodities",
        "unitsOfMeasure",
        "customsDistricts",
    )
    assert [name for name, *_ in PACKAGED] == list(PACKAGED_LISTS)
    assert "commodities" not in PACKAGED_LISTS


@pytest.mark.parametrize(
    ("name", "endpoint", "wrapper", "fetched", "count"),
    PACKAGED,
    ids=[name for name, *_ in PACKAGED],
)
def test_each_packaged_list_is_its_recorded_answer_verbatim(
    name: str, endpoint: str, wrapper: str, fetched: str, count: int
) -> None:
    """Written by ``scripts/refresh_reference.py`` from the recorded answer served through
    ``respx``: the same records, field for field, in upstream's field order and record
    order; ``fetched`` is the day of the recording (UTC), read as its 00:00 UTC."""
    packaged = PackagedList.load(PACKAGE, name)
    assert (packaged.param, packaged.endpoint) == (name, endpoint)
    assert packaged.fetched == datetime.fromisoformat(f"{fetched}T00:00:00+00:00")
    fixture = load_fixture(FIXTURES / wrapper / "all.json")
    assert fixture.recorded_at.date().isoformat() == fetched
    recorded = json.loads(fixture.response.body)
    assert len(packaged.records) == count
    assert packaged.records == recorded
    assert [list(r) for r in packaged.records] == [list(r) for r in recorded], "field order"


def test_the_countries_list_is_packaged_and_parses() -> None:
    packaged = PackagedList.load(PACKAGE, "countries")
    assert (packaged.param, packaged.endpoint) == ("countries", "GATSData_GetCountries")
    assert packaged.fetched == FETCHED_COUNTRIES
    countries = parse(
        list[Country], packaged.records, source="usda-gats", endpoint="GATSData_GetCountries"
    )
    assert len(countries) == 322
    china = next(c for c in countries if c.country_code == "CH")
    assert (china.country_name, china.iso3_code, china.region_code) == ("China", "CHN", "R40")
    assert all(len(c.country_code) == 2 for c in countries)


def test_the_hs10_list_has_no_packaged_file() -> None:
    with pytest.raises(FileNotFoundError):
        PackagedList.load(PACKAGE, "commodities")  # the HS10 list is fetched live


def test_units_of_measure_render_one_int_enum() -> None:
    """``unitOfMeasureId`` to ``unitOfMeasureName``, ids 0 to 107: a member equals the id
    in upstream's data, and the name ``"Crates"`` of ids 33 and 105 gets ``_<id>``."""
    assert enums.__all__ == ["UnitOfMeasureId"]
    unit = enums.UnitOfMeasureId
    assert issubclass(unit, IntEnum)
    assert [member.value for member in unit] == list(range(108))
    assert unit.KILOGRAMS.value == 47
    assert unit(47) is unit.KILOGRAMS
    assert (unit.NONE, unit.NUMBERS, unit.METRIC_TONS) == (0, 78, 70)
    assert (unit.CRATES_33, unit.CRATES_105) == (33, 105)
    assert not hasattr(unit, "CRATES")
    assert unit._1_000_UNITS.value == 60, (
        "a name that starts with a digit gets a leading underscore"
    )
    assert unit.OZONE_DEPLETION_EQUIVALENT.value == 107
    packaged = PackagedList.load(PACKAGE, "unitsOfMeasure")
    assert {r["unitOfMeasureId"] for r in packaged.records} == {m.value for m in unit}
    kilograms = packaged.records[47]
    assert kilograms["unitOfMeasureId"] == unit.KILOGRAMS, "an IntEnum equals upstream's int"
    assert UnitOfMeasure.model_validate(kilograms).unit_of_measure_id == unit.KILOGRAMS
    assert unit.__doc__ == "Values of ``unitOfMeasureId`` (fetched 2026-10-26)."


def test_the_rendered_module_is_ascii() -> None:
    """Committed as formatted: ASCII-only, as core's ``render_enums`` writes it (ADR-0008)."""
    source = Path(enums.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    assert source.startswith(
        '"""Enums of the packaged lists, generated by scripts/refresh_reference.py; '
    )


@pytest.mark.parametrize("code", ["CH", "MX", "BV", "01", "GE"])
def test_listed_partner_codes_pass(code: str) -> None:
    """``BV`` (Bouvet Island) is listed without trade; ``GE`` was discontinued in 199009
    and still passes here: the months before it may hold its trade, and
    ``validate_partner_month`` refuses the months after it."""
    assert validate_partner_code(code) == code


def test_the_recorded_unknown_partner_is_refused_without_a_close_code() -> None:
    """``ZZ``, which GATS answers with ``[]`` (``unknown_partner.json``): no listed code is
    close by difflib's measure, so the message names two examples instead."""
    with pytest.raises(UnknownCode) as info:
        validate_partner_code("ZZ")
    error = info.value
    assert isinstance(error, InvalidRequestError)
    assert status_for(error) == 422
    assert (error.param, error.value, error.list_name, error.fetched) == (
        "partner_code",
        "ZZ",
        "countries",
        FETCHED_COUNTRIES,
    )
    assert error.closest == ()
    assert error.message.startswith(
        "'ZZ' is not a partner_code in the packaged countries list (fetched 2026-10-25)."
    )
    assert 'e.g. "CH" (China), "MX" (Mexico)' in error.message
    assert "list_countries lists every one and searches them by name, ISO or GENC code" in (
        error.message
    )
    assert "Did you mean" not in error.message
    assert "GATS answers an unknown partner code with an empty result" in error.message
    assert "/refresh-reference-data" in error.message


@pytest.mark.parametrize(
    ("value", "closest"),
    [("ch", ("CH", "China")), ("China", ("CH", "China")), ("mexico", ("MX", "Mexico"))],
)
def test_an_unknown_code_names_the_closest_known_ones(value: str, closest: tuple[str, str]) -> None:
    with pytest.raises(UnknownCode) as info:
        validate_partner_code(value)
    assert info.value.closest[0] == closest
    assert len(info.value.closest) <= 3
    assert f"Did you mean {closest[0]} ({closest[1]})" in info.value.message


@pytest.mark.parametrize(
    ("value", "closest"),
    [
        ("CHN", [("CH", "China"), ("CN", "Comoros")]),
        ("chn", [("CH", "China"), ("CN", "Comoros")]),
        ("USA", [("US", "United States"), ("SA", "Saudi Arabia"), ("RS", "Russia")]),
        ("DEU", [("GM", "Germany"), ("GE", "Germany, Federal Republic (Former)")]),
        ("CHE", [("SR", "Switzerland"), ("SZ", "Switzerland"), ("CH", "China")]),
    ],
)
def test_an_iso_or_genc_code_leads_to_its_partner_code_first(
    value: str, closest: list[tuple[str, str]]
) -> None:
    """An exact ``isO3Code`` or ``gencCode`` match comes before difflib's: ``CHN`` names
    ``CH`` (China) before ``CN`` (Comoros), which is close by its letters. ``CHE`` is the
    ISO code of two Switzerland codes; the current one, ``SR``, comes before ``SZ``,
    discontinued in 198712."""
    with pytest.raises(UnknownCode) as info:
        validate_partner_code(value)
    assert list(info.value.closest) == closest
    first, name = closest[0]
    assert f"Did you mean {first} ({name})" in info.value.message


def test_three_blanks_are_no_iso_code() -> None:
    """Three records carry ``isO3Code`` ``"   "``; three spaces lead to none of them."""
    packaged = PackagedList.load(PACKAGE, "countries")
    blank = [r["countryCode"] for r in packaged.records if r["isO3Code"] == "   "]
    assert blank == ["18", "MQ", "WQ"]
    with pytest.raises(UnknownCode) as info:
        validate_partner_code("   ")
    assert not {code for code, _ in info.value.closest} & set(blank)


@pytest.mark.parametrize("value", [1, None, ("CH",)])
def test_a_partner_code_that_is_not_text_is_refused(value: object) -> None:
    with pytest.raises(InvalidRequestError, match="partner_code must be a two-character") as info:
        validate_partner_code(value)  # type: ignore[arg-type]
    assert not isinstance(info.value, UnknownCode)
    assert "list_countries lists them" in info.value.message


def test_a_leaf_discontinued_before_the_month_is_refused() -> None:
    """``D1`` (Denmark) reads ``discontinuedOn`` ``"198712"`` and is no other code's
    parent: 2026-08 is refused, naming ``9U`` and ``DA``, the listed codes of the same
    name."""
    with pytest.raises(InvalidRequestError) as info:
        validate_partner_month("D1", 2026, 8)
    error = info.value
    assert not isinstance(error, UnknownCode), "the code is listed"
    assert status_for(error) == 422
    assert error.message == (
        "partner_code 'D1' (Denmark) was discontinued in 198712 (discontinuedOn in "
        "GATS's countries list, packaged, fetched 2026-10-25) and is no other code's parent: "
        "it holds no trade after that month, so 2026-08 (202608) is refused. Listed under "
        "the same name: 9U, DA (discontinued 198712)."
    )


def test_a_leaf_refusal_names_its_parent_code() -> None:
    """``GE`` (Germany, Federal Republic (Former)), discontinued in 199009, is a child of
    ``GM`` (Germany), which a refusal names as accepted for every month."""
    with pytest.raises(InvalidRequestError) as info:
        validate_partner_month("GE", 2026, 8)
    assert info.value.message == (
        "partner_code 'GE' (Germany, Federal Republic (Former)) was discontinued in 199009 "
        "(discontinuedOn in GATS's countries list, packaged, fetched 2026-10-25) and is no "
        "other code's parent: it holds no trade after that month, so 2026-08 (202608) is "
        "refused. Its parent code GM (Germany) is accepted for every month. No other listed "
        "code carries the name 'Germany, Federal Republic (Former)'; list_countries "
        "searches them."
    )
    assert validate_partner_month("GM", 2026, 8) == "GM"


@pytest.mark.parametrize("parent", [None, "", "QQ", "GE"], ids=["null", "empty", "unlisted", "own"])
def test_a_leaf_refusal_names_no_parent_the_list_does_not_hold(
    monkeypatch: pytest.MonkeyPatch, parent: str | None
) -> None:
    """A refreshed list may give a leaf no ``countryParentCode``, or one it does not list:
    the refusal then names no parent and never fails on the lookup."""
    countries = params._countries()
    parents = params._parent_codes()
    changed = {**countries, "GE": {**countries["GE"], "countryParentCode": parent}}
    monkeypatch.setattr(params, "_countries", lambda: changed)
    monkeypatch.setattr(params, "_parent_codes", lambda: parents)
    with pytest.raises(InvalidRequestError) as info:
        validate_partner_month("GE", 2026, 8)
    message = info.value.message
    assert "parent code" not in message
    assert "None" not in message
    assert message.endswith(
        "is refused. No other listed code carries the name "
        "'Germany, Federal Republic (Former)'; list_countries searches them."
    )


@pytest.mark.parametrize("code", ["SZ", "AS", "Y1"])
def test_a_discontinued_parent_passes_for_a_current_month(code: str) -> None:
    """``SZ`` (Switzerland, 198712), ``AS`` (Australia, 198712) and ``Y1``
    (Leeward-Windward Islands, 198801) are parents and pass for 2026-08: the rule accepts
    every parent by decision. Two were recorded: ``Y1`` as the sum of its children would
    answer (``Y1_2026_8.json``, holding every HS10 code of ``AC_2026_8.json`` at no lower
    a value), ``AS`` with the records of ``A2`` apart from the code while ``NF`` was
    empty; ``SZ`` was not."""
    assert validate_partner_month(code, 2026, 8) == code


@pytest.mark.parametrize(
    ("code", "year", "month"),
    [("D1", 1987, 12), ("D1", 1987, 6), ("D1", 1967, 1), ("CH", 2026, 8), ("SR", 1980, 1)],
)
def test_a_month_at_or_before_the_discontinuation_passes(code: str, year: int, month: int) -> None:
    """The ``discontinuedOn`` month itself passes; a current code passes for any month."""
    assert validate_partner_month(code, year, month) == code


def test_the_codes_of_the_same_name_carry_their_own_discontinuation() -> None:
    with pytest.raises(InvalidRequestError) as denmark:
        validate_partner_month("D1", 1988, 1)
    assert denmark.value.message.endswith(
        "Listed under the same name: 9U, DA (discontinued 198712)."
    )
    with pytest.raises(InvalidRequestError) as germany:
        validate_partner_month("GE", 1990, 10)
    assert "discontinued in 199009" in germany.value.message
    assert germany.value.message.endswith(
        "No other listed code carries the name 'Germany, Federal Republic (Former)'; "
        "list_countries searches them."
    )


def test_discontinuation_months_compare_as_upstream_writes_them() -> None:
    """``YS`` (Yemen (Aden)) reads ``"199091"``, no month: as six-digit text it sorts after
    every month of 1990 and before 1991's."""
    assert validate_partner_month("YS", 1990, 12) == "YS"
    with pytest.raises(InvalidRequestError, match=r"discontinued in 199091 .* 1991-01 \(199101\)"):
        validate_partner_month("YS", 1991, 1)


def test_validate_partner_month_checks_the_code_the_year_and_the_month_first() -> None:
    with pytest.raises(UnknownCode):
        validate_partner_month("ZZ", 2026, 8)
    with pytest.raises(InvalidRequestError, match="four-digit year"):
        validate_partner_month("SZ", 26, 8)
    with pytest.raises(InvalidRequestError, match="month must be a whole number"):
        validate_partner_month("SZ", 2026, 13)


def _parents_and_leaves() -> tuple[set[str], set[str]]:
    """The packaged list's parents (codes another record names as its
    ``countryParentCode``) and its leaves (discontinued codes that are nobody's parent)."""
    records = PackagedList.load(PACKAGE, "countries").records
    parents = {
        str(r["countryParentCode"]) for r in records if r["countryParentCode"] != r["countryCode"]
    }
    leaves = {str(r["countryCode"]) for r in records if r["discontinuedOn"]} - parents
    return parents, leaves


def test_the_packaged_list_has_21_parents_and_7_discontinued_leaves() -> None:
    parents, leaves = _parents_and_leaves()
    assert len(parents) == 21
    assert leaves == {"D1", "DA", "GC", "GE", "RB", "YE", "YS"}
    packaged = PackagedList.load(PACKAGE, "countries")
    ended = {str(r["countryCode"]) for r in packaged.records if r["discontinuedOn"]}
    assert len(ended) == 26
    assert len(ended & parents) == 19
    assert parents - ended == {"GM", "YM"}, "two parents are current"


def test_every_discontinued_leaf_is_refused_after_its_month_and_every_parent_passes() -> None:
    parents, leaves = _parents_and_leaves()
    packaged = PackagedList.load(PACKAGE, "countries")
    ended = [
        (str(r["countryCode"]), str(r["discontinuedOn"]))
        for r in packaged.records
        if r["discontinuedOn"]
    ]
    for code, month_code in ended:
        year, month = int(month_code[:4]), min(int(month_code[4:]), 12)
        assert validate_partner_month(code, year, month) == code, code
        if code in leaves:
            with pytest.raises(InvalidRequestError, match=f"discontinued in {month_code}"):
                validate_partner_month(code, 2026, 8)
        else:
            assert validate_partner_month(code, 2026, 8) == code, code
    for code in parents:
        assert validate_partner_month(code, 2026, 8) == code, code


@pytest.mark.parametrize("district", [0, 1, 10, 52, 99])
def test_listed_customs_districts_pass(district: int) -> None:
    assert validate_customs_district_id(district) == district


@pytest.mark.parametrize(
    ("district", "closest"),
    [
        (12, [("11", "PHILADELPHIA, PA."), ("13", "BALTIMORE, MD."), ("10", "NEW YORK, N.Y.")]),
        (
            100,
            [
                ("99", "MILITARY SHIPMENTS"),
                ("80", "MAIL SHIPMENTS"),
                ("70", "SHIPMENTS UNDER $251"),
            ],
        ),
        (-1, [("0", "Z UNKNOW CDIST CODES"), ("1", "PORTLAND,MAINE"), ("2", "ST.ALBANS, VT.")]),
    ],
)
def test_an_unknown_customs_district_names_the_nearest_ids(
    district: int, closest: list[tuple[str, str]]
) -> None:
    """``UnknownCode``'s wording serves the district list too: the parameter, the list,
    the nearest listed ids with their names, why it is refused."""
    with pytest.raises(UnknownCode) as info:
        validate_customs_district_id(district)
    error = info.value
    assert status_for(error) == 422
    assert (error.param, error.value, error.list_name, error.fetched) == (
        "customs_district_id",
        district,
        "customsDistricts",
        FETCHED_OTHERS,
    )
    assert list(error.closest) == closest
    assert error.message.startswith(
        f"{district} is not a customs_district_id in the packaged customsDistricts list "
        "(fetched 2026-10-26). Did you mean "
    )
    assert "list_customs_districts lists the ids" in error.message
    assert "partner code" not in error.message, "the partner reason is the countries list's"
    assert "/refresh-reference-data" in error.message


@pytest.mark.parametrize("district", [True, "10", 10.0, None])
def test_a_customs_district_that_is_not_an_integer_is_refused(district: object) -> None:
    with pytest.raises(InvalidRequestError, match="customs_district_id must be an integer") as info:
        validate_customs_district_id(district)  # type: ignore[arg-type]
    assert not isinstance(info.value, UnknownCode)


def test_every_recorded_partner_is_listed() -> None:
    """The partners of the recorded Census answers are in the packaged list; the probe's
    ``ZZ`` is not."""
    packaged = PackagedList.load(PACKAGE, "countries")
    codes = {record["countryCode"] for record in packaged.records}
    for endpoint, case in [
        ("get_census_exports", "CH_2026_8"),
        ("get_census_import", "CH_2026_8"),
    ]:
        records = json.loads(load_fixture(FIXTURES / endpoint / f"{case}.json").response.body)
        assert {r["countryCode"] for r in records} <= codes, case
    assert "BV" in codes
    assert "ZZ" not in codes


@pytest.mark.parametrize("year", [2026, 1967, 1000, 9999])
def test_four_digit_years_pass(year: int) -> None:
    assert validate_year(year) == year


@pytest.mark.parametrize("year", [26, 999, 10000, -2026, True, "2026", 2026.0])
def test_other_years_are_refused(year: object) -> None:
    with pytest.raises(InvalidRequestError, match="four-digit year such as 2026"):
        validate_year(year)  # type: ignore[arg-type]


@pytest.mark.parametrize("month", range(1, 13))
def test_months_1_to_12_pass(month: int) -> None:
    assert validate_month(month) == month


@pytest.mark.parametrize("month", [0, 13, -1, 100, True, "8", 8.0])
def test_other_months_are_refused(month: object) -> None:
    """Month 0 and 13 are the recorded empty 404s (``month_0.json``, ``month_13.json``)."""
    with pytest.raises(InvalidRequestError, match="month must be a whole number from 1") as info:
        validate_month(month)  # type: ignore[arg-type]
    assert "month 0 and month 13 with HTTP 404" in info.value.message


@pytest.mark.parametrize("code", ["0103910000", "0201", "02", "0", "9999999999"])
def test_hs10_codes_and_prefixes_pass(code: str) -> None:
    assert validate_hs10_code(code) == code


@pytest.mark.parametrize(
    "code",
    [
        "",
        "01039100001",
        "02.01",
        " 02",
        "02 ",
        "ab",
        "\N{FULLWIDTH DIGIT ZERO}\N{FULLWIDTH DIGIT TWO}",
        "\N{SUPERSCRIPT TWO}",
        2,
    ],
)
def test_other_hs10_filters_are_refused(code: object) -> None:
    """Too long, punctuation, spaces, letters, full-width or superscript digits, a number."""
    with pytest.raises(InvalidRequestError, match="hs10_code must be 1 to 10 digits as text"):
        validate_hs10_code(code)  # type: ignore[arg-type]


def _fixture_records(endpoint: str, case: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = json.loads(
        load_fixture(FIXTURES / endpoint / f"{case}.json").response.body
    )
    return records


UN_DATA = [
    ("get_un_trade_exports", "IC_2019"),
    ("get_un_trade_imports", "TP_2019"),
    ("get_un_trade_re_exports", "MC_2019"),
]
UN_RELEASES = [
    "get_un_trade_export_data_release_info",
    "get_un_trade_import_data_release_info",
]


@pytest.mark.parametrize("code", ["IC", "TP", "MC", "AS", "NO", "15"])
def test_listed_reporter_codes_pass(code: str) -> None:
    """``AS`` (Australia) and ``NO`` (Norway) were discontinued in 198712 and pass: the UN
    Trade check is membership only."""
    assert validate_reporter_code(code) == code


def test_an_unknown_reporter_names_the_parameter_and_its_own_reason() -> None:
    """``ZZ``, which GATS answers with ``[]`` (``unknown_reporter.json``)."""
    with pytest.raises(UnknownCode) as info:
        validate_reporter_code("ZZ")
    error = info.value
    assert status_for(error) == 422
    assert (error.param, error.value, error.list_name) == ("reporter_code", "ZZ", "countries")
    assert error.closest == ()
    assert error.message.startswith(
        "'ZZ' is not a reporter_code in the packaged countries list (fetched 2026-10-25)."
    )
    assert "GATS's country codes are its own" in error.message
    assert REPORTER_REASON in error.message
    assert "partner" not in error.message
    with pytest.raises(UnknownCode, match=r"Did you mean IC \(Iceland\)"):
        validate_reporter_code("ISL")
    with pytest.raises(InvalidRequestError, match="reporter_code must be a two-character") as text:
        validate_reporter_code(None)  # type: ignore[arg-type]
    assert not isinstance(text.value, UnknownCode)


def test_the_membership_check_names_the_parameter_it_was_given_as() -> None:
    """One check, three uses: the Census partner, the UN Trade reporter and the UN Trade
    partner filter, each refusal naming its parameter and its reason."""
    assert validate_country_code("US", "partner_code", reason=UN_PARTNER_REASON) == "US"
    with pytest.raises(UnknownCode) as info:
        validate_country_code("ZZ", "partner_code", reason=UN_PARTNER_REASON)
    assert info.value.message.startswith("'ZZ' is not a partner_code in the packaged countries")
    assert info.value.message.endswith(
        f"{UN_PARTNER_REASON} If upstream added it since, the packaged list needs a refresh "
        "(/refresh-reference-data)."
    )
    with pytest.raises(UnknownCode) as census:
        validate_partner_code("ZZ")
    assert "GATS answers an unknown partner code with an empty result" in census.value.message
    with pytest.raises(UnknownCode) as close:
        validate_country_code("AUS", "reporter_code", reason=REPORTER_REASON)
    assert close.value.closest[:2] == (("A2", "Australia"), ("AS", "Australia")), (
        "the current code first, as for every ISO code"
    )


def test_every_un_reporter_and_partner_recorded_passes_without_a_discontinuation_check() -> None:
    """Every reporter of both recorded release lists and every reporter and partner of the
    three recorded answers is a listed code; nine reporters are listed for years after
    their ``discontinuedOn``. Two of them, ``DA`` (Denmark) and ``RB`` (Serbia and
    Kosovo), are leaves, which ``validate_partner_month`` would refuse; the other seven
    are parents, which it accepts."""
    reporters = {
        str(r["reporterCode"])
        for endpoint in UN_RELEASES
        for r in _fixture_records(endpoint, "all")
    }
    codes = {
        str(r[field])
        for endpoint, case in UN_DATA
        for r in _fixture_records(endpoint, case)
        for field in ("reporterCountryCode", "partnerCountryCode")
    }
    for code in sorted(reporters | codes):
        assert validate_reporter_code(code) == code
        assert validate_country_code(code, "partner_code", reason=UN_PARTNER_REASON) == code
    assert {"AS", "NO", "DA", "IT", "NZ"} <= reporters | codes
    with pytest.raises(InvalidRequestError, match="discontinued in 198712"):
        validate_partner_month("DA", 2019, 1)
    assert validate_partner_month("AS", 2019, 1) == "AS"


@pytest.mark.parametrize("code", ["030444", "070700", "010110", "0304", "03", "0", "99999"])
def test_hs6_codes_and_prefixes_pass(code: str) -> None:
    """A full code from the packaged list, or a prefix of 1 to 5 digits, accepted as digits
    whether or not a listed code starts with it (``"99999"``)."""
    assert validate_hs6_code(code) == code


def test_every_packaged_and_every_recorded_hs6_code_passes() -> None:
    packaged = PackagedList.load(PACKAGE, "HS6Commodities")
    listed = {str(record["hS6Code"]) for record in packaged.records}
    recorded = {
        str(r["hS6Code"]) for endpoint, case in UN_DATA for r in _fixture_records(endpoint, case)
    }
    assert recorded <= listed
    for code in sorted(listed):
        assert validate_hs6_code(code) == code


@pytest.mark.parametrize(
    ("code", "closest"),
    [
        (
            "020119",
            [
                ("020110", "Bovine Carcass Fr/Ch"),
                ("020120", "Bovine Bone In Fr/Ch"),
                ("020130", "Bovine Boneless Fr/Ch"),
            ],
        ),
        (
            "030400",
            [
                ("030410", "Fish Fillets, ex. Steaks, Fr/Ch"),
                ("030411", "Swordfish Fillets, ex. Steaks, Fr/Ch"),
                ("030412", "Toothfish Fillets, ex Steaks, Fr/Ch"),
            ],
        ),
        (
            "999999",
            [
                ("981700", "Duty Free Nesoi"),
                ("981400", "Tea Duty Free"),
                ("980800", "Imports Us Gov"),
            ],
        ),
    ],
)
def test_a_full_hs6_code_the_list_lacks_names_the_codes_sharing_its_digits(
    code: str, closest: list[tuple[str, str]]
) -> None:
    """``020119`` is not listed: the codes of its heading, 0201, come first, nearest first."""
    with pytest.raises(UnknownCode) as info:
        validate_hs6_code(code)
    error = info.value
    assert status_for(error) == 422
    assert (error.param, error.value, error.list_name, error.fetched) == (
        "hs6_code",
        code,
        "HS6Commodities",
        FETCHED_OTHERS,
    )
    assert list(error.closest) == closest
    first, name = closest[0]
    assert error.message.startswith(
        f"{code!r} is not a hs6_code in the packaged HS6Commodities list (fetched "
        f"2026-10-26). Did you mean {first} ({name}), "
    )
    assert "list_hs6_commodities lists the codes" in error.message
    assert "partner" not in error.message


@pytest.mark.parametrize(
    "code",
    [
        "",
        "0304441",
        "03.04",
        " 03",
        "03 ",
        "ab",
        "\N{FULLWIDTH DIGIT ZERO}\N{FULLWIDTH DIGIT THREE}",
        "\N{SUPERSCRIPT THREE}",
        3,
        None,
    ],
)
def test_other_hs6_filters_are_refused(code: object) -> None:
    """Seven digits, punctuation, spaces, letters, full-width or superscript digits, a
    number: refused as malformed, before any list is read, by both HS6 checks."""
    for check in (validate_hs6_code, validate_hs6_prefix):
        with pytest.raises(
            InvalidRequestError, match="hs6_code must be 1 to 6 digits as text"
        ) as info:
            check(code)  # type: ignore[arg-type]
        assert not isinstance(info.value, UnknownCode)
        assert "list_hs6_commodities lists the codes" in info.value.message


@pytest.mark.parametrize("code", ["030444", "020119", "999999", "0201", "02", "0"])
def test_the_hs6_prefix_check_is_the_shape_alone(code: str) -> None:
    """``list_hs6_commodities``'s filter: 1 to 6 digits pass, a six-digit code the packaged
    list lacks (``"020119"``) included, since it selects nothing from that list; the UN
    Trade filter's check refuses that code."""
    assert validate_hs6_prefix(code) == code


def test_the_year_message_names_both_data_series() -> None:
    with pytest.raises(InvalidRequestError) as info:
        validate_year(19)
    assert info.value.message == (
        "year must be a four-digit year such as 2026, got 19. GATS's Census data starts in "
        "January 1967, its UN Trade data in 1989."
    )
    with pytest.raises(InvalidRequestError, match=r"^statistical_year must be a four-digit"):
        validate_year(19, "statistical_year")
    assert validate_year(1987, "statistical_year") == 1987
