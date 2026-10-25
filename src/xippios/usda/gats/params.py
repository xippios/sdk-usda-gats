"""Packaged GATS reference lists and the argument checks of the Census tasks (conventions §3).

The countries list, ``GATSData_GetCountries``, ships inside the package under
``reference/`` so that a partner code is checked without a network call; GATS answers an
unknown code with an empty list (``errors.UnknownCode``). The other lists GATS publishes
are not packaged yet. ``scripts/refresh_reference.py`` writes the file through the
``api/`` wrapper, never by hand; ``reference/README.md`` carries its provenance. The file
keeps upstream's records verbatim, under upstream's field names.

The other checks need no list: a four-digit year, a month from 1 to 12 and an HS10 code
or prefix of 1 to 10 digits, all refused before any call.

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
from xippios.usda.gats.errors import UnknownCode

__all__ = [
    "PACKAGED_LISTS",
    "PackagedList",
    "packaged_values",
    "validate_hs10_code",
    "validate_month",
    "validate_partner_code",
    "validate_year",
]

PACKAGE = "xippios.usda.gats"

PACKAGED_LISTS: tuple[str, ...] = ("countries",)
"""Lists that ship inside the package, named as the upstream path names them.

Keep in step with ``TABLES`` in ``scripts/refresh_reference.py``, which checks it before
a refresh.
"""

PARTNER_EXAMPLES = '"CH" (China), "MX" (Mexico)'
"""Two partner codes from the packaged list, for messages that name no close code."""

_HS10 = re.compile(r"[0-9]{1,10}")


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


def _closest(value: str, codes: dict[str, str]) -> list[tuple[str, str]]:
    """Up to three known codes close to ``value``, by code first, then by upstream name.

    sdk-usda-psd's matching: an agent may pass ``"ch"`` for ``"CH"`` or ``"China"`` for
    ``"CH"``; both lead to the code. Two-character codes are close only when they differ
    in case, so a code that shares one character with a known one (``"ZZ"``) gets none.
    """
    matches = difflib.get_close_matches(value.upper(), list(codes), n=3)
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
    check runs before any upstream call. Every listed code passes, the 26 with a
    ``discontinuedOn`` month included: the months before it may hold their trade.

    Args:
        partner_code: Two characters, as ``GATSData_GetCountries`` lists them, e.g.
            ``"CH"`` (China), ``"MX"`` (Mexico), ``"01"`` (Caribbean,nes).

    Returns:
        The code, unchanged.

    Raises:
        InvalidRequestError: When the code is not text.
        UnknownCode: When the list lacks the code, naming up to three close codes with
            their upstream names, or two examples when none is close.
    """
    fetched, codes = _codes("countries", "countryCode", "countryName")
    if not isinstance(partner_code, str):
        raise InvalidRequestError(
            f"partner_code must be a two-character GATS country code as text, such as "
            f"{PARTNER_EXAMPLES}, got {partner_code!r}.",
            source=SOURCE,
        )
    if partner_code in codes:
        return partner_code
    closest = _closest(partner_code, codes)
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
            f"lists them, e.g. {PARTNER_EXAMPLES}."
        ),
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
