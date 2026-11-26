"""The client's wiring and its cache, and the shared package's api.data.gov gateway on it.

Recorded answers come from ``tests/fixtures``: the invalid-key answer
(``get_regions/invalid_key.json``, sent with a made-up key on 2026-10-25) and the
quota headers of the keyed answers. GATS has no recorded 429: the gateway's 429 is built in
the shape api.data.gov documents and sdk-usda-psd recorded (its
``PSDData_GetCommodities/over_rate_limit.json``, 2026-10-23), and every such test says so.
The gateway and its quota policy are the shared package's (``xippios.usda.fas``'s
``Gateway``, sdk-core ADR-0032, sdk-core ADR-0037), whose tests hold its answers, the key's
codes, the policy's headers and window, a 429 classified on its own and core's retries of a
429; this module checks that the package installs them, that the policy reads a 429 through
the package's client, that GATS's own answers fall through ``classify``, and which answers
the cache keeps and for how long.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from xippios.core import (
    AuthError,
    MemoryCache,
    RateLimitError,
    ValidationError,
)
from xippios.core.client import CachedResponse, cache_key
from xippios.core.testing import (
    CLOCK_SLACK,
    ReplayFixture,
    assert_time_between,
    load_fixture,
    response_from_fixture,
    sent_urls,
)
from xippios.usda.fas import API_KEY_ENV, Gateway

from xippios.usda.gats import api
from xippios.usda.gats._client import (
    BASE_URL,
    CACHE_MAX_BYTES,
    COMMODITIES_PATH,
    COMMODITIES_TTL,
    DEFAULT_TTL,
    LIFETIMES,
    RATE_LIMIT,
    RELEASE_DATES_PATHS,
    RELEASE_DATES_TTL,
    SOURCE,
    UN_TRADE_PATH,
    UN_TRADE_TTL,
    auth,
    cache,
    classify,
    client,
    config,
    gateway,
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
    """NOT RECORDED as such: an answer in the shape api.data.gov documents and sends.
    It is composed from what the gateway documents (conventions §10, kind 2).
    """
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
"""NOT RECORDED here: the 429 body sdk-usda-psd recorded from the same gateway
(conventions §10, kind 2)."""
SPENT = {"Retry-After": "3151", "x-ratelimit-limit": "1000", "x-ratelimit-remaining": "0"}
"""NOT RECORDED here: the quota headers of sdk-usda-psd's recorded 429 (conventions §10,
kind 2)."""


def test_the_client_is_wired_for_the_gateway() -> None:
    """One request per second, gats's classify, and the shared package's gateway installed: its
    key auth and its one quota policy per process for the shared key, whose headers and window
    the shared package's tests hold (sdk-core ADR-0032, sdk-core ADR-0037). The gateway is built
    with no data path, since GATS answers a month or a year without data with ``[]`` and never
    with FAS's empty 404, so it maps no answer of GATS's to ``NoDataForYear``."""
    assert (RATE_LIMIT.per_minute, RATE_LIMIT.capacity) == (60, 1)
    assert config.rate_limit is RATE_LIMIT
    assert config.classify is classify
    assert client.config is config
    assert config.base_url == BASE_URL == "https://api.fas.usda.gov"
    assert gateway.source == SOURCE == "usda-gats"
    assert gateway.data_path is None, "no data path: GATS never answers FAS's empty 404"
    assert gateway.policy is Gateway.policy, "one policy per process for the shared key"
    assert config.observe == Gateway.policy.observe, "installed: every answer reaches it"
    assert config.before_request == Gateway.policy.before_request
    assert auth is gateway.auth
    assert (auth.location, auth.name) == ("header", "X-Api-Key")
    assert auth.env_var == API_KEY_ENV == "DATA_GOV_API_KEY"  # pragma: allowlist secret


def test_the_client_asks_for_json() -> None:
    """The snapshot's operations produce JSON and XML; httpx alone sends ``Accept: */*``."""
    assert config.headers == {"Accept": "application/json"}


@pytest.mark.parametrize(
    ("endpoint", "case", "remaining"),
    [
        ("get_countries", "all", "969"),
        ("get_census_exports", "CH_2026_8", "966"),
        ("get_census_exports", "unknown_partner", "965"),
        ("get_census_exports", "month_13", "964"),
        ("get_census_import", "CH_2026_8", "965"),
        ("get_un_trade_export_data_release_info", "all", "992"),
        ("get_un_trade_exports", "IC_2019", "991"),
        ("get_un_trade_exports", "year_text", "985"),
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


def test_the_recorded_invalid_key_answer_is_the_documented_shape() -> None:
    """The bad-key answer carries api.data.gov's error object and no quota headers: the
    gateway refuses it before counting."""
    response = recorded("get_regions", "invalid_key")
    body = json.loads(response.text)
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert "x-ratelimit-remaining" not in response.headers
    assert "x-ratelimit-limit" not in response.headers


@pytest.mark.anyio
async def test_a_call_raises_auth_error_on_the_recorded_invalid_key(
    replay_fixture: ReplayFixture, placeholder_api_key: str
) -> None:
    route = replay_fixture("get_regions", "invalid_key")
    with pytest.raises(AuthError, match="API_KEY_INVALID") as info:
        await client.get_answer(REGIONS)
    assert placeholder_api_key not in str(info.value)
    assert route.call_count == 1, "a 403 is never retried"
    assert sent_urls(route) == [f"{BASE_URL}{REGIONS}"]


def test_an_empty_404_falls_through_to_core() -> None:
    """The recorded month-0 answer: no gateway code, so ``classify`` leaves it to core."""
    response = recorded("get_census_exports", "month_0")
    assert (response.status_code, response.content) == (404, b"")
    assert classify(response) is None


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_the_policy_reads_a_429_through_core(respx_mock: respx.MockRouter) -> None:
    """NOT RECORDED here: psd's recorded 429 mocked on a GATS path, in the shape the gateway
    documents (conventions §10, kind 2), through the package's client. Core's
    ``observe`` marks the gateway's quota spent until its ``Retry-After``, ``classify``
    raises after one request (3151 s is beyond ``backoff_max``) with the snapshot's wait
    from now, and the next request is refused before it is sent, in the gateway's name.
    Marked ``rate_limited``: the refusal is the policy's pause, which the plugin turns
    off."""
    route = respx_mock.get(f"{BASE_URL}/api/gats/countries").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=SPENT)
    )
    with pytest.raises(RateLimitError) as info:
        await api.get_countries()
    slack = CLOCK_SLACK.total_seconds()
    assert info.value.retry_after is not None
    assert 3151 - slack <= info.value.retry_after <= 3151 + slack, "the snapshot's wait from now"
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
        await api.get_census_export_data_release_info()
    assert refused.value.message.startswith("quota spent (")
    assert API_KEY_ENV not in refused.value.message, "core's subject names no key's variable"
    assert refused.value.source == "api.data.gov"
    assert refused.value.retry_after is not None
    assert 3151 - slack <= refused.value.retry_after <= 3151 + slack
    assert route.call_count == 1
    assert releases.call_count == 0


def test_the_client_caches_every_answer_with_a_lifetime_per_prefix() -> None:
    """Core's one cache with a lifetime per path prefix keeps every answer, by the
    maintainer's decision of 2026-11-26 (sdk-core ADR-0040, decision 3; ADR-0061, decision
    11): core's default of 300 seconds for every path, the two Census release-date paths for
    an hour, every UN Trade path, its data and its two release lists, for a day, the feed
    being frozen, and the commodities path for a day. A body of up to 16 MiB is stored,
    twice core's default."""
    assert config.cache is cache
    assert isinstance(cache, MemoryCache)
    assert config.cache_max_bytes == CACHE_MAX_BYTES == 16 * 1024 * 1024
    assert (DEFAULT_TTL, RELEASE_DATES_TTL, UN_TRADE_TTL, COMMODITIES_TTL) == (
        300.0,
        3600.0,
        86400.0,
        86400.0,
    )
    assert {EXPORT_RELEASES, IMPORT_RELEASES} == RELEASE_DATES_PATHS
    assert UN_TRADE_PATH == "/api/gats/UNTrade"
    assert all(path.startswith(UN_TRADE_PATH) for path in (UN_EXPORT_RELEASES, *UN_DATA))
    assert COMMODITIES_PATH == "/api/gats/commodities"
    assert (
        dict(cache.lifetimes)
        == dict(LIFETIMES)
        == {
            "/": DEFAULT_TTL,
            EXPORT_RELEASES: RELEASE_DATES_TTL,
            IMPORT_RELEASES: RELEASE_DATES_TTL,
            UN_TRADE_PATH: UN_TRADE_TTL,
            COMMODITIES_PATH: COMMODITIES_TTL,
        }
    )


CENSUS_DATA = [
    "/api/gats/censusExports/partnerCode/CH/year/2026/month/8",
    "/api/gats/censusImports/partnerCode/CH/year/2026/month/8",
    "/api/gats/customsDistrictExports/partnerCode/IC/year/2026/month/8",
]
"""Census data paths, which core's default keeps for 300 seconds."""

UN_DATA = [
    "/api/gats/UNTradeExports/reporterCode/IC/year/2019",
    "/api/gats/UNTradeImports/reporterCode/TP/year/2019",
    "/api/gats/UNTradeReExports/reporterCode/MC/year/2019",
]
"""UN Trade data paths, which ``UN_TRADE_PATH`` keeps for a day."""


def _entry(stored_at: float) -> CachedResponse:
    """A body that no route serves: an entry for the cache alone, an input of the test."""
    return CachedResponse(status=200, headers=(), content=b"[]", stored_at=stored_at)


def test_each_path_keeps_its_own_lifetime() -> None:
    """``LIFETIMES`` in a ``MemoryCache`` with a clock of its own: every path is stored. Ten
    minutes on, the Census data and the packaged lists' paths have expired, core's 300
    seconds; two hours on, the Census release list's entry too, while the UN Trade answers
    and the commodities entry still answer; past a day, they have expired too."""
    now = [1_000_000.0]
    store = MemoryCache(lifetimes=LIFETIMES, clock=lambda: now[0])
    other = [*CENSUS_DATA, "/api/gats/countries", "/api/gats/HS6Commodities", REGIONS]
    daily = [UN_EXPORT_RELEASES, *UN_DATA, COMMODITIES_PATH]
    keys = {
        path: cache_key("GET", httpx.URL(f"{BASE_URL}{path}"))
        for path in (EXPORT_RELEASES, *daily, *other)
    }
    for path, key in keys.items():
        store.set(key, _entry(now[0]), path=path)
    assert len(store) == len(keys), "every path is stored"
    now[0] += 600
    assert [path for path in other if store.get(keys[path]) is not None] == []
    assert store.get(keys[EXPORT_RELEASES]) is not None, "an hour has not passed"
    now[0] += 2 * 3600
    assert store.get(keys[EXPORT_RELEASES]) is None, "an hour has passed"
    assert [path for path in daily if store.get(keys[path]) is None] == [], "a day has not"
    now[0] += 86400.0
    assert [path for path in daily if store.get(keys[path]) is not None] == []


@pytest.mark.anyio
async def test_the_commodities_list_lands_in_the_daily_cache(
    replay_fixture: ReplayFixture,
) -> None:
    """Through the real client: the commodities answer and a release list are stored, and
    the second commodities call sends nothing and carries the entry's stored time."""
    commodities = replay_fixture("get_commodities", "all")
    replay_fixture("get_census_export_data_release_info", "all")
    first = (await api.get_commodities()).payload
    await api.get_census_export_data_release_info()
    assert len(cache) == 2, "the commodities list and the release list"
    entry = cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{COMMODITIES_PATH}")))
    assert entry is not None
    answer = await api.get_commodities()
    again, retrieved_at = answer.payload, answer.retrieved_at
    assert retrieved_at == datetime.fromtimestamp(entry.stored_at, UTC)
    assert len(again) == len(first) == 24936
    assert commodities.call_count == 1
    assert sent_urls(commodities) == [f"{BASE_URL}{COMMODITIES_PATH}"]


def test_the_recorded_hs10_list_fits_the_cache_bound_with_room() -> None:
    """sdk-core ADR-0040, decision 3: core's default bound, 8 MiB, would leave the recorded HS10
    list less than 10 % of room, so the package raises it to 16 MiB. The recorded body,
    as ``httpx`` gives the client its bytes, must stay under three quarters of the bound:
    a re-recording that grew towards it fails here, before the day's cache silently stops
    storing the list."""
    body = load_fixture(FIXTURES / "get_commodities" / "all.json").response.body
    assert isinstance(body, str)
    size = len(body.encode("utf-8"))
    assert size <= CACHE_MAX_BYTES * 3 // 4, f"{size} bytes, past 75 % of {CACHE_MAX_BYTES}"


@pytest.mark.anyio
async def test_a_release_list_is_fetched_once_and_then_answered_from_the_cache(
    replay_fixture: ReplayFixture,
) -> None:
    """The first call says when the answer arrived, the second sends nothing and says when
    the entry was stored, for ``meta.retrieved_at`` (conventions §4, ``get_answer``); each
    flow's list is an entry of its own."""
    exports = replay_fixture("get_census_export_data_release_info", "all")
    imports = replay_fixture("get_census_import_data_release_info", "all")
    before = datetime.now(UTC)
    answer = await api.get_census_export_data_release_info()
    first, first_at = answer.payload, answer.retrieved_at
    assert_time_between(first_at, before, datetime.now(UTC))
    assert exports.call_count == 1, "the first answer came from the wire"
    entry = cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{EXPORT_RELEASES}")))
    assert entry is not None
    answer = await api.get_census_export_data_release_info()
    again, stored = answer.payload, answer.retrieved_at
    assert stored == datetime.fromtimestamp(entry.stored_at, UTC), "when it was stored"
    assert stored.tzinfo is UTC
    assert again == first
    assert exports.call_count == 1
    assert sent_urls(exports) == [f"{BASE_URL}{EXPORT_RELEASES}"]
    await api.get_census_import_data_release_info()
    assert imports.call_count == 1, "the imports list is not the exports list's entry"


RELEASE_WRAPPERS = [
    ("get_census_export_data_release_info", "/api/gats/census/data/exports/dataReleaseDates"),
    ("get_census_import_data_release_info", "/api/gats/census/data/imports/dataReleaseDates"),
    ("get_un_trade_export_data_release_info", "/api/gats/UNTrade/data/exports/dataReleaseDates"),
    ("get_un_trade_import_data_release_info", "/api/gats/UNTrade/data/imports/dataReleaseDates"),
]
"""The four release-list wrappers and their paths, cached for an hour or a day."""


@pytest.mark.anyio
@pytest.mark.parametrize(("wrapper", "path"), RELEASE_WRAPPERS)
async def test_a_release_list_that_fails_the_models_is_asked_again(
    respx_mock: respx.MockRouter, wrapper: str, path: str
) -> None:
    """NOT RECORDED: a 200 of JSON that is no list of releases, a body of no shape GATS
    sends, to show what the cache does with it (conventions §10, kind 5). The wrapper parses
    through ``get_answer``, which stores an answer only once it parsed, so the next call
    asks upstream again, where the cache answered the same error without a request until
    its entry expired (https://github.com/xippios/sdk-core/issues/122)."""
    route = respx_mock.get(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json={"message": "maintenance"})
    )
    for _ in range(2):
        with pytest.raises(ValidationError, match="Input should be a valid list"):
            await getattr(api, wrapper)()
    assert route.call_count == 2
    assert cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{path}"))) is None


@pytest.mark.anyio
async def test_census_data_is_cached_for_five_minutes(replay_fixture: ReplayFixture) -> None:
    """A Census month is one entry for core's default of 300 seconds: the second read sends
    nothing and says when the entry was stored (conventions §4)."""
    route = replay_fixture("get_census_exports", "CH_2026_8")
    first = await api.get_census_exports("CH", 2026, 8)
    again = await api.get_census_exports("CH", 2026, 8)
    assert route.call_count == 1
    assert len(cache) == 1
    entry = cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{CENSUS_DATA[0]}")))
    assert entry is not None
    assert again.retrieved_at == datetime.fromtimestamp(entry.stored_at, UTC)
    assert again.payload == first.payload


@pytest.mark.anyio
async def test_the_un_release_lists_are_stored_once_each(
    replay_fixture: ReplayFixture,
) -> None:
    """Through the real client: each UN Trade list is an entry of its own, beside the Census
    list's; the second call sends nothing and says when the entry was stored."""
    exports = replay_fixture("get_un_trade_export_data_release_info", "all")
    imports = replay_fixture("get_un_trade_import_data_release_info", "all")
    replay_fixture("get_census_export_data_release_info", "all")
    first = (await api.get_un_trade_export_data_release_info()).payload
    await api.get_un_trade_import_data_release_info()
    await api.get_census_export_data_release_info()
    assert (exports.call_count, imports.call_count) == (1, 1), "both from the wire"
    assert len(cache) == 3
    entry = cache.get(cache_key("GET", httpx.URL(f"{BASE_URL}{UN_EXPORT_RELEASES}")))
    assert entry is not None
    answer = await api.get_un_trade_export_data_release_info()
    again, stored = answer.payload, answer.retrieved_at
    assert stored == datetime.fromtimestamp(entry.stored_at, UTC)
    assert again == first
    assert (exports.call_count, imports.call_count) == (1, 1)
    assert sent_urls(exports) == [f"{BASE_URL}{UN_EXPORT_RELEASES}"]
    assert sent_urls(imports) == [f"{BASE_URL}{UN_IMPORT_RELEASES}"]


@pytest.mark.anyio
async def test_un_trade_data_is_cached_for_a_day(replay_fixture: ReplayFixture) -> None:
    """A UN Trade reporter-year is one entry under ``UN_TRADE_PATH``, kept for a day: the
    second read sends nothing."""
    route = replay_fixture("get_un_trade_re_exports", "MC_2019")
    await api.get_un_trade_re_exports("MC", "2019")
    await api.get_un_trade_re_exports("MC", "2019")
    assert route.call_count == 1
    assert len(cache) == 1


@pytest.mark.anyio
@pytest.mark.rate_limited
async def test_a_cached_release_list_answers_while_the_quota_is_spent(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    """NOT RECORDED here: psd's recorded 429 mocked on a GATS path, in the shape the gateway
    documents (conventions §10, kind 2), spends the quota; the
    release list cached before it still answers, since a cache hit returns before the
    quota policy's check (sdk-core ADR-0037), while the uncached countries list is refused unsent.
    Marked ``rate_limited``: the refusal is the policy's pause, which the plugin turns off."""
    releases = replay_fixture("get_census_export_data_release_info", "all")
    first = (await api.get_census_export_data_release_info()).payload
    spent = respx_mock.get(f"{BASE_URL}{REGIONS}").mock(
        return_value=httpx.Response(429, json=OVER_RATE_LIMIT, headers=SPENT)
    )
    with pytest.raises(RateLimitError):
        await client.get_answer(REGIONS)
    cached = (await api.get_census_export_data_release_info()).payload
    assert cached == first
    assert releases.call_count == 1, "answered from the cache"
    countries = respx_mock.get(f"{BASE_URL}/api/gats/countries")
    with pytest.raises(RateLimitError, match="nothing was sent"):
        await api.get_countries()
    assert (spent.call_count, countries.call_count) == (1, 0)
