"""The configured ``xippios.core`` client for USDA FAS Global Agricultural Trade System.

One ``AsyncClient`` for the whole package, shared by the tasks, the sync facades and the
MCP server, on api.data.gov's gateway at ``BASE_URL`` with ``Accept: application/json``.
It keeps a pace of its own, ``RATE_LIMIT``, since the snapshot documents none. The key,
the gateway's documented answers and its hourly quota are ``xippios.core.data_gov``'s
(ADR-0009): ``gateway.auth`` sends the key from ``DATA_GOV_API_KEY`` in the
``X-Api-Key`` header; ``Gateway.policy``, one ``QuotaPolicy`` per process for the key,
keeps api.data.gov's hourly quota from every answer and never fires a request into a
spent one, waiting within the policy's ``pause_cap`` or refusing without sending
(ADR-0010, ADR-0015); and ``classify`` asks ``gateway.classify`` first, which maps the
gateway's ``API_KEY_*`` answers to ``AuthError``, its 429 to ``RateLimitError`` and its
``NOT_FOUND`` to ``NotFoundError``. ``x-ratelimit-limit: 1000`` and
``x-ratelimit-remaining`` are on every keyed GATS answer recorded on 2026-10-25, the
error answers to a valid key included; the gateway sends no reset header.

Core's response cache keeps five answers and nothing else (``cache``, ``cache_filter``,
``CACHED_PATHS``): the two Census release-date lists for an hour, since every Census data
task fetches its flow's list before the data and would otherwise cost two requests
against the hourly quota; the two UN Trade release-date lists for a day, since the UN
Trade feed is frozen (both lists end with statistical year 2019, last released on
2021-01-18, as recorded on 2026-10-26), so a UN task costs one keyed call per flow per day
for its list instead of one per hour; and the HS10 commodities list for a day, 7.6 MB that
``tasks.list_commodities`` fetches whole for every search. Core's ``MemoryCache`` has one
TTL, so ``cache`` is a ``CacheBackend`` of the package's own over three of them,
``PathCaches``. The cache stores a body of up to ``CACHE_MAX_BYTES``, 16 MiB, twice
core's default, so that the HS10 list stays cached when it grows (ADR-0019, decision 3).

GATS's own answers to an unknown partner, a month out of range or a month without data
are not mapped here: what they are is recorded under
``tests/fixtures/get_census_exports/`` and decided with the tasks.
"""

from collections.abc import Mapping
from types import MappingProxyType

import httpx
from xippios.core import (
    AsyncClient,
    ClientConfig,
    MemoryCache,
    RateLimit,
    XippiosError,
)
from xippios.core.client import CachedResponse, cache_key
from xippios.core.data_gov import API_KEY_ENV, Gateway

from xippios.usda.gats._version import __version__

SOURCE = "usda-gats"
BASE_URL = "https://api.fas.usda.gov"
"""The gateway's host root; every GATS path keeps its ``/api/gats/`` prefix, as the
snapshot's ``paths`` name it (the portal document's ``host`` is ``api.fas.usda.gov``, no
``basePath``)."""
# A self-imposed pace: upstream documents no per-second or per-minute limit (ADR-0010
# decision 1).
RATE_LIMIT = RateLimit(per_minute=60, burst=1)
"""One request per second, no burst: a pace of our own, since the snapshot documents none.

At this pace the gateway's 1,000 requests per hour, shared with every other package using
the same key, last about 17 minutes; past that ``Gateway.policy`` takes over.
"""

# api.data.gov's key, its documented answers and its hourly quota, kept by one policy per
# process that every source behind the gateway shares (ADR-0009).
gateway = Gateway(SOURCE)

RELEASE_DATES_PATHS: frozenset[str] = frozenset(
    {
        "/api/gats/census/data/exports/dataReleaseDates",
        "/api/gats/census/data/imports/dataReleaseDates",
    }
)
"""The two Census release-date lists, cached for ``RELEASE_DATES_TTL``, an hour.

Each Census data task (``tasks.get_census_exports`` and the five others) first fetches its
flow's list, ``GATSData_GetCensusExportDataReleaseInfo`` or
``GATSData_GetCensusImportDataReleaseInfo``, to check that the month is released, so
every task call would cost one extra request against api.data.gov's 1,000 per hour; from
the cache it costs one per flow per ``RELEASE_DATES_TTL``. The three series tasks
(``tasks.get_census_export_series`` and the two others) read the list once for all
their months. A list is one record per
statistical month and changes only when a month is released or revised: as recorded
(``tests/fixtures/get_census_export_data_release_info/all.json``), 2026-08 was
released on 2026-10-06 and 2026-07 on 2026-09-03, and the annual revision re-released
2023-01 to 2025-12 on 2026-06-24.
"""

UN_RELEASE_DATES_PATHS: frozenset[str] = frozenset(
    {
        "/api/gats/UNTrade/data/exports/dataReleaseDates",
        "/api/gats/UNTrade/data/imports/dataReleaseDates",
    }
)
"""The two UN Trade release-date lists, cached for ``UN_RELEASE_DATES_TTL``, a day.

``GATSData_GetUNTradeExportDataReleaseInfo`` and
``GATSData_GetUNTradeImportDataReleaseInfo`` are one record per reporter and statistical
year, about 400 KB of JSON each. Each UN Trade data task (``tasks.get_un_exports`` and
the two others) reads its flow's list before the data to check the reporter-year, and
``tasks.get_un_release_dates`` answers from it; from the cache a task costs one request
per flow per ``UN_RELEASE_DATES_TTL``. As recorded on 2026-10-26 both lists end with
statistical year 2019 and their newest release is dated 2021-01-18
(``tests/fixtures/get_un_trade_export_data_release_info/all.json``): the feed is frozen,
so a day's cache loses nothing an hour's would catch.
"""

COMMODITIES_PATH = "/api/gats/commodities"
"""``GATSData_GetCommodities``, the HS10 commodities list, cached for ``COMMODITIES_TTL``.

One answer of 24,936 records and about 7.6 MB of JSON, the largest in the family, which
``tasks.list_commodities`` fetches whole and filters itself; from the cache a search costs
no request for a day.
"""

CACHED_PATHS: frozenset[str] = RELEASE_DATES_PATHS | UN_RELEASE_DATES_PATHS | {COMMODITIES_PATH}
"""The only paths the client caches; the data answers, the countries list and every other
path are never cached."""

RELEASE_DATES_TTL = 3600.0
"""Seconds a cached Census release-date list answers: one hour.

Within that hour after a release the cached list can lag upstream: a task can refuse a
month Census has just released, as not released yet, until the entry expires. Its
``NotFoundError`` then says when the list was fetched.
"""

UN_RELEASE_DATES_TTL = 86400.0
"""Seconds a cached UN Trade release-date list answers: one day.

The UN Trade feed is frozen: as recorded on 2026-10-26 both lists end with statistical
year 2019, and their newest release is dated 2021-01-18, so nothing has been released
for years and an hour's cache would spend one keyed call per flow per hour for the same
answer; a day spends one per flow per day. Should GATS release a reporter-year after all,
a task can refuse it as not listed for up to a day, and its ``NotFoundError`` says when
the list was fetched.
"""

COMMODITIES_TTL = 86400.0
"""Seconds the cached HS10 commodities list answers: one day.

The list names codes, their start months and their units, which change with the HS
revisions and Census's schedule changes, not from hour to hour; a day keeps a code added
upstream out of a search for at most a day, and ``meta.retrieved_at`` says when the list
was fetched.
"""

CACHE_MAX_BYTES = 16 * 1024 * 1024
"""The largest body the client's cache stores, 16 MiB: ``ClientConfig.cache_max_bytes``.

Core's default is 8 MiB, and a source that caches a larger answer raises the bound and
says why (ADR-0019, decision 3). The HS10 commodities list was 7,592,916 bytes as
recorded on 2026-10-26 (``tests/fixtures/get_commodities/all.json``), 795,692 bytes
(9.5 %) under the default: a refresh upstream that grew it past 8 MiB would silently stop
the day's cache, and every ``tasks.list_commodities`` search would fetch the 7.6 MB again.
16 MiB leaves it room to double; the release-date lists, about 81 KB and 400 KB, are far
below either bound.
"""


# The package's own until core offers a TTL per path; one consumer, so it waits (queue row
# 39 (f); ADR-0023, decision 4).
class PathCaches:
    """Core's ``CacheBackend`` over one ``MemoryCache`` per path: a TTL per path.

    Core's ``MemoryCache`` keeps one TTL for every entry, and a client takes one backend
    (``ClientConfig.cache``); this backend routes each entry to the ``MemoryCache`` of its
    path. The client keys an entry by ``cache_key("GET", url)`` of the request as built
    from ``BASE_URL`` and the path (``CacheBackend``'s contract), so the keys of the
    paths named here are known in advance. A key of no path named here finds nothing and
    is dropped: ``cache_filter`` lets only ``CACHED_PATHS`` through, but a request to one
    of them with a query has a key of its own (``cache_key`` takes the query in), so it
    goes to the wire every time and is never stored.

    Args:
        caches: Path, as ``CACHED_PATHS`` names it, to the cache that keeps its answer,
            e.g. ``{"/api/gats/commodities": MemoryCache(ttl=86400.0, maxsize=1)}``.
    """

    def __init__(self, caches: Mapping[str, MemoryCache]) -> None:
        self._by_path = dict(caches)
        self._by_key = {
            cache_key("GET", httpx.URL(f"{BASE_URL}{path}")): store
            for path, store in self._by_path.items()
        }
        self._stores = tuple({id(store): store for store in self._by_key.values()}.values())

    @property
    def by_path(self) -> Mapping[str, MemoryCache]:
        """Path to the cache that keeps its answer, as given, as a read-only view.

        ``get``, ``set``, ``clear`` and ``len`` go by what was built from it once, so the
        view cannot change under them.
        """
        return MappingProxyType(self._by_path)

    def get(self, key: str) -> CachedResponse | None:
        """The live entry for ``key`` from its path's cache, or ``None``."""
        store = self._by_key.get(key)
        return None if store is None else store.get(key)

    def set(self, key: str, value: CachedResponse) -> None:
        """Store ``value`` in its path's cache; a key of no path named here is dropped."""
        store = self._by_key.get(key)
        if store is not None:
            store.set(key, value)

    def clear(self) -> None:
        """Drop every entry of every cache."""
        for store in self._stores:
            store.clear()

    def __len__(self) -> int:
        return sum(len(store) for store in self._stores)


release_dates_cache = MemoryCache(ttl=RELEASE_DATES_TTL, maxsize=2)
"""The Census release-date lists' cache: its two entries, about 81 KB of JSON each, kept
for an hour."""

un_release_dates_cache = MemoryCache(ttl=UN_RELEASE_DATES_TTL, maxsize=2)
"""The UN Trade release-date lists' cache: its two entries, about 400 KB of JSON each,
kept for a day."""

commodities_cache = MemoryCache(ttl=COMMODITIES_TTL, maxsize=1)
"""The HS10 commodities list's cache: its one entry, about 7.6 MB, kept for a day."""

cache = PathCaches(
    {
        **dict.fromkeys(sorted(RELEASE_DATES_PATHS), release_dates_cache),
        **dict.fromkeys(sorted(UN_RELEASE_DATES_PATHS), un_release_dates_cache),
        COMMODITIES_PATH: commodities_cache,
    }
)
"""Core's response cache, shared by every caller of ``client`` in the process.

Only HTTP 200 answers of up to ``CACHE_MAX_BYTES`` are stored, and only for
``CACHED_PATHS`` (``cache_filter``): the Census release-date lists for an hour, the UN
Trade release-date lists and the commodities list for a day. A hit sends nothing, so the
rate limiter and the quota policy never see it (ADR-0015).
"""


def cache_filter(request: httpx.Request) -> bool:
    """Whether the client caches ``request``: only a GET of one of ``CACHED_PATHS``.

    ``ClientConfig.cache_filter`` (ADR-0015) lets one client cache a few paths and
    nothing else; core asks it with the request as built, before credentials apply, and
    caches GETs only.
    """
    return request.url.path in CACHED_PATHS


def classify(response: httpx.Response) -> XippiosError | None:
    """Upstream's documented error shapes as taxonomy errors, else ``None`` (conventions §6).

    The ``ClientConfig.classify`` hook: it sees every response before core's status mapping.
    The gateway's answers come first, mapped by ``gateway.classify``: an ``API_KEY_*`` 401
    or 403 (recorded: ``get_regions/invalid_key.json``), the 429 and the
    ``NOT_FOUND`` 404. GATS has no answers of its own to map here: everything else falls
    through to core's status mapping, GATS's own answers to the Census data paths
    included (``tests/fixtures/get_census_exports/``), which the tasks decide.
    """
    error = gateway.classify(response)
    if error is not None:
        return error
    return None


config = gateway.install(
    ClientConfig(
        source=SOURCE,
        version=__version__,
        base_url=BASE_URL,
        rate_limit=RATE_LIMIT,
        cache=cache,
        cache_filter=cache_filter,
        cache_max_bytes=CACHE_MAX_BYTES,
        headers={"Accept": "application/json"},
        classify=classify,
    )
)
# The key is read from the environment on the first request, never at import.
auth = gateway.auth
client = AsyncClient(config, auth=auth)


__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "CACHED_PATHS",
    "CACHE_MAX_BYTES",
    "COMMODITIES_PATH",
    "COMMODITIES_TTL",
    "RATE_LIMIT",
    "RELEASE_DATES_PATHS",
    "RELEASE_DATES_TTL",
    "SOURCE",
    "UN_RELEASE_DATES_PATHS",
    "UN_RELEASE_DATES_TTL",
    "PathCaches",
    "auth",
    "cache",
    "cache_filter",
    "classify",
    "client",
    "commodities_cache",
    "config",
    "gateway",
    "release_dates_cache",
    "un_release_dates_cache",
]
