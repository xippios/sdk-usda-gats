"""The configured ``xippios.core`` client for USDA FAS Global Agricultural Trade System.

One ``AsyncClient`` for the whole package, shared by the tasks, the sync facades and the
MCP server, on api.data.gov's gateway at ``BASE_URL`` with the key in the ``X-Api-Key``
header and ``Accept: application/json``. It keeps a pace of its own, ``RATE_LIMIT``,
since the snapshot documents none; core's ``QuotaPolicy``, ``policy``, keeps
api.data.gov's hourly quota from every answer and never fires a request into a spent
one, waiting within ``RetryPolicy.backoff_max`` or refusing without sending (ADR-0010,
ADR-0015); and ``classify`` maps the gateway's ``API_KEY_*`` answers to ``AuthError``,
its 429 to ``RateLimitError`` and its ``NOT_FOUND`` to ``NotFoundError``.

Core's response cache keeps five answers and nothing else (``cache``, ``cache_filter``,
``CACHED_PATHS``): the Census and UN Trade release-date lists for an hour, since every
Census data task fetches its flow's list before the data and would otherwise cost two
requests against the hourly quota, and the HS10 commodities list for a day, 7.6 MB that
``tasks.list_commodities`` fetches whole for every search. Core's ``MemoryCache`` has one
TTL, so ``cache`` is a ``CacheBackend`` of the package's own over two of them,
``PathCaches``.

The gateway handling here (``HeaderKeyAuth("X-Api-Key", ...)``, the ``QuotaPolicy`` on
``x-ratelimit-*``, the ``API_KEY_*``, ``OVER_RATE_LIMIT`` and ``NOT_FOUND`` mappings with
host-free messages) is copied from sdk-usda-psd's adopted client, the shape sdk-usda-esr
copies too. It is the family-review C14 candidate for a shared api.data.gov gateway
module in core (conventions §15 item 4); until core provides one, these lines stay a
copy and are not extended. GATS's own answers to an unknown partner, a month out of range
or a month without data are not mapped here: what they are is recorded under
``tests/fixtures/GATSData_GetCensusExports/`` and decided with the tasks.
"""

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

import httpx
from xippios.core import (
    AsyncClient,
    AuthError,
    ClientConfig,
    HeaderKeyAuth,
    MemoryCache,
    NotFoundError,
    QuotaPolicy,
    RateLimit,
    RateLimitError,
    XippiosError,
)
from xippios.core.client import CachedResponse, cache_key
from xippios.core.errors import parse_retry_after

from xippios.usda.gats._version import __version__

SOURCE = "usda-gats"
BASE_URL = "https://api.fas.usda.gov"
"""The gateway's host root; every GATS path keeps its ``/api/gats/`` prefix, as the
snapshot's ``paths`` name it (the portal document's ``host`` is ``api.fas.usda.gov``, no
``basePath``)."""
API_KEY_ENV = "DATA_GOV_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
# A self-imposed pace: upstream documents no limit (ADR-0010 decision 1).
RATE_LIMIT = RateLimit(per_minute=60, burst=1)
"""One request per second, no burst: a pace of our own, since the snapshot documents none.

At this pace the gateway's 1,000 requests per hour, shared with every other package using
the same key, last about 17 minutes; past that the quota policy takes over.
"""

policy = QuotaPolicy(
    window=3600.0,
    source=SOURCE,
    limit_header="x-ratelimit-limit",
    remaining_header="x-ratelimit-remaining",
)
"""api.data.gov's quota for the key, kept by core from every answer from the wire.

``x-ratelimit-limit: 1000`` and ``x-ratelimit-remaining`` count requests per rolling hour
per key, not a pace: they are on every keyed GATS answer recorded on 2026-10-25, the
error answers to a valid key included, and they are the quota api.data.gov documents
(https://api.data.gov/docs/developer-manual/), shared by every package and process using
the same ``DATA_GOV_API_KEY`` (ADR-0009). The gateway sends no reset header: a spent
quota comes back after a 429's ``Retry-After``, else after ``window``, one hour, from the
developer manual: "The block will automatically be lifted by waiting an hour".
``policy.snapshot()`` reads the quota as the last answer reported it.
"""

RELEASE_DATES_PATHS: frozenset[str] = frozenset(
    {
        "/api/gats/census/data/exports/dataReleaseDates",
        "/api/gats/census/data/imports/dataReleaseDates",
        "/api/gats/UNTrade/data/exports/dataReleaseDates",
        "/api/gats/UNTrade/data/imports/dataReleaseDates",
    }
)
"""The Census and UN Trade release-date lists, cached for ``RELEASE_DATES_TTL``.

Each Census data task (``tasks.get_census_exports`` and the five others) first fetches its
flow's list, ``GATSData_GetCensusExportDataReleaseInfo`` or
``GATSData_GetCensusImportDataReleaseInfo``, to check that the month is released, so
every task call would cost one extra request against api.data.gov's 1,000 per hour; from
the cache it costs one per flow per ``RELEASE_DATES_TTL``. The three series tasks
(``tasks.get_census_export_series`` and the two others) read the list once for all
their months. A list is one record per
statistical month and changes only when a month is released or revised: as recorded
(``tests/fixtures/GATSData_GetCensusExportDataReleaseInfo/all.json``), 2026-08 was
released on 2026-10-06 and 2026-07 on 2026-09-03, and the annual revision re-released
2023-01 to 2025-12 on 2026-06-24.

The UN Trade lists, ``GATSData_GetUNTradeExportDataReleaseInfo`` and
``GATSData_GetUNTradeImportDataReleaseInfo``, are one record per reporter and statistical
year, about 400 KB of JSON each, and as recorded on 2026-10-26 they end with 2019, last
released on 2021-01-18
(``tests/fixtures/GATSData_GetUNTradeExportDataReleaseInfo/all.json``); they are cached
alike, so that a task that reads one before the data costs one request per flow per
``RELEASE_DATES_TTL`` too.
"""

COMMODITIES_PATH = "/api/gats/commodities"
"""``GATSData_GetCommodities``, the HS10 commodities list, cached for ``COMMODITIES_TTL``.

One answer of 24,936 records and about 7.6 MB of JSON, the largest in the family, which
``tasks.list_commodities`` fetches whole and filters itself; from the cache a search costs
no request for a day.
"""

CACHED_PATHS: frozenset[str] = RELEASE_DATES_PATHS | {COMMODITIES_PATH}
"""The only paths the client caches; the data answers, the countries list and every other
path are never cached."""

RELEASE_DATES_TTL = 3600.0
"""Seconds a cached release-date list answers: one hour.

Within that hour after a release the cached list can lag upstream: a task can refuse a
month Census has just released, as not released yet, until the entry expires. Its
``NotFoundError`` then says when the list was fetched.
"""

COMMODITIES_TTL = 86400.0
"""Seconds the cached HS10 commodities list answers: one day.

The list names codes, their start months and their units, which change with the HS
revisions and Census's schedule changes, not from hour to hour; a day keeps a code added
upstream out of a search for at most a day, and ``meta.retrieved_at`` says when the list
was fetched.
"""


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


release_dates_cache = MemoryCache(ttl=RELEASE_DATES_TTL, maxsize=8)
"""The release-date lists' cache: four entries, the Census lists of about 81 KB of JSON
each and the UN Trade lists of about 400 KB, so eight are plenty."""

commodities_cache = MemoryCache(ttl=COMMODITIES_TTL, maxsize=1)
"""The HS10 commodities list's cache: its one entry, about 7.6 MB, kept for a day."""

cache = PathCaches(
    {
        **dict.fromkeys(sorted(RELEASE_DATES_PATHS), release_dates_cache),
        COMMODITIES_PATH: commodities_cache,
    }
)
"""Core's response cache, shared by every caller of ``client`` in the process.

Only HTTP 200 answers are stored, and only for ``CACHED_PATHS`` (``cache_filter``): the
release-date lists for an hour, the commodities list for a day. A hit sends nothing, so
the rate limiter and the quota policy never see it (ADR-0015).
"""


def cache_filter(request: httpx.Request) -> bool:
    """Whether the client caches ``request``: only a GET of one of ``CACHED_PATHS``.

    ``ClientConfig.cache_filter`` (ADR-0015) lets one client cache a few paths and
    nothing else; core asks it with the request as built, before credentials apply, and
    caches GETs only.
    """
    return request.url.path in CACHED_PATHS


def stored_at(response: httpx.Response) -> datetime | None:
    """When the cache stored ``response``, as UTC; ``None`` for an answer from the wire.

    Core marks a hit with ``extensions["xippios_cache_stored_at"]``, epoch seconds; on a
    hit a task's ``meta.retrieved_at`` is that time, not the time of the call
    (conventions §4).
    """
    stamp = response.extensions.get("xippios_cache_stored_at")
    return None if stamp is None else datetime.fromtimestamp(stamp, UTC)


_URL = re.compile(r"https?://[^/\s]+")


def _gateway_error(response: httpx.Response) -> tuple[str | None, str]:
    """api.data.gov's ``{"error": {"code": ..., "message": ...}}``, or ``(None, "")``.

    The message comes back host-free (conventions §5): the gateway ends its messages with
    its URL (``"Get one at https://api.fas.usda.gov:443"``), written ``<host>`` here.
    """
    try:
        payload = response.json()
    except ValueError:
        return None, ""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return None, ""
    message = error.get("message")
    return error["code"], _URL.sub("<host>", message) if isinstance(message, str) else ""


def _over_rate_limit(response: httpx.Response) -> RateLimitError:
    """The gateway's 429, ``retry_after`` as long as the policy keeps the quota spent.

    Core's ``observe`` has read this answer before ``classify`` runs, so
    ``policy.snapshot()`` describes it; called on its own, without the client, there may be
    no snapshot, and the message says how long instead.
    """
    code, message = _gateway_error(response)
    upstream = ": ".join(part for part in (code, message) if part)
    named = parse_retry_after(response.headers.get("Retry-After"))
    wait = policy.window if named is None else min(named, policy.window)
    snapshot = policy.snapshot()
    allowance = (
        f"{snapshot.limit} requests per rolling hour per key"
        if snapshot is not None and snapshot.limit is not None
        else "an hourly quota per key"
    )
    state = (
        f"Quota: {snapshot.describe()}."
        if snapshot is not None
        else f"The quota is expected back in {wait:.0f} s."
    )
    bound = config.retry.backoff_max
    retried = (
        f" Nothing was retried: that is longer than a call waits ({bound:g} s)."
        if wait > bound
        else ""
    )
    return RateLimitError(
        f"api.data.gov rate limit reached for the key in {API_KEY_ENV} "
        f"(HTTP 429{' ' + upstream if upstream else ''}). The gateway allows {allowance}, "
        f"shared by every package using that key. {state}{retried}",
        retry_after=wait,
        source=SOURCE,
    )


def classify(response: httpx.Response) -> XippiosError | None:
    """The gateway's documented error shapes, mapped once (ADR-0008).

    - 401/403 with an api.data.gov ``error.code`` starting ``API_KEY_`` (developer manual:
      ``API_KEY_MISSING``, ``API_KEY_INVALID``, ``API_KEY_DISABLED``,
      ``API_KEY_UNAUTHORIZED``, ``API_KEY_UNVERIFIED``) is ``AuthError`` naming the code
      and the variable, never the key. Recorded: ``API_KEY_INVALID``
      (``GATSData_GetRegions/invalid_key.json``).
    - 429 (``OVER_RATE_LIMIT``) is ``RateLimitError`` with ``retry_after`` from
      ``Retry-After``, else the policy's ``window`` (3600 s): as long as ``policy`` keeps
      the quota spent. Not recorded here; sdk-usda-psd recorded the gateway's 429 on
      2026-10-23 (``Retry-After: 3151``, ``x-ratelimit-remaining: 0``, body
      ``{"error": {"code": "OVER_RATE_LIMIT", "message": "You have exceeded your rate
      limit. ..."}}``). Core asks ``classify`` before it retries, so a wait beyond
      ``RetryPolicy.backoff_max`` is raised after one request, and the message describes
      ``policy.snapshot()``.
    - 404 with ``error.code`` ``NOT_FOUND`` is the gateway's: no such path.

    Everything else falls through to core's status mapping, GATS's own answers to the
    Census data paths included (``tests/fixtures/GATSData_GetCensusExports/``). Messages
    name the path, never the host.
    """
    status = response.status_code
    if status in (401, 403):
        code, message = _gateway_error(response)
        if code is not None and code.startswith("API_KEY_"):
            return AuthError(
                f"api.data.gov refused the key in {API_KEY_ENV} (HTTP {status} {code}: "
                f"{message}). Check that the variable holds a valid, active api.data.gov key.",
                status=status,
                source=SOURCE,
            )
    if status == 429:
        return _over_rate_limit(response)
    if status == 404:
        code, message = _gateway_error(response)
        if code == "NOT_FOUND":
            return NotFoundError(
                f"api.data.gov has no route for {response.request.url.path} "
                f"(HTTP 404 NOT_FOUND: {message})",
                source=SOURCE,
            )
    return None


config = policy.install(
    ClientConfig(
        source=SOURCE,
        version=__version__,
        base_url=BASE_URL,
        rate_limit=RATE_LIMIT,
        cache=cache,
        cache_filter=cache_filter,
        headers={"Accept": "application/json"},
        classify=classify,
    )
)
# The key is read from the environment on the first request, never at import.
auth = HeaderKeyAuth("X-Api-Key", API_KEY_ENV, source=SOURCE)
client = AsyncClient(config, auth=auth)


__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "CACHED_PATHS",
    "COMMODITIES_PATH",
    "COMMODITIES_TTL",
    "RATE_LIMIT",
    "RELEASE_DATES_PATHS",
    "RELEASE_DATES_TTL",
    "SOURCE",
    "PathCaches",
    "auth",
    "cache",
    "cache_filter",
    "classify",
    "client",
    "commodities_cache",
    "config",
    "policy",
    "release_dates_cache",
    "stored_at",
]
