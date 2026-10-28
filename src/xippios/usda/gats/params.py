"""Packaged GATS reference lists and the argument checks of the data tasks (conventions §3).

Five of the lists GATS publishes, regions, countries, HS6 commodities, units of measure
and customs districts, ship inside the package under ``reference/`` so that lookups and
argument checks need no network call; GATS answers an unknown partner code with an empty
list, so core's ``UnknownCode`` refuses one the list lacks (``errors``).
``scripts/refresh_reference.py`` writes the files through the ``api/`` wrappers with
``PackagedList.write``, never by hand, and regenerates ``UnitOfMeasureId`` in
``enums.py``; ``PackagedList.load(PACKAGE, name)`` reads one, and ``reference/README.md``
carries their provenance. Each file keeps upstream's records verbatim, under upstream's
field names. The HS10 list is not packaged: ``tasks.list_commodities`` fetches it live.

The checks built on them: a country code against ``countries`` (``validate_country_code``,
named by its parameter: ``validate_partner_code`` for the Census partner,
``validate_reporter_code`` for the UN Trade reporter), a Census partner against its
``discontinuedOn`` month as well (``validate_partner_month``), a customs district id
against ``customsDistricts`` (``validate_customs_district_id``) and a full HS6 code
against ``HS6Commodities`` (``validate_hs6_code``). The UN Trade tasks check membership
only: their data keeps codes the countries list marks discontinued in 1987, such as
``AS`` (Australia), for 2019. The other checks need no list: a four-digit year, a month
from 1 to 12, an HS10 code or prefix of 1 to 10 digits and an HS6 prefix of 1 to 5. All
of them run before any call.

Refresh policy: ``/refresh-reference-data`` runs inside ``/release-prep``, and whenever
a validation failure names a code the package lacks.
"""

import functools
import re
from datetime import datetime
from typing import Any

from xippios.core import InvalidRequestError, PackagedList, UnknownCode, closest

from xippios.usda.gats._client import SOURCE
from xippios.usda.gats.errors import HS6_REASON, PARTNER_REASON, REPORTER_REASON

__all__ = [
    "PACKAGE",
    "PACKAGED_LISTS",
    "validate_country_code",
    "validate_customs_district_id",
    "validate_hs6_code",
    "validate_hs10_code",
    "validate_month",
    "validate_partner_code",
    "validate_partner_month",
    "validate_reporter_code",
    "validate_year",
]

PACKAGE = "xippios.usda.gats"
"""The package whose ``reference/`` holds the lists: ``PackagedList.load(PACKAGE, name)``."""

PACKAGED_LISTS: tuple[str, ...] = (
    "regions",
    "countries",
    "HS6Commodities",
    "unitsOfMeasure",
    "customsDistricts",
)
"""Lists that ship inside the package, named as the upstream path names them, in the
snapshot's order.

Keep in step with ``ID_LISTS`` and ``TABLES`` in ``scripts/refresh_reference.py``, which
checks it before a refresh. The HS10 list (``commodities``) is not packaged:
``tasks.list_commodities`` fetches it live.
"""

PARTNER_EXAMPLES = '"CH" (China), "MX" (Mexico)'
"""Two partner codes from the packaged list, for messages that name no close code."""

_HS10 = re.compile(r"[0-9]{1,10}")
_HS6 = re.compile(r"[0-9]{1,6}")
_THREE = re.compile(r"[A-Z0-9]{3}")


@functools.cache
def _codes(name: str, code_field: str, name_field: str) -> tuple[datetime, dict[str, str]]:
    """When a packaged list was fetched and its ``{code: upstream name}``, in upstream order."""
    packaged = PackagedList.load(PACKAGE, name)
    codes = {str(record[code_field]): str(record[name_field]) for record in packaged.records}
    return packaged.fetched, codes


@functools.cache
def _countries() -> dict[str, dict[str, Any]]:
    """The packaged ``countries`` records by ``countryCode``, in upstream order."""
    packaged = PackagedList.load(PACKAGE, "countries")
    return {str(record["countryCode"]): record for record in packaged.records}


@functools.cache
def _three_letter_codes() -> dict[str, list[str]]:
    """``{isO3Code or gencCode: [countryCode, ...]}``: current codes first, then upstream order.

    ``isO3Code`` repeats (``"CHE"`` is ``SZ``, discontinued in 198712, and ``SR``, both
    Switzerland), so a three-letter code may lead to several partner codes; one without a
    ``discontinuedOn`` comes first.
    """
    by_code: dict[str, list[str]] = {}
    for code, record in _countries().items():
        for field in ("isO3Code", "gencCode"):
            three = record[field]
            if isinstance(three, str) and _THREE.fullmatch(three):
                listed = by_code.setdefault(three, [])
                if code not in listed:
                    listed.append(code)
    current = {code for code, record in _countries().items() if not record["discontinuedOn"]}
    return {
        three: sorted(codes, key=lambda code: code not in current)
        for three, codes in by_code.items()
    }


def _closest(
    value: str, codes: dict[str, str], three_letter: dict[str, list[str]] | None = None
) -> list[tuple[str, str]]:
    """Up to three known codes close to ``value``: a three-letter code, then core's ``closest``.

    GATS's ISO and GENC codes in front of core's two passes, by code and then by name
    (``xippios.core.closest``): an agent may pass ``"CHN"`` (``isO3Code`` and
    ``gencCode``) for ``"CH"``, ``"ch"`` for ``"CH"`` or ``"China"`` for ``"CH"``; each
    leads to the code. An exact three-letter match comes first, so ``"CHN"`` names ``CH``
    (China) before ``CN`` (Comoros), which difflib finds close by its letters.
    Two-character codes are close only when they differ in case, so a code that shares one
    character with a known one (``"ZZ"``) gets none. The three-letter pass is this
    package's own strategy in front of core's (ADR-0022, amendment 2026-10-27, point 3).
    """
    matches = list((three_letter or {}).get(value.upper(), []))
    matches += [code for code, _ in closest(value, codes) if code not in matches]
    return [(code, codes[code]) for code in matches[:3]]


def validate_country_code(code: str, param: str, *, reason: str = PARTNER_REASON) -> str:
    """Check a country code against the packaged ``countries`` list; messages name ``param``.

    The membership check of every code a task takes from that list: the Census
    ``partner_code`` (``validate_partner_code``), the UN Trade ``reporter_code``
    (``validate_reporter_code``) and the UN Trade ``partner_code`` filter. Every listed
    code passes, the 26 with a ``discontinuedOn`` month included; only the Census tasks
    check that month too (``validate_partner_month``).

    Args:
        code: Two characters, as ``GATSData_GetCountries`` lists them, e.g. ``"CH"``
            (China), ``"IC"`` (Iceland), ``"01"`` (Caribbean,nes), ``"AS"`` (Australia,
            discontinued 198712).
        param: The parameter the code was given as, for the messages, e.g.
            ``"partner_code"``, ``"reporter_code"``.
        reason: Why an unknown code is refused, the end of ``UnknownCode``'s message,
            e.g. ``errors.PARTNER_REASON``, ``errors.REPORTER_REASON``.

    Returns:
        The code, unchanged.

    Raises:
        InvalidRequestError: When the code is not text.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names (an ISO or GENC code such as ``"CHN"`` leads to its
            country code first, a current code before a discontinued one), or two
            examples and ``list_countries`` when none is close.
    """
    fetched, codes = _codes("countries", "countryCode", "countryName")
    if not isinstance(code, str):
        raise InvalidRequestError(
            f"{param} must be a two-character GATS country code as text, such as "
            f"{PARTNER_EXAMPLES}, got {code!r}. list_countries lists them.",
            source=SOURCE,
        )
    if code in codes:
        return code
    nearest = _closest(code, codes, _three_letter_codes())
    raise UnknownCode(
        param,
        code,
        list_name="countries",
        fetched=fetched,
        closest=nearest,
        hint=None
        if nearest
        else (
            "GATS's country codes are its own, two characters, as GATSData_GetCountries "
            f"lists them, e.g. {PARTNER_EXAMPLES}; list_countries lists every one and "
            "searches them by name, ISO or GENC code."
        ),
        reason=reason,
        source=SOURCE,
    )


def validate_partner_code(partner_code: str) -> str:
    """Check a Census partner code against the packaged ``countries`` list.

    GATS answers an unknown code with HTTP 200 and ``[]``, the same as a listed partner
    without trade (``unknown_partner.json``, ``no_data_valid_partner.json``), so the
    check runs before any upstream call. Every listed code passes here, the 26 with a
    ``discontinuedOn`` month included; ``validate_partner_month`` then refuses one for a
    month after it. ``validate_country_code`` with ``"partner_code"`` and
    ``errors.PARTNER_REASON``.

    Args:
        partner_code: Two characters, as ``GATSData_GetCountries`` lists them, e.g.
            ``"CH"`` (China), ``"MX"`` (Mexico), ``"01"`` (Caribbean,nes).

    Returns:
        The code, unchanged.

    Raises:
        InvalidRequestError: When the code is not text.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names (an ISO or GENC code such as ``"CHN"`` leads to its
            partner code first), or two examples and ``list_countries`` when none is
            close.
    """
    return validate_country_code(partner_code, "partner_code", reason=PARTNER_REASON)


def validate_reporter_code(reporter_code: str) -> str:
    """Check a UN Trade reporter code against the packaged ``countries`` list, membership only.

    GATS answers an unknown reporter with HTTP 200 and ``[]``
    (``tests/fixtures/GATSData_GetUNTradeExports/unknown_reporter.json``, ``ZZ``, 2019),
    as it answers a year without data, so the check runs before any upstream call. Every
    reporter of the recorded UN Trade release lists is a listed code. No
    ``discontinuedOn`` check: the UN Trade data keeps codes the countries list marks
    discontinued long before (``AS``, Australia, ``"198712"``, reports exports to 2016
    and imports to 2018) and never their same-name successors (``A2``), so the Census
    rule would refuse the codes the data uses. ``validate_country_code`` with
    ``"reporter_code"`` and ``errors.REPORTER_REASON``.

    Args:
        reporter_code: Two characters, as ``GATSData_GetCountries`` lists them, e.g.
            ``"IC"`` (Iceland), ``"TP"`` (Sao Tome and Principe), ``"MC"`` (Macau),
            ``"AS"`` (Australia).

    Returns:
        The code, unchanged.

    Raises:
        InvalidRequestError: When the code is not text.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names (``"ISL"`` leads to ``IC``), or two examples and
            ``list_countries`` when none is close.
    """
    return validate_country_code(reporter_code, "reporter_code", reason=REPORTER_REASON)


def validate_partner_month(partner_code: str, year: int, month: int) -> str:
    """Check a partner code, a year and a month, and that the code was current in that month.

    Runs ``validate_partner_code``, ``validate_year`` and ``validate_month``, then the
    code's ``discontinuedOn``: 26 codes of the packaged ``countries`` list carry one, a
    year and month as six digits (``SZ``, Switzerland, ``"198712"``), and GATS lists a
    successor under the same name for 11 of them (``SR``, Switzerland). The package reads
    that month as the code's last: a month at or before it passes, a later one is refused
    before any call, naming the listed codes with the same ``countryName``. Months are
    compared as six-digit text, as upstream writes them; ``YS`` (Yemen (Aden)) reads
    ``"199091"``, so every month of 1990 passes for it and 1991-01 on is refused.

    Args:
        partner_code: GATS's two-character code, e.g. ``"SZ"`` (Switzerland, discontinued
            198712), ``"CH"`` (China, current).
        year: The calendar year, four digits, e.g. ``2026``, ``1987``.
        month: The calendar month from 1 to 12, e.g. ``8``.

    Returns:
        The code, unchanged.

    Raises:
        UnknownCode: When the list lacks the code (``validate_partner_code``).
        InvalidRequestError: When the year or the month is not valid, or the month is
            after the code's ``discontinuedOn``, e.g. ``SZ`` for 2026-08.
    """
    validate_partner_code(partner_code)
    validate_year(year)
    validate_month(month)
    record = _countries()[partner_code]
    ended = record["discontinuedOn"]
    asked = f"{year:04d}{month:02d}"
    if not ended or asked <= ended:
        return partner_code
    name = record["countryName"]
    fetched, _ = _codes("countries", "countryCode", "countryName")
    same = [
        f"{code} (discontinued {other['discontinuedOn']})" if other["discontinuedOn"] else code
        for code, other in _countries().items()
        if other["countryName"] == name and code != partner_code
    ]
    instead = (
        f"Listed under the same name: {', '.join(same)}."
        if same
        else f"No other listed code carries the name {name!r}; list_countries searches them."
    )
    raise InvalidRequestError(
        f"partner_code {partner_code!r} ({name}) was discontinued in {ended} "
        f"(discontinuedOn in GATS's countries list, packaged, fetched {fetched:%Y-%m-%d}): it "
        f"holds no trade after that month, so {year:04d}-{month:02d} ({asked}) is refused. "
        f"{instead}",
        source=SOURCE,
    )


def _nearest(value: int, codes: dict[str, str]) -> list[tuple[str, str]]:
    """Up to three listed integer ids nearest to ``value``, nearest first, the lower on a tie."""
    ids = sorted((abs(int(code) - value), int(code)) for code in codes)
    return [(str(ident), codes[str(ident)]) for _, ident in ids[:3]]


def validate_customs_district_id(customs_district_id: int) -> int:
    """Check a customs district id against the packaged ``customsDistricts`` list.

    The customs-district operations take no district: a task keeps the records of one
    after the call, so an id the list lacks would select nothing. The check runs before
    any upstream call.

    Args:
        customs_district_id: An integer, as ``GATSData_GetCustomsDistricts`` lists it,
            e.g. ``10`` (NEW YORK, N.Y.), ``30`` (SEATTLE, WASH.), ``52`` (MIAMI, FLA.),
            ``0`` (Z UNKNOW CDIST CODES).

    Returns:
        The id, unchanged.

    Raises:
        InvalidRequestError: When the id is not an integer (``True`` is not ``1``).
        UnknownCode: When the list lacks the id, naming the three nearest listed ids with
            their upstream names.
    """
    if isinstance(customs_district_id, bool) or not isinstance(customs_district_id, int):
        raise InvalidRequestError(
            "customs_district_id must be an integer id such as 10 (NEW YORK, N.Y.), got "
            f"{customs_district_id!r}. list_customs_districts lists them.",
            source=SOURCE,
        )
    fetched, codes = _codes("customsDistricts", "customsDistrictId", "customsDistrictName")
    if str(customs_district_id) in codes:
        return customs_district_id
    raise UnknownCode(
        "customs_district_id",
        customs_district_id,
        list_name="customsDistricts",
        fetched=fetched,
        closest=_nearest(customs_district_id, codes),
        reason="The customs-district operations take no district; the task keeps this "
        "district's records after the call, so an id the packaged list lacks would give an "
        "empty result, and the package refuses it. list_customs_districts lists the ids.",
        source=SOURCE,
    )


def validate_year(year: int) -> int:
    """Check that a year is a four-digit integer.

    The snapshot types the Census ``year`` as ``int32`` and the UN Trade ``year`` as a
    string, and states no range for either, so none is invented beyond four digits. The
    Census release lists start at ``"196701"``
    (``tests/fixtures/GATSData_GetCensusExportDataReleaseInfo/all.json``), the UN Trade
    lists at ``"1989"`` (``.../GATSData_GetUNTradeExportDataReleaseInfo/all.json``); a
    task checks the month, or the reporter-year, against its list after this.

    Args:
        year: The calendar or statistical year, e.g. ``2026``, ``1967``, ``2019``.

    Returns:
        The year, unchanged.

    Raises:
        InvalidRequestError: When the year is not an integer from 1000 to 9999 (``True``
            is not ``1``).
    """
    if isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999:
        raise InvalidRequestError(
            f"year must be a four-digit year such as 2026, got {year!r}. GATS's Census "
            "data starts in January 1967, its UN Trade data in 1989.",
            source=SOURCE,
        )
    return year


def validate_month(month: int) -> int:
    """Check that a month is an integer from 1 to 12.

    GATS answers month 0 and month 13 with HTTP 404 and an empty body
    (``tests/fixtures/GATSData_GetCensusExports/month_0.json`` and ``month_13.json``,
    recorded for China in 2026); month 0 is no whole-year form. The check refuses them,
    and every other month outside 1 to 12, before any call.

    Args:
        month: The calendar month, e.g. ``8`` (August), ``1`` (January).

    Returns:
        The month, unchanged.

    Raises:
        InvalidRequestError: When the month is not an integer from 1 to 12 (``True`` is
            not ``1``).
    """
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise InvalidRequestError(
            f"month must be a whole number from 1 (January) to 12 (December), got "
            f"{month!r}. GATS answers month 0 and month 13 with HTTP 404 and an empty body; "
            "it has no whole-year form of the Census data: ask month by month.",
            source=SOURCE,
        )
    return month


def validate_hs10_code(hs10_code: str) -> str:
    """Check that an HS10 filter is 1 to 10 ASCII digits as text: a full code or a prefix.

    The Census records carry ``hS10Code`` as ten digits as text (``"0103910000"``); the
    filter keeps the records whose code starts with it, so a shorter one is a prefix,
    e.g. the chapter ``"02"``. Digits only: a dot or a space would match nothing.

    Args:
        hs10_code: E.g. ``"0103910000"`` (one product), ``"0201"`` (an HS heading),
            ``"02"`` (chapter 02).

    Returns:
        The filter, unchanged.

    Raises:
        InvalidRequestError: When it is not text of 1 to 10 digits from 0 to 9.
    """
    if not isinstance(hs10_code, str) or _HS10.fullmatch(hs10_code) is None:
        raise InvalidRequestError(
            "hs10_code must be 1 to 10 digits as text: a full HS10 code such as "
            f'"0103910000" or a prefix such as "02" (chapter 02), got {hs10_code!r}.',
            source=SOURCE,
        )
    return hs10_code


def _sharing_digits(value: str, codes: dict[str, str]) -> list[tuple[str, str]]:
    """Up to three listed codes sharing the most leading digits with ``value``, nearest first.

    HS codes nest by their leading digits, chapter, heading and subheading, so a listed
    code of the same heading is closer than one that matches more digits elsewhere:
    ``"020119"`` names ``020110``, ``020120`` and ``020130``, the codes of heading 0201.
    Within the same shared length the numerically nearest come first, the lower on a tie.
    """
    target = int(value)

    def shared(code: str) -> int:
        return next((i for i, (a, b) in enumerate(zip(value, code, strict=False)) if a != b), 6)

    ranked = sorted(codes, key=lambda code: (-shared(code), abs(int(code) - target), code))
    return [(code, codes[code]) for code in ranked[:3]]


def validate_hs6_code(hs6_code: str) -> str:
    """Check an HS6 filter: 1 to 6 ASCII digits as text, a full code only if it is packaged.

    The UN Trade records carry ``hS6Code`` as six digits as text (``"070700"``), every
    recorded one a code of the packaged ``HS6Commodities`` list. The filter keeps the
    records whose code starts with it: a shorter one is a prefix, e.g. the chapter
    ``"03"`` or the heading ``"0304"``, accepted as digits; a full six-digit code must be
    in the packaged list, since one it lacks would select nothing. Digits only: a dot or
    a space would match nothing.

    Args:
        hs6_code: E.g. ``"030444"`` (Codlet Fillets Frh/Ch, one product), ``"0304"`` (an
            HS heading), ``"03"`` (chapter 03).

    Returns:
        The filter, unchanged.

    Raises:
        InvalidRequestError: When it is not text of 1 to 6 digits from 0 to 9.
        UnknownCode: When it is a six-digit code the packaged list lacks, naming up to
            three listed codes that share the most leading digits with it, with their
            upstream names.
    """
    if not isinstance(hs6_code, str) or _HS6.fullmatch(hs6_code) is None:
        raise InvalidRequestError(
            "hs6_code must be 1 to 6 digits as text: a full HS6 code such as "
            f'"030444" or a prefix such as "03" (chapter 03), got {hs6_code!r}. '
            "list_hs6_commodities lists the codes.",
            source=SOURCE,
        )
    if len(hs6_code) < 6:
        return hs6_code
    fetched, codes = _codes("HS6Commodities", "hS6Code", "commodityName")
    if hs6_code in codes:
        return hs6_code
    raise UnknownCode(
        "hs6_code",
        hs6_code,
        list_name="HS6Commodities",
        fetched=fetched,
        closest=_sharing_digits(hs6_code, codes),
        reason=HS6_REASON,
        source=SOURCE,
    )
