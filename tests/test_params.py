"""The packaged countries list and the argument checks of the Census tasks."""

import json
from pathlib import Path

import pytest
from xippios.core import InvalidRequestError, parse
from xippios.core.http import status_for
from xippios.core.testing import load_fixture

from xippios.usda.gats import enums
from xippios.usda.gats.errors import UnknownCode
from xippios.usda.gats.models import Country
from xippios.usda.gats.params import (
    PACKAGED_LISTS,
    packaged_values,
    validate_hs10_code,
    validate_month,
    validate_partner_code,
    validate_year,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_the_countries_list_is_packaged_and_parses() -> None:
    assert PACKAGED_LISTS == ("countries",)
    packaged = packaged_values("countries")
    assert packaged is not None
    assert (packaged.param, packaged.endpoint) == ("countries", "GATSData_GetCountries")
    assert packaged.fetched.isoformat() == "2026-10-25"
    countries = parse(
        list[Country], packaged.records, source="usda-gats", endpoint="GATSData_GetCountries"
    )
    assert len(countries) == 322
    china = next(c for c in countries if c.country_code == "CH")
    assert (china.country_name, china.iso3_code, china.region_code) == ("China", "CHN", "R40")
    assert all(len(c.country_code) == 2 for c in countries)


def test_the_packaged_list_is_the_recorded_answer_verbatim() -> None:
    packaged = packaged_values("countries")
    assert packaged is not None
    fixture = FIXTURES / "GATSData_GetCountries" / "all.json"
    recorded = json.loads(load_fixture(fixture).response.body)
    assert packaged.records == recorded
    assert [list(r) for r in packaged.records] == [list(r) for r in recorded], "field order"


def test_an_unknown_list_is_none() -> None:
    assert packaged_values("regions") is None, "not packaged yet"
    assert packaged_values("not_a_list") is None


def test_the_countries_table_renders_no_enum() -> None:
    assert enums.__all__ == []


@pytest.mark.parametrize("code", ["CH", "MX", "BV", "01", "GE"])
def test_listed_partner_codes_pass(code: str) -> None:
    """``BV`` (Bouvet Island) is listed without trade; ``GE`` was discontinued in 199009
    and still passes: the months before it may hold its trade."""
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
        "2026-10-25",
    )
    assert error.closest == []
    assert error.message.startswith(
        "'ZZ' is not a partner_code in GATS's countries list (packaged, fetched 2026-10-25)."
    )
    assert 'e.g. "CH" (China), "MX" (Mexico)' in error.message
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


@pytest.mark.parametrize("value", [1, None, ("CH",)])
def test_a_partner_code_that_is_not_text_is_refused(value: object) -> None:
    with pytest.raises(InvalidRequestError, match="partner_code must be a two-character") as info:
        validate_partner_code(value)  # type: ignore[arg-type]
    assert not isinstance(info.value, UnknownCode)


def test_every_recorded_partner_is_listed() -> None:
    """The partners of the recorded Census answers are in the packaged list; the probe's
    ``ZZ`` is not."""
    packaged = packaged_values("countries")
    assert packaged is not None
    codes = {record["countryCode"] for record in packaged.records}
    for endpoint, case in [
        ("GATSData_GetCensusExports", "CH_2026_8"),
        ("GATSData_GetCensusImport", "CH_2026_8"),
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
