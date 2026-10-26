"""GATS failure modes with a distinct meaning (conventions §5)."""

from xippios.core import InvalidRequestError

from xippios.usda.gats._client import SOURCE

__all__ = ["UnknownCode"]


class UnknownCode(InvalidRequestError):
    """A code the packaged GATS reference list does not contain (HTTP 422).

    GATS answers an unknown partner code with HTTP 200 and an empty list
    (``tests/fixtures/GATSData_GetCensusExports/unknown_partner.json``, ``ZZ``), the same
    answer as a listed partner without trade in that month (``no_data_valid_partner.json``,
    ``BV``, Bouvet Island): nothing in the answer tells the two apart. The package
    therefore checks a partner code against the packaged ``countries`` list before calling
    upstream and refuses an unknown one, naming the closest known codes, or example codes
    when none is close.

    Attributes:
        param: The parameter, as the package names it, e.g. ``"partner_code"``.
        value: The value given, e.g. ``"ZZ"``.
        list_name: The packaged list checked, as upstream names it, e.g. ``"countries"``.
        fetched: The day the packaged list was fetched, an ISO date, e.g. ``"2026-10-25"``.
        closest: The closest known codes with their upstream names, best match first;
            empty when none is close, and ``hint`` then says what the codes look like.
    """

    def __init__(
        self,
        param: str,
        value: str,
        *,
        list_name: str,
        fetched: str,
        closest: list[tuple[str, str]],
        hint: str | None = None,
    ) -> None:
        if closest:
            hint = "Did you mean " + ", ".join(f"{code} ({name})" for code, name in closest) + "?"
        super().__init__(
            f"{value!r} is not a {param} in GATS's {list_name} list (packaged, fetched "
            f"{fetched}).{' ' + hint if hint else ''} GATS answers an unknown partner code "
            "with an empty result, the same as a partner without trade, so the package "
            "refuses it. If GATS added the code since, the packaged list needs a refresh "
            "(/refresh-reference-data).",
            source=SOURCE,
        )
        self.param = param
        self.value = value
        self.list_name = list_name
        self.fetched = fetched
        self.closest = closest
