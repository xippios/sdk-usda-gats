"""Why GATS's codes the packaged lists lack are refused (conventions §5, ADR-0022).

GATS answers an unknown partner code with HTTP 200 and an empty list
(``tests/fixtures/GATSData_GetCensusExports/unknown_partner.json``, ``ZZ``), the same
answer as a listed partner without trade in that month (``no_data_valid_partner.json``,
``BV``, Bouvet Island): nothing in the answer tells the two apart. The package therefore
checks a code against its packaged list before calling upstream and refuses an unknown
one with core's ``UnknownCode``, naming the closest known codes, or example codes when
none is close (``params``). The same check covers the customs district a task keeps after
the call, the UN Trade ``reporter_code``, which GATS answers with ``[]`` when unknown
(``GATSData_GetUNTradeExports/unknown_reporter.json``), and the UN Trade filters
``partner_code`` and a six-digit ``hs6_code``. The reasons below go into
``UnknownCode``'s message as its ``reason=``, before core's closing sentence on refreshing
the packaged list; the customs-district reason is written inline in
``params.validate_customs_district_id``.
"""

__all__ = ["HS6_REASON", "PARTNER_REASON", "REPORTER_REASON", "UN_PARTNER_REASON"]

PARTNER_REASON = (
    "GATS answers an unknown partner code with an empty result, the same as a partner "
    "without trade, so the package refuses it."
)
"""Why an unknown ``partner_code`` of a Census task is refused, the default ``reason`` of
``params.validate_country_code``."""

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
