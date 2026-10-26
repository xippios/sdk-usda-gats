"""GATS failure modes with a distinct meaning (conventions §5)."""

from xippios.core import InvalidRequestError

from xippios.usda.gats._client import SOURCE

__all__ = ["UnknownCode"]

PARTNER_REASON = (
    "GATS answers an unknown partner code with an empty result, the same as a partner "
    "without trade, so the package refuses it."
)
"""Why an unknown ``partner_code`` is refused, the default ``reason`` of ``UnknownCode``."""


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
    ``reason``.

    Attributes:
        param: The parameter, as the package names it, e.g. ``"partner_code"``,
            ``"customs_district_id"``.
        value: The value given, e.g. ``"ZZ"``, or ``12`` for a ``customs_district_id``.
        list_name: The packaged list checked, as upstream names it, e.g. ``"countries"``,
            ``"customsDistricts"``.
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
