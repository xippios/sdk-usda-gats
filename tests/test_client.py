"""The client's error mapping, and core's quota policy wired to the gateway's answers.

Recorded answers come from ``tests/fixtures``: the invalid-key answer
(``GATSData_GetRegions/invalid_key.json``, sent with a made-up key on 2026-10-25) and the
quota headers of the keyed answers. GATS has no recorded 429: the gateway's 429 and its
``NOT_FOUND`` 404 are built in the shape api.data.gov documents and sdk-usda-psd recorded
(its ``PSDData_GetCommodities/over_rate_limit.json``, 2026-10-23), and every such test
says so. The gateway's mapping and its quota policy are core's (``xippios.core.data_gov``,
ADR-0009, ADR-0015) and are tested there; this module checks that the package installs
them, that the policy reads a 429 on a GATS path, and that ``classify`` shapes core's
retries of a 429.
"""

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import (
    AsyncClient,
    AuthError,
    MemoryCache,
    NotFoundError,
    RateLimitError,
    RetryPolicy,
)
from xippios.core.client import CachedResponse, cache_key
from xippios.core.data_gov import API_KEY_ENV, Gateway
from xippios.core.testing import (
    CLOCK_SLACK,
    ReplayFixture,
    assert_time_between,
    load_fixture,
    response_from_fixture,
    sent_urls,
)

from xippios.usda.gats import api
from xippios.usda.gats._client import (
    BASE_URL,
    CACHED_PATHS,
    COMMODITIES_PATH,
    COMMODITIES_TTL,
    RATE_LIMIT,
    RELEASE_DATES_PATHS,
    RELEASE_DATES_TTL,
    PathCaches,
    auth,
    cache,
    cache_filter,
    classify,
    client,
    commodities_cache,
    config,
    gateway,
    release_dates_cache,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGIONS = "/api/gats/regions"
EXPORT_RELEASES = "/api/gats/census/data/exports/dataReleaseDates"
IMPORT_RELEASES = "/api/gats/census/data/imports/dataReleaseDates"
UN_EXPORT_RELEASES = "/api/gats/UNTrade/data/exports/dataReleaseDates"
UN_IMPORT_RELEASES = "/api/gats/UNTrade/data/imports/dataReleaseDates"


def recorded(endpoint: str, case: str) -> httpx.Response:
    """A recorded answer as an ``httpx.Response``, for calling ``classify`` directly."""
    return response_from_fixture(load_fixture(FIXTURES / endpoint / f"{case}.json"))


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
    """One request per second, gats's classify, and the gateway's quota policy, one per
    process, on api.data.gov's ``x-ratelimit-*`` headers, which count the rolling hour,
    not a pace; one hour is the wait without ``Retry-After`` (ADR-0009, ADR-0010,
    ADR-0015)."""
    assert (RATE_LIMIT.per_minute, RATE_LIMIT.capacity) == (60, 1)
    assert config.rate_limit is RATE_LIMIT
    assert config.classify is classify
    assert client.config is config
    policy = Gateway.policy
    assert config.observe == policy.observe, "installed: every answer reaches the policy"
    assert config.before_request == policy.before_request
    assert (policy.limit_header, policy.remaining_header) == (
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
    )
    assert (policy.window, policy.source) == (3600.0, "api.data.gov")
    assert gateway.source == "usda-gats"
    assert auth is gateway.auth
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
        ("GATSData_GetUNTradeExportDataReleaseInfo", "all", "992"),
        ("GATSData_GetUNTradeExports", "IC_2019", "991"),
        ("GATSData_GetUNTradeExports", "year_text", "985"),
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
    assert "retry after" not in error.message, "core's adapters append the retry hint"
    assert API_KEY_ENV in error.message
    assert error.source == "usda-gats"


def test_429_without_retry_after_falls_back_to_the_quota_window() -> None:
    """NOT RECORDED: the 429 body without Retry-After or quota headers."""
    error = classify(synthesised(429, OVER_RATE_LIMIT))
    assert isinstance(error, RateLimitError)
    assert error.retry_after == Gateway.policy.window == 3600.0
    assert "an hourly quota per key" in error.message, "no limit known, none invented"
    assert "expected back in 3600 s" in error.message


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_the_policy_reads_a_429_through_core(respx_mock: respx.MockRouter) -> None:
    """NOT RECORDED here: psd's recorded 429 mocked on a GATS path, through the package's
    client. Core's ``observe`` marks the gateway's quota spent until its ``Retry-After``,
    ``classify`` raises after one request (3151 s is beyond ``backoff_max``) with the
    snapshot's wait from now, and the next request is refused before it is sent, in the
    gateway's name. Marked ``rate_limited``: the refusal is the policy's pause, which the
    plugin turns off."""
    route = respx_mock.get(f"{BASE_URL}/api/gats/countries").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=SPENT)
    )
    with pytest.raises(RateLimitError) as info:
        await api.GATSData_GetCountries()
    slack = CLOCK_SLACK.total_seconds()
    assert info.value.retry_after is not None
    assert 3151 - slack <= info.value.retry_after <= 3151, "the snapshot's wait from now"
    assert info.value.source == "usda-gats"
    assert route.call_count == 1, "not retried"
    assert "1000 requests per rolling hour per key" in info.value.message
    assert "0 of 1000 requests left" in info.value.message
    snapshot = Gateway.policy.snapshot()
    assert snapshot is not None
    assert (snapshot.limit, snapshot.remaining) == (1000, 0)
    assert snapshot.resumes_at == snapshot.observed_at + timedelta(seconds=3151)
    releases = respx_mock.get(f"{BASE_URL}/api/gats/census/data/exports/dataReleaseDates")
    with pytest.raises(RateLimitError, match="nothing was sent") as refused:
        await api.GATSData_GetCensusExportDataReleaseInfo()
    assert refused.value.message.startswith(
        "api.data.gov quota of the key in DATA_GOV_API_KEY spent"  # pragma: allowlist secret
    )
    assert refused.value.source == "api.data.gov"
    assert refused.value.retry_after is not None
    assert 3151 - slack <= refused.value.retry_after <= 3151
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
    ``Retry-After`` or else the one-hour window, counted from the snapshot core's
    ``observe`` took, so a fraction under it read through the client, and beyond
    ``backoff_max`` (30 s), so a 429 is sent once, with or without the header. The control
    drops ``classify``: core then retries the 429 without ``Retry-After`` on its status
    alone, three more times at its short backoff, so this test fails if ``classify`` stops
    shaping the retries."""
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
        wait = float(retry_after or 3600)
        assert info.value.retry_after is not None
        assert wait - CLOCK_SLACK.total_seconds() <= info.value.retry_after <= wait
    else:
        assert info.value.retry_after is None, "core's own mapping: no Retry-After, no wait"


def test_the_client_caches_five_paths_and_nothing_else() -> None:
    """Core's cache on the four release-date paths, Census and UN Trade, for an hour, and
    the commodities path, for a day (ADR-0015's ``cache_filter``, a ``MemoryCache`` per
    TTL behind ``PathCaches``): the data, the countries and every other path go to the
    wire."""
    assert config.cache is cache
    assert config.cache_filter is cache_filter
    assert isinstance(cache, PathCaches)
    assert release_dates_cache.ttl == RELEASE_DATES_TTL == 3600.0
    assert commodities_cache.ttl == COMMODITIES_TTL == 86400.0
    releases = {EXPORT_RELEASES, IMPORT_RELEASES, UN_EXPORT_RELEASES, UN_IMPORT_RELEASES}
    assert releases == RELEASE_DATES_PATHS
    assert COMMODITIES_PATH == "/api/gats/commodities"
    assert {*releases, COMMODITIES_PATH} == CACHED_PATHS
    assert cache.by_path == {
        EXPORT_RELEASES: release_dates_cache,
        IMPORT_RELEASES: release_dates_cache,
        UN_EXPORT_RELEASES: release_dates_cache,
        UN_IMPORT_RELEASES: release_dates_cache,
        COMMODITIES_PATH: commodities_cache,
    }
    for path, cached in [
        (EXPORT_RELEASES, True),
        (IMPORT_RELEASES, True),
        (UN_EXPORT_RELEASES, True),
        (UN_IMPORT_RELEASES, True),
        (COMMODITIES_PATH, True),
        ("/api/gats/censusExports/partnerCode/CH/year/2026/month/8", False),
        ("/api/gats/censusImports/partnerCode/CH/year/2026/month/8", False),
        ("/api/gats/customsDistrictExports/partnerCode/IC/year/2026/month/8", False),
        ("/api/gats/UNTradeExports/reporterCode/IC/year/2019", False),
        ("/api/gats/UNTradeImports/reporterCode/TP/year/2019", False),
        ("/api/gats/UNTradeReExports/reporterCode/MC/year/2019", False),
        ("/api/gats/countries", False),
        ("/api/gats/HS6Commodities", False),
        (REGIONS, False),
    ]:
        assert cache_filter(httpx.Request("GET", f"{BASE_URL}{path}")) is cached, path


def _entry(stored_at: float) -> CachedResponse:
    return CachedResponse(status=200, headers=(), content=b"[]", stored_at=stored_at)


def test_each_path_keeps_its_own_ttl() -> None:
    """``PathCaches`` with clocks of its own: two hours on, the release list's entry has
    expired and the commodities entry still answers; past a day, it has expired too. A
    key of no path named, or of a named path with a query, is neither stored nor looked
    up, and ``by_path`` cannot be changed under the routing."""
    now = [1_000_000.0]
    hourly = MemoryCache(ttl=RELEASE_DATES_TTL, maxsize=8, clock=lambda: now[0])
    daily = MemoryCache(ttl=COMMODITIES_TTL, maxsize=1, clock=lambda: now[0])
    caches = PathCaches({EXPORT_RELEASES: hourly, COMMODITIES_PATH: daily})
    with pytest.raises(TypeError):
        caches.by_path[REGIONS] = hourly  # type: ignore[index]
    releases = cache_key("GET", httpx.URL(f"{BASE_URL}{EXPORT_RELEASES}"))
    commodities = cache_key("GET", httpx.URL(f"{BASE_URL}{COMMODITIES_PATH}"))
    other = cache_key("GET", httpx.URL(f"{BASE_URL}{REGIONS}"))
    queried = cache_key("GET", httpx.URL(f"{BASE_URL}{COMMODITIES_PATH}", params={"a": "1"}))
    for key in (releases, commodities, other, queried):
        caches.set(key, _entry(now[0]))
    assert (len(hourly), len(daily), len(caches)) == (1, 1, 2), "the other keys are dropped"
    assert caches.get(other) is None
    assert caches.get(queried) is None
    now[0] += 2 * 3600
    assert caches.get(releases) is None, "an hour has passed"
    assert caches.get(commodities) is not None, "a day has not"
    now[0] += COMMODITIES_TTL
    assert caches.get(commodities) is None
    caches.set(commodities, _entry(now[0]))
    caches.clear()
    assert len(caches) == 0


@pytest.mark.anyio
async def test_the_commodities_list_lands_in_the_daily_cache(
    replay_fixture: ReplayFixture,
) -> None:
    """Through the real client: the commodities answer is stored in the day's cache, a
    release list in the hour's, and the second commodities call sends nothing and carries
    the entry's stored time."""
    commodities = replay_fixture("GATSData_GetCommodities", "all")
    replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    first, _ = await api.GATSData_GetCommodities()
    await api.GATSData_GetCensusExportDataReleaseInfo()
    assert (len(commodities_cache), len(release_dates_cache)) == (1, 1)
    entry = commodities_cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{COMMODITIES_PATH}")))
    assert entry is not None
    again, retrieved_at = await api.GATSData_GetCommodities()
    assert retrieved_at == datetime.fromtimestamp(entry.stored_at, UTC)
    assert len(again) == len(first) == 24936
    assert commodities.call_count == 1
    assert sent_urls(commodities) == [f"{BASE_URL}{COMMODITIES_PATH}"]


@pytest.mark.anyio
async def test_a_release_list_is_fetched_once_and_then_answered_from_the_cache(
    replay_fixture: ReplayFixture,
) -> None:
    """The first call says when the answer arrived, the second sends nothing and says when
    the entry was stored, for ``meta.retrieved_at`` (conventions §4, ``get_answer``); each
    flow's list is an entry of its own."""
    exports = replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    imports = replay_fixture("GATSData_GetCensusImportDataReleaseInfo", "all")
    before = datetime.now(UTC)
    first, first_at = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert_time_between(first_at, before, datetime.now(UTC))
    assert exports.call_count == 1, "the first answer came from the wire"
    entry = cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{EXPORT_RELEASES}")))
    assert entry is not None
    again, stored = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert stored == datetime.fromtimestamp(entry.stored_at, UTC), "when it was stored"
    assert stored.tzinfo is UTC
    assert again == first
    assert exports.call_count == 1
    assert sent_urls(exports) == [f"{BASE_URL}{EXPORT_RELEASES}"]
    await api.GATSData_GetCensusImportDataReleaseInfo()
    assert imports.call_count == 1, "the imports list is not the exports list's entry"


@pytest.mark.anyio
async def test_census_data_is_never_cached(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetCensusExports", "CH_2026_8")
    await api.GATSData_GetCensusExports("CH", 2026, 8)
    await api.GATSData_GetCensusExports("CH", 2026, 8)
    assert route.call_count == 2
    assert len(cache) == 0


@pytest.mark.anyio
async def test_the_un_release_lists_land_in_the_release_dates_store(
    replay_fixture: ReplayFixture,
) -> None:
    """Through the real client: each UN Trade list is an entry of the hour's store, beside
    the Census lists, never the day's; the second call sends nothing and says when the
    entry was stored."""
    exports = replay_fixture("GATSData_GetUNTradeExportDataReleaseInfo", "all")
    imports = replay_fixture("GATSData_GetUNTradeImportDataReleaseInfo", "all")
    replay_fixture("GATSData_GetCensusExportDataReleaseInfo", "all")
    first, _ = await api.GATSData_GetUNTradeExportDataReleaseInfo()
    await api.GATSData_GetUNTradeImportDataReleaseInfo()
    await api.GATSData_GetCensusExportDataReleaseInfo()
    assert (exports.call_count, imports.call_count) == (1, 1), "both from the wire"
    assert (len(release_dates_cache), len(commodities_cache)) == (3, 0)
    for path in (UN_EXPORT_RELEASES, UN_IMPORT_RELEASES):
        key = cache_key("GET", httpx.URL(f"{BASE_URL}{path}"))
        assert release_dates_cache.get(key) is not None, path
        assert commodities_cache.get(key) is None, path
    entry = cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{UN_EXPORT_RELEASES}")))
    assert entry is not None
    again, stored = await api.GATSData_GetUNTradeExportDataReleaseInfo()
    assert stored == datetime.fromtimestamp(entry.stored_at, UTC)
    assert again == first
    assert (exports.call_count, imports.call_count) == (1, 1)
    assert sent_urls(exports) == [f"{BASE_URL}{UN_EXPORT_RELEASES}"]
    assert sent_urls(imports) == [f"{BASE_URL}{UN_IMPORT_RELEASES}"]


@pytest.mark.anyio
async def test_un_trade_data_is_never_cached(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("GATSData_GetUNTradeReExports", "MC_2019")
    await api.GATSData_GetUNTradeReExports("MC", "2019")
    await api.GATSData_GetUNTradeReExports("MC", "2019")
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
    cached, _ = await api.GATSData_GetCensusExportDataReleaseInfo()
    assert cached == first
    assert releases.call_count == 1, "answered from the cache"
    countries = respx_mock.get(f"{BASE_URL}/api/gats/countries")
    with pytest.raises(RateLimitError, match="nothing was sent"):
        await api.GATSData_GetCountries()
    assert (spent.call_count, countries.call_count) == (1, 0)
