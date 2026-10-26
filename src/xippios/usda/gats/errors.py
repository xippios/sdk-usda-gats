"""GATS failure modes with a distinct meaning (conventions §5)."""

from xippios.core import InvalidRequestError

from xippios.usda.gats._client import SOURCE

__all__ = ["UnknownCode"]

PARTNER_REASON = (
    "GATS answers an unknown partner code with an empty result, the same as a partner "
    "without trade, so the package refuses it."
)
"""Why an unknown ``partner_code`` of a Census task is refused, the default ``reason`` of
``UnknownCode``."""

REPORTER_REASON = (
    "GATS answers an unknown reporter code with an empty result, as it answers a year "
    "without data, so the package refuses it."
)
"""Why an unknown ``reporter_code`` of a UN Trade task is refused: ``unknown_reporter.json``
(``ZZ``, 2019), ``future_year.json`` and ``unreleased_year.json`` under
``tests/fixtures/GATSData_GetUNTradeExports/`` all answer HTTP 200 with ``[]``."""

UN_PARTNER_REASON = (
    "The UN Trade operations take no partner: the task keeps this partner's records after "
    "the call, so a code the packaged list lacks would give an empty result, and the "
    "package refuses it."
)
"""Why an unknown ``partner_code`` of a UN Trade task is refused: there it is a filter."""

HS6_REASON = (
    "The UN Trade operations take no product: the task keeps the records whose HS6 code "
    "starts with hs6_code after the call, and every HS6 code of the recorded UN Trade "
    "answers is in the packaged list, so a full code it lacks would give an empty result, "
    "and the package refuses it. list_hs6_commodities lists the codes."
)
"""Why a six-digit ``hs6_code`` the packaged ``HS6Commodities`` list lacks is refused."""


class UnknownCode(InvalidRequestError):
    """A code the packaged GATS reference list does not contain (HTTP 422).

    GATS answers an unknown partner code with HTTP 200 and an empty list
    (``tests/fixtures/GATSData_GetCensusExports/unknown_partner.json``, ``ZZ``), the same
    answer as a listed partner without trade in that month (``no_data_valid_partner.json``,
    ``BV``, Bouvet Island): nothing in the answer tells the two apart. The package
    therefore checks a partner code against the packaged ``countries`` list before calling
    upstream and refuses an unknown one, naming the closest known codes, or example codes
    when none is close.

    The same check covers the customs district a task keeps after the call
    (``customs_district_id`` of the three customs-district tasks): the operations take no
    district, so an id the packaged ``customsDistricts`` list lacks would select nothing,
    an empty result like an unknown code's, and it is refused the same way, with its own
    ``reason``. The UN Trade tasks use it alike: their ``reporter_code``, which GATS
    answers with ``[]`` when unknown (``GATSData_GetUNTradeExports/unknown_reporter.json``),
    and their two filters, ``partner_code`` against ``countries`` and a six-digit
    ``hs6_code`` against ``HS6Commodities``, each with its own ``reason``.

    Attributes:
        param: The parameter, as the package names it, e.g. ``"partner_code"``,
            ``"reporter_code"``, ``"customs_district_id"``, ``"hs6_code"``.
        value: The value given, e.g. ``"ZZ"``, or ``12`` for a ``customs_district_id``.
        list_name: The packaged list checked, as upstream names it, e.g. ``"countries"``,
            ``"customsDistricts"``, ``"HS6Commodities"``.
        fetched: The day the packaged list was fetched, an ISO date, e.g. ``"2026-10-25"``.
        closest: The closest known codes with their upstream names, best match first;
            empty when none is close, and ``hint`` then says what the codes look like.
    """

    def __init__(
        self,
        param: str,
        value: str | int,
        *,
        list_name: str,
        fetched: str,
        closest: list[tuple[str, str]],
        hint: str | None = None,
        reason: str = PARTNER_REASON,
    ) -> None:
        if closest:
            hint = "Did you mean " + ", ".join(f"{code} ({name})" for code, name in closest) + "?"
        article = "an" if param[:1] in set("aeiou") else "a"
        super().__init__(
            f"{value!r} is not {article} {param} in GATS's {list_name} list (packaged, "
            f"fetched {fetched}).{' ' + hint if hint else ''} {reason} If GATS added it "
            "since, the packaged list needs a refresh (/refresh-reference-data).",
            source=SOURCE,
        )
        self.param = param
        self.value = value
        self.list_name = list_name
        self.fetched = fetched
        self.closest = closest
