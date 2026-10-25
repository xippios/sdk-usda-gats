"""The client's error mapping, and core's quota policy wired to the gateway's answers.

Recorded answers come from ``tests/fixtures``: the invalid-key answer
(``GATSData_GetRegions/invalid_key.json``, sent with a made-up key on 2026-10-25) and the
quota headers of the keyed answers. GATS has no recorded 429: the gateway's 429 and its
``NOT_FOUND`` 404 are built in the shape api.data.gov documents and sdk-usda-psd recorded
(its ``PSDData_GetCommodities/over_rate_limit.json``, 2026-10-23), and every such test
says so. The quota policy itself is core's (``QuotaPolicy``, ADR-0015) and is tested
there; this module checks that the package installs it on the gateway's headers, that it
reads a 429, and that ``classify`` shapes core's retries of a 429.
"""

import dataclasses
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import AsyncClient, AuthError, NotFoundError, RateLimitError, RetryPolicy
from xippios.core.testing import ReplayFixture, load_fixture, sent_urls

from xippios.usda.gats import api
from xippios.usda.gats._client import (
    API_KEY_ENV,
    BASE_URL,
    CACHED_PATHS,
    RATE_LIMIT,
    RELEASE_DATES_TTL,
    auth,
    cache,
    cache_filter,
    classify,
    client,
    config,
    policy,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGIONS = "/api/gats/regions"
EXPORT_RELEASES = "/api/gats/census/data/exports/dataReleaseDates"
IMPORT_RELEASES = "/api/gats/census/data/imports/dataReleaseDates"


@pytest.fixture(autouse=True)
def empty_cache() -> Iterator[None]:
    """The client caches the release-date lists for an hour (``_client.cache``): each
    test starts and ends without an entry, so a list one test fetched never answers the
    route the next test mounted, nor the refusal a quota test expects."""
    cache.clear()
    yield
    cache.clear()


def recorded(endpoint: str, case: str) -> httpx.Response:
    """A recorded answer as an ``httpx.Response``, for calling ``classify`` directly."""
    fixture = load_fixture(FIXTURES / endpoint / f"{case}.json")
    return httpx.Response(
        fixture.response.status,
        headers=fixture.response.headers,
        content=fixture.response.content,
        request=httpx.Request(fixture.request.method, fixture.request.url),
    )


def synthesised(
    status: int, body: object, headers: dict[str, str] | None = None, path: str = REGIONS
) -> httpx.Response:
    """NOT RECORDED as such: an answer in the shape api.data.gov documents and sends."""
    return httpx.Response(
        status,
        json=body,
        headers=headers or {},
        request=httpx.Request("GET", f"{BASE_URL}{path}"),
    )


OVER_RATE_LIMIT = {
    "error": {
        "code": "OVER_RATE_LIMIT",
        "message": (
            "You have exceeded your rate limit. Try again later or contact us for "
            "assistance: https://api.fas.usda.gov:443"
        ),
    }
}
"""NOT RECORDED here: the 429 body sdk-usda-psd recorded from the same gateway."""
SPENT = {"Retry-After": "3151", "x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
"""NOT RECORDED here: the quota headers of sdk-usda-psd's recorded 429."""
NOT_FOUND = {
    "error": {
        "code": "NOT_FOUND",
        "message": "The requested URL was not found on this server.",
    }
}
"""NOT RECORDED: api.data.gov's documented NOT_FOUND body."""


def test_the_client_is_wired_for_the_gateway() -> None:
    """One request per second, gats's classify, and core's quota policy on api.data.gov's
    ``x-ratelimit-*`` headers, which count the rolling hour, not a pace; the gateway sends
    no reset header, so one hour is the fallback wait (ADR-0010, ADR-0015)."""
    assert (RATE_LIMIT.per_minute, RATE_LIMIT.capacity) == (60, 1)
    assert config.rate_limit is RATE_LIMIT
    assert config.classify is classify
    assert client.config is config
    assert config.observe == policy.observe, "installed: every answer reaches the policy"
    assert config.before_request is not None
    assert (policy.limit_header, policy.remaining_header, policy.reset_header) == (
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        None,
    )
    assert (policy.window, policy.source) == (3600.0, "usda-gats")
    assert auth.header == "X-Api-Key"
    assert auth.env_var == API_KEY_ENV == "DATA_GOV_API_KEY"  # pragma: allowlist secret


def test_the_client_asks_for_json() -> None:
    """The snapshot's operations produce JSON and XML; httpx alone sends ``Accept: */*``."""
    assert config.headers == {"Accept": "application/json"}


@pytest.mark.parametrize(
    ("endpoint", "case", "remaining"),
    [
        ("GATSData_GetCountries", "all", "969"),
        ("GATSData_GetCensusExports", "CH_2026_8", "966"),
        ("GATSData_GetCensusExports", "unknown_partner", "965"),
        ("GATSData_GetCensusExports", "month_13", "964"),
        ("GATSData_GetCensusImport", "CH_2026_8", "965"),
    ],
)
def test_keyed_gats_answers_carry_the_hourly_quota(
    endpoint: str, case: str, remaining: str
) -> None:
    """The quota the policy reads is on GATS paths too, the 404s included: 1,000 per hour."""
    response = recorded(endpoint, case)
    assert response.headers["x-ratelimit-limit"] == "1000"
    assert response.headers["x-ratelimit-remaining"] == remaining
    assert "x-ratelimit-reset" not in response.headers


def test_invalid_key_is_an_auth_error_naming_the_code_and_the_variable() -> None:
    response = recorded("GATSData_GetRegions", "invalid_key")
    error = classify(response)
    assert isinstance(error, AuthError)
    assert error.status == 403
    assert "API_KEY_INVALID" in error.message
    assert API_KEY_ENV in error.message
    assert "An invalid api_key was supplied. Get one at <host>" in error.message
    assert "api.fas.usda.gov" not in error.message, "host-free (conventions §5)"
    assert error.source == "usda-gats"


def test_the_recorded_invalid_key_answer_is_the_documented_shape() -> None:
    """The bad-key answer carries api.data.gov's error object and no quota headers: the
    gateway refuses it before counting."""
    response = recorded("GATSData_GetRegions", "invalid_key")
    body = json.loads(response.text)
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert "x-ratelimit-remaining" not in response.headers
    assert "x-ratelimit-limit" not in response.headers


@pytest.mark.parametrize(
    "code",
    ["API_KEY_MISSING", "API_KEY_DISABLED", "API_KEY_UNAUTHORIZED", "API_KEY_UNVERIFIED"],
)
def test_every_documented_key_code_is_an_auth_error(code: str) -> None:
    """NOT RECORDED: the other documented codes, in the recorded body's shape."""
    error = classify(synthesised(403, {"error": {"code": code, "message": "documented"}}))
    assert isinstance(error, AuthError)
    assert code in error.message


def test_a_403_without_a_gateway_code_falls_through_to_core() -> None:
    assert classify(synthesised(403, {"Message": "Access denied"})) is None


@pytest.mark.anyio
async def test_a_call_raises_auth_error_on_the_recorded_invalid_key(
    replay_fixture: ReplayFixture, placeholder_api_key: str
) -> None:
    route = replay_fixture("GATSData_GetRegions", "invalid_key")
    with pytest.raises(AuthError, match="API_KEY_INVALID") as info:
        await client.get_json(REGIONS)
    assert placeholder_api_key not in str(info.value)
    assert route.call_count == 1, "a 403 is never retried"
    assert sent_urls(route) == [f"{BASE_URL}{REGIONS}"]


def test_the_gateway_not_found_is_a_not_found_error() -> None:
    """NOT RECORDED: api.data.gov's documented NOT_FOUND body."""
    error = classify(synthesised(404, NOT_FOUND))
    assert isinstance(error, NotFoundError)
    assert f"no route for {REGIONS} (HTTP 404 NOT_FOUND" in error.message
    assert "api.fas.usda.gov" not in error.message


@pytest.mark.anyio
async def test_a_call_raises_not_found_error_on_the_gateway_not_found(
    respx_mock: respx.MockRouter,
) -> None:
    """NOT RECORDED: the gateway's NOT_FOUND through the package's client, sent once."""
    route = respx_mock.get(f"{BASE_URL}/api/gats/nowhere").mock(
        return_value=httpx.Response(404, json=NOT_FOUND)
    )
    with pytest.raises(NotFoundError, match="no route for /api/gats/nowhere"):
        await client.get_json("/api/gats/nowhere")
    assert route.call_count == 1


def test_an_empty_404_falls_through_to_core() -> None:
    """The recorded month-0 answer: no gateway code, so ``classify`` leaves it to core."""
    response = recorded("GATSData_GetCensusExports", "month_0")
    assert (response.status_code, response.content) == (404, b"")
    assert classify(response) is None


def test_other_statuses_fall_through_to_core() -> None:
    assert classify(synthesised(500, {"Message": "An error has occurred."})) is None
    assert classify(recorded("GATSData_GetCountries", "all")) is None


def test_a_429_is_a_rate_limit_error_with_its_retry_after() -> None:
    """NOT RECORDED here: psd's recorded 429, body and quota headers, on a GATS path."""
    error = classify(synthesised(429, OVER_RATE_LIMIT, SPENT))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 3151.0
    assert "OVER_RATE_LIMIT: You have exceeded your rate limit" in error.message
    assert "api.fas.usda.gov" not in error.message, "host-free (conventions §5)"
    assert "expected back in 3151 s" in error.message, "no snapshot without the client"
    assert "Nothing was retried" in error.message
    assert "retry after" not in error.message, "core's adapters append the retry hint"
    assert API_KEY_ENV in error.message
    assert error.source == "usda-gats"


def test_429_without_retry_after_falls_back_to_the_quota_window() -> None:
    """NOT RECORDED: the 429 body without Retry-After or quota headers."""
    error = classify(synthesised(429, OVER_RATE_LIMIT))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == policy.window == 3600.0
    assert "an hourly quota per key" in error.message, "no limit known, none invented"
    assert "expected back in 3600 s" in error.message


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_the_policy_reads_a_429_through_core(respx_mock: respx.MockRouter) -> None:
    """NOT RECORDED here: psd's recorded 429 mocked on a GATS path, through the package's
    client. Core's ``observe`` marks the quota spent until its ``Retry-After``, ``classify``
    raises after one request (3151 s is beyond ``backoff_max``), and the next request is
    refused before it is sent. Marked ``rate_limited``: the refusal is the policy's pause,
    which the plugin turns off."""
    route = respx_mock.get(f"{BASE_URL}/api/gats/countries").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=SPENT)
    )
    with pytest.raises(RateLimitError) as info:
        await api.GATSData_GetCountries()
    assert info.value.retry_after == 3151.0
    assert route.call_count == 1, "not retried"
    assert "1000 requests per rolling hour per key" in info.value.message
    assert "0 of 1000 requests left" in info.value.message
    snapshot = policy.snapshot()
    assert snapshot is not None
    assert (snapshot.limit, snapshot.remaining) == (1000, 0)
    assert snapshot.resumes_at == snapshot.observed_at + timedelta(seconds=3151)
    releases = respx_mock.get(f"{BASE_URL}/api/gats/census/data/exports/dataReleaseDates")
    with pytest.raises(RateLimitError, match="nothing was sent") as refused:
        await api.GATSData_GetCensusExportDataReleaseInfo()
    assert refused.value.retry_after is not None
    assert 3140 <= refused.value.retry_after <= 3151
    assert route.call_count == 1
    assert releases.call_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("retry_after", "shaped", "attempts"),
    [("3151", True, 1), (None, True, 1), (None, False, 4)],
    ids=["with_retry_after", "without_retry_after", "control_without_classify"],
)
async def test_core_retries_a_429_only_within_its_backoff(
    respx_mock: respx.MockRouter, retry_after: str | None, shaped: bool, attempts: int
) -> None:
    """NOT RECORDED here: psd's recorded 429, with or without its ``Retry-After``. gats's
    ``classify`` shapes core's retries (ADR-0015): its ``RateLimitError`` carries the wait,
    ``Retry-After`` or else the one-hour window, beyond ``backoff_max`` (30 s), so a 429 is
    sent once, with or without the header. The control drops ``classify``: core then
    retries the 429 without ``Retry-After`` on its status alone, three more times at its
    short backoff, so this test fails if ``classify`` stops shaping the retries."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    headers = {
        name: value
        for name, value in SPENT.items()
        if retry_after is not None or name != "Retry-After"
    }
    route = respx_mock.get(f"{BASE_URL}{REGIONS}").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=headers)
    )
    quick = dataclasses.replace(config, rate_limit=None)
    if not shaped:
        quick = dataclasses.replace(quick, classify=None)
    with pytest.raises(RateLimitError) as info:
        await AsyncClient(quick, sleep=fake_sleep).get_json(REGIONS)
    assert route.call_count == attempts
    assert len(sleeps) == attempts - 1
    assert all(seconds <= RetryPolicy().backoff_max for seconds in sleeps)
    if shaped:
        assert info.value.retry_after == float(retry_after or 3600)
    else:
        assert info.value.retry_after is None, "core's own mapping: no Retry-After, no wait"


def test_the_client_caches_the_census_release_date_lists_and_nothing_else() -> None:
    """Core's cache, for one hour, on the two release-date paths only (ADR-0015's
    ``cache_filter``): the data, the countries and every other path go to the wire."""
    assert config.cache is cache
    assert config.cache_filter is cache_filter
    assert cache.ttl == RELEASE_DATES_TTL == 3600.0
    assert {EXPORT_RELEASES, IMPORT_RELEASES} == CACHED_PATHS
    for path, cached in [
        (EXPORT_RELEASES, True),
        (IMPORT_RELEASES, True),
        ("/api/gats/censusExports/partnerCode/CH/year/2026/month/8", False),
        ("/api/gats/censusImports/partnerCode/CH/year/2026/month/8", False),
        ("/api/gats/countries", False),
        ("/api/gats/UNTrade/data/exports/dataReleaseDates", False),
        (REGIONS, False),
    ]:
        assert cache_filter(httpx.Request("GET", f"{BASE_URL}{path}")) is cached, path


@pytest.mark.anyio
async def test_a_release_list_is_fetched_once_and_then_answered_from_the_cache(
    replay_fixture: ReplayFixture,
) -> None:
    """The second call sends nothing and says when the entry was stored, for
    ``meta.retrieved_at`` (conventions §4); each flow's list is an entry of its own."""
    exports = replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    imports = replay_fixture("GATSData_GetCensusImportDataReleaseInfo", "all")
    before = datetime.now(UTC)
    first, first_stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    after = datetime.now(UTC)
    again, stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert first_stored is None, "the first answer came from the wire"
    assert stored is not None
    assert before <= stored <= after, "when the first answer was stored, as UTC"
    assert again == first
    assert exports.call_count == 1
    assert sent_urls(exports) == [f"{BASE_URL}{EXPORT_RELEASES}"]
    _, imports_stored = await api.GATSData_GetCensusImportDataReleaseInfo()
    assert imports_stored is None, "the imports list is not the exports list's entry"
    assert imports.call_count == 1


@pytest.mark.anyio
async def test_census_data_is_never_cached(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCensusExports", "CH_2026_8")
    await api.GATSData_GetCensusExports("CH", 2026, 8)
    await api.GATSData_GetCensusExports("CH", 2026, 8)
    assert route.call_count == 2
    assert len(cache) == 0


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_a_cached_release_list_answers_while_the_quota_is_spent(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """NOT RECORDED here: psd's recorded 429 mocked on a GATS path spends the quota; the
    release list cached before it still answers, since a cache hit returns before the
    quota policy's check (ADR-0015), while the uncached countries list is refused unsent.
    Marked ``rate_limited``: the refusal is the policy's pause, which the plugin turns off."""
    releases = replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    first, _ = await api.GATSData_GetCensusExportDataReleaseInfo()
    spent = respx_mock.get(f"{BASE_URL}{REGIONS}").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=SPENT)
    )
    with pytest.raises(RateLimitError):
        await client.get_json(REGIONS)
    cached, stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert (cached, stored is not None) == (first, True)
    assert releases.call_count == 1
    countries = respx_mock.get(f"{BASE_URL}/api/gats/countries")
    with pytest.raises(RateLimitError, match="nothing was sent"):
        await api.GATSData_GetCountries()
    assert (spent.call_count, countries.call_count) == (1, 0)
