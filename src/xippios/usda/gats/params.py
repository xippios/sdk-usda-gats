"""Packaged GATS reference lists and the argument checks of the Census tasks (conventions §3).

Five of the lists GATS publishes, regions, countries, HS6 commodities, units of measure
and customs districts, ship inside the package under ``reference/`` so that lookups and
argument checks need no network call; GATS answers an unknown partner code with an empty
list (``errors.UnknownCode``). ``scripts/refresh_reference.py`` writes the files through
the ``api/`` wrappers, never by hand, and regenerates ``UnitOfMeasureId`` in
``enums.py``; ``reference/README.md`` carries their provenance. Each file keeps
upstream's records verbatim, under upstream's field names. The HS10 list is not
packaged: ``tasks.list_commodities`` fetches it live.

The checks built on them: a partner code against ``countries`` (``validate_partner_code``)
and against its ``discontinuedOn`` month (``validate_partner_month``), and a customs
district id against ``customsDistricts`` (``validate_customs_district_id``). The other
checks need no list: a four-digit year, a month from 1 to 12 and an HS10 code or prefix
of 1 to 10 digits. All of them run before any call.

Refresh policy: ``/refresh-reference-data`` runs inside ``/release-prep``, and whenever
a validation failure names a code the package lacks.
"""

import difflib
import functools
import re
from datetime import date
from typing import Any

from xippios.core import InvalidRequestError, UpstreamModel, load_json

from xippios.usda.gats._client import SOURCE
from xippios.usda.gats.errors import PARTNER_REASON, UnknownCode

__all__ = [
    "PACKAGED_LISTS",
    "PackagedList",
    "packaged_values",
    "validate_customs_district_id",
    "validate_hs10_code",
    "validate_month",
    "validate_partner_code",
    "validate_partner_month",
    "validate_year",
]

PACKAGE = "xippios.usda.gats"

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
_THREE = re.compile(r"[A-Z0-9]{3}")


class PackagedList(UpstreamModel):
    """One packaged list: ``reference/<name>.json``.

    Attributes:
        param: The list, as the upstream path names it, e.g. ``"countries"``.
        endpoint: The upstream operation it was fetched from, e.g.
            ``"GATSData_GetCountries"``.
        fetched: Day the list was fetched (UTC).
        records: Upstream's records verbatim, under upstream's field names, in upstream
            order, e.g. ``{"countryCode": "CH", "regionCode": "R40", ...,
            "countryName": "China", ...}``.
    """

    param: str
    endpoint: str
    fetched: date
    records: list[dict[str, Any]]


def packaged_values(name: str) -> PackagedList | None:
    """The packaged list ``name``, or ``None`` when it is not packaged."""
    if name not in PACKAGED_LISTS:
        return None
    return PackagedList.model_validate(load_json(PACKAGE, f"{name}.json"))


@functools.cache
def _codes(name: str, code_field: str, name_field: str) -> tuple[str, dict[str, str]]:
    """Fetch date and ``{code: upstream name}`` of a packaged list, in upstream order."""
    packaged = packaged_values(name)
    if packaged is None:  # pragma: no cover - only the lists above are asked for
        raise KeyError(name)
    codes = {str(record[code_field]): str(record[name_field]) for record in packaged.records}
    return packaged.fetched.isoformat(), codes


@functools.cache
def _countries() -> dict[str, dict[str, Any]]:
    """The packaged ``countries`` records by ``countryCode``, in upstream order."""
    packaged = packaged_values("countries")
    if packaged is None:  # pragma: no cover - the list ships with the package
        raise KeyError("countries")
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
    """Up to three known codes close to ``value``: a three-letter code, then code, then name.

    sdk-usda-psd's matching, with GATS's ISO and GENC codes in front of it: an agent may
    pass ``"CHN"`` (``isO3Code`` and ``gencCode``) for ``"CH"``, ``"ch"`` for ``"CH"`` or
    ``"China"`` for ``"CH"``; each leads to the code. An exact three-letter match comes
    first, so ``"CHN"`` names ``CH`` (China) before ``CN`` (Comoros), which difflib finds
    close by its letters. Two-character codes are close only when they differ in case, so
    a code that shares one character with a known one (``"ZZ"``) gets none.
    """
    matches = list((three_letter or {}).get(value.upper(), []))
    matches += [
        code
        for code in difflib.get_close_matches(value.upper(), list(codes), n=3)
        if code not in matches
    ]
    by_name = {name.lower(): code for code, name in codes.items()}
    matches += [
        by_name[name]
        for name in difflib.get_close_matches(value.lower(), list(by_name), n=3)
        if by_name[name] not in matches
    ]
    return [(code, codes[code]) for code in matches[:3]]


def validate_partner_code(partner_code: str) -> str:
    """Check a partner code against the packaged ``countries`` list.

    GATS answers an unknown code with HTTP 200 and ``[]``, the same as a listed partner
    without trade (``unknown_partner.json``, ``no_data_valid_partner.json``), so the
    check runs before any upstream call. Every listed code passes here, the 26 with a
    ``discontinuedOn`` month included; ``validate_partner_month`` then refuses one for a
    month after it.

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
    fetched, codes = _codes("countries", "countryCode", "countryName")
    if not isinstance(partner_code, str):
        raise InvalidRequestError(
            f"partner_code must be a two-character GATS country code as text, such as "
            f"{PARTNER_EXAMPLES}, got {partner_code!r}. list_countries lists them.",
            source=SOURCE,
        )
    if partner_code in codes:
        return partner_code
    closest = _closest(partner_code, codes, _three_letter_codes())
    raise UnknownCode(
        "partner_code",
        partner_code,
        list_name="countries",
        fetched=fetched,
        closest=closest,
        hint=None
        if closest
        else (
            "GATS's partner codes are its own, two characters, as GATSData_GetCountries "
            f"lists them, e.g. {PARTNER_EXAMPLES}; list_countries lists every one and "
            "searches them by name, ISO or GENC code."
        ),
        reason=PARTNER_REASON,
    )


def validate_partner_month(partner_code: str, year: int, month: int) -> str:
    """Check a partner code, a year and a month, and that the code was current in that month.

    Runs ``validate_partner_code``, ``validate_year`` and ``validate_month``, then the
    code's ``discontinuedOn``: 26 codes of the packaged ``countries`` list carry one, a
    year and month as six digits (``SZ``, Switzerland, ``"198712"``), and GATS lists a
    successor under the same name for most (``SR``, Switzerland). The package reads that
    month as the code's last: a month at or before it passes, a later one is refused
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
        f"(discontinuedOn in GATS's countries list, packaged, fetched {fetched}): it holds "
        f"no trade after that month, so {year:04d}-{month:02d} ({asked}) is refused. "
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
    )


def validate_year(year: int) -> int:
    """Check that a year is a four-digit integer.

    The snapshot types ``year`` as ``int32`` and states no range, so none is invented
    beyond four digits. The Census release lists start at ``"196701"``
    (``tests/fixtures/GATSData_GetCensusExportDataReleaseInfo/all.json``); a task checks
    the month against its list after this.

    Args:
        year: The calendar year, e.g. ``2026``, ``1967``.

    Returns:
        The year, unchanged.

    Raises:
        InvalidRequestError: When the year is not an integer from 1000 to 9999 (``True``
            is not ``1``).
    """
    if isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999:
        raise InvalidRequestError(
            f"year must be a four-digit year such as 2026, got {year!r}. GATS's Census "
            "data starts in January 1967.",
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
