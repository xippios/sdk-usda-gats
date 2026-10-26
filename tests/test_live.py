"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

One live smoke test per task function, three in all, four keyed calls: each data task
spends two, its flow's release list and the month, and ``get_census_release_dates`` for
``X`` runs after ``get_census_exports`` and answers from the client's cache, which the
tests share, without a call. The data tasks ask for Iceland (``"IC"``), a listed partner
with modest trade, so the nightly run stays light, in August 2026, released on
2026-10-06; ``vintage`` is that month's release time as upstream writes it, a date and a
time without a zone. The tests record what they answered as test properties
(``--junitxml`` shows them), never a key. Next to them, the template's reachability check,
``test_upstream_answers``, sends no key: a plain request to ``BASE_URL`` that spends no
quota call.
"""

import re
from collections.abc import Callable

import httpx
import pytest

from xippios.usda.gats import tasks
from xippios.usda.gats._client import BASE_URL, config, policy
from xippios.usda.gats.models import ProductType
from xippios.usda.gats.params import validate_partner_code

pytestmark = [pytest.mark.live, pytest.mark.anyio]

PARTNER = validate_partner_code("IC")  # Iceland, in the packaged countries list
YEAR, MONTH = 2026, 8
RELEASE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


async def test_upstream_answers() -> None:
    """The base URL answers without a server error (sdk-template's reachability check).

    A plain request, not the package's client, so no key goes out and no call counts
    against the key's quota; a keyed gateway's answer to it (a 403 or a 404, say) still
    shows the host is up.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        timeout=config.timeouts.to_httpx(),
        follow_redirects=True,
    ) as http:
        response = await http.get(BASE_URL)
    assert response.status_code < 500


def _vintage_is_a_release_time(vintage: str | None) -> None:
    assert vintage is not None
    assert RELEASE_TIME.match(vintage), vintage


def _quota_is_the_gateways() -> None:
    snapshot = policy.snapshot()
    assert snapshot is not None
    assert snapshot.limit == 1000


async def test_get_census_exports_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_census_exports_async(PARTNER, YEAR, MONTH)
    assert result.data
    assert {(r.country_code, r.date) for r in result.data} == {(PARTNER, "202608")}
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.published_at is None
    _quota_is_the_gateways()
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


async def test_get_census_imports_live(record_property: Callable[[str, object], None]) -> None:
    result = await tasks.get_census_imports_async(PARTNER, YEAR, MONTH)
    assert result.data
    assert {(r.country_code, r.date) for r in result.data} == {(PARTNER, "202608")}
    _vintage_is_a_release_time(result.meta.vintage)
    assert result.meta.published_at is None
    _quota_is_the_gateways()
    record_property("records", len(result.data))
    record_property("vintage", result.meta.vintage)


async def test_get_census_release_dates_live(
    record_property: Callable[[str, object], None],
) -> None:
    result = await tasks.get_census_release_dates_async(ProductType.X)
    months = [r.statistical_year_month for r in result.data]
    assert max(months) >= "202608"
    assert min(months) == "196701"
    assert months == sorted(months, reverse=True), "newest first"
    assert {r.product_type for r in result.data} == {ProductType.X}
    assert (result.meta.published_at, result.meta.vintage) == (None, None)
    record_property("latest", months[0])
    record_property("released", result.data[0].release_time_stamp.isoformat())
