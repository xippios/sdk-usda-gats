"""The configured ``xippios.core`` client for USDA FAS Global Agricultural Trade System.

One ``AsyncClient`` for the whole package, shared by the tasks, the sync facades and the MCP
server, on api.data.gov's gateway at ``BASE_URL`` with ``Accept: application/json``. It
keeps a pace of its own, ``RATE_LIMIT``, since the snapshot documents none. The gateway is
the shared package's, ``xippios.usda.fas``'s ``Gateway`` (sdk-core ADR-0032, decision 5;
sdk-core ADR-0065, decision 1): ``gateway.auth`` sends the key from ``DATA_GOV_API_KEY`` in
the ``X-Api-Key`` header; ``Gateway.policy``, the one ``QuotaPolicy`` per process for that
key, keeps api.data.gov's hourly quota from every answer from the wire and never fires a
request into a spent one, waiting it out within 30 s and otherwise refusing it without
sending (sdk-core ADR-0033, sdk-core ADR-0037); and ``classify`` asks ``gateway.classify``
first, which maps the gateway's ``API_KEY_*`` answers to ``AuthError``, its 429 to
``RateLimitError`` and its ``NOT_FOUND`` to ``NotFoundError``. ``Gateway(SOURCE)`` names no
data path: GATS answers a month or a year without data with ``[]`` and never with FAS's
empty 404, so no answer of GATS's is the shared package's ``NoDataForYear``.
``x-ratelimit-limit: 1000`` and ``x-ratelimit-remaining`` are on every keyed GATS answer
recorded on 2026-10-25, the error answers to a valid key included; the gateway sends no
reset header.

Core's response cache keeps every answer, by the maintainer's decision of 2026-11-26, in
one ``MemoryCache`` with a lifetime per path prefix, ``LIFETIMES`` (sdk-core ADR-0040,
decision 3; ADR-0061, decisions 9 and 11): core's default of 300 seconds for every path, so that a
narrower filter on an answer already read and the next rows of a cut tool send no request;
the two Census release-date lists for an hour, since every Census data task fetches its
flow's list before the data and would otherwise cost two requests against the hourly quota;
every UN Trade answer, its data and its two release-date lists, for a day, since the UN
Trade feed is frozen (both lists end with statistical year 2019, last released on
2021-01-18, as recorded on 2026-10-26); and the HS10 commodities list for a day, 7.6 MB that
``tasks.list_commodities`` fetches whole for every search. It stores a body of up to
``CACHE_MAX_BYTES``, 16 MiB, twice core's default, so that the HS10 list stays cached when
it grows; a larger answer, as India's 2016 UN Trade exports of about 17 MB, is not stored.

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
    EnvVar,
    MemoryCache,
    RateLimit,
    XippiosError,
)
from xippios.usda.fas import API_KEY_ENV, Gateway

from xippios.usda.gats._version import __version__

SOURCE = "usda-gats"
BASE_URL = "https://api.fas.usda.gov"
"""The gateway's host root; every GATS path keeps its ``/api/gats/`` prefix, as the
snapshot's ``paths`` name it (the portal document's ``host`` is ``api.fas.usda.gov``, no
``basePath``)."""
ENV_VARS: tuple[EnvVar, ...] = (EnvVar(API_KEY_ENV, secret=True, required=True),)
"""The variables the package reads, for a host (conventions §7; sdk-core ADR-0026, amendment
2026-11-18, point c): the gateway's key alone. An ``EnvVar`` names a variable and reads none;
a variable the source reads beside these joins the list."""
# A self-imposed pace: upstream documents no per-second or per-minute limit (sdk-core ADR-0033,
# decision 1).
RATE_LIMIT = RateLimit(per_minute=60, burst=1)
"""One request per second, no burst: a pace of our own, since the snapshot documents none.

At this pace the gateway's 1,000 requests per hour, shared with every other package using
the same key, last about 17 minutes; past that ``Gateway.policy`` takes over.
"""

# api.data.gov's key, its documented answers and its hourly quota, kept by one policy per
# process that every source behind the gateway shares (sdk-core ADR-0032).
gateway = Gateway(SOURCE)
"""api.data.gov for this package: ``auth``, ``classify`` and ``install``, with no data path,
since GATS never answers FAS's empty 404 for a period without data."""

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

UN_TRADE_PATH = "/api/gats/UNTrade"
"""The prefix of every UN Trade path, its data and its release lists, cached for
``UN_TRADE_TTL``, a day.

``GATSData_GetUNTradeExports`` and its two siblings answer one reporter-year, and
``GATSData_GetUNTradeExportDataReleaseInfo`` and ``GATSData_GetUNTradeImportDataReleaseInfo``
one record per reporter and statistical year, about 400 KB of JSON each. Each UN Trade data
task (``tasks.get_un_exports`` and the two others) reads its flow's list before the data to
check the reporter-year, and ``tasks.get_un_release_dates`` answers from it; from the cache
a task costs one request per flow and one per reporter-year per ``UN_TRADE_TTL``. As
recorded on 2026-10-26 both lists end with statistical year 2019 and their newest release
is dated 2021-01-18 (``tests/fixtures/get_un_trade_export_data_release_info/all.json``): the
feed is frozen, so a day's cache loses nothing an hour's would catch.
"""

COMMODITIES_PATH = "/api/gats/commodities"
"""``GATSData_GetCommodities``, the HS10 commodities list, cached for ``COMMODITIES_TTL``.

One answer of 24,936 records and about 7.6 MB of JSON, the largest in the family, which
``tasks.list_commodities`` fetches whole and filters itself; from the cache a search costs
no request for a day.
"""

DEFAULT_TTL = 300.0
"""Seconds a cached answer of any other path answers: five minutes, core's default.

A Census month or a customs-district month, the packaged lists' paths that the reference
refresh reads and every path that no longer prefix names. Within it, a narrower filter on a month
already read and the next rows of a cut tool are the cache's (sdk-core ADR-0061, decisions
9 and 11), and a month that Census revises in those minutes keeps its earlier figures until the
entry expires.
"""

RELEASE_DATES_TTL = 3600.0
"""Seconds a cached Census release-date list answers: one hour.

Within that hour after a release the cached list can lag upstream: a task can refuse a
month Census has just released, as not released yet, until the entry expires. Its
``NotFoundError`` then says when the list was fetched.
"""

UN_TRADE_TTL = 86400.0
"""Seconds a cached UN Trade answer answers: one day.

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
says why (sdk-core ADR-0040, decision 3). The HS10 commodities list was 7,592,916 bytes as
recorded on 2026-10-26 (``tests/fixtures/get_commodities/all.json``), 795,692 bytes
(9.5 %) under the default: a refresh upstream that grew it past 8 MiB would silently stop
the day's cache, and every ``tasks.list_commodities`` search would fetch the 7.6 MB again.
16 MiB leaves it room to double; the release-date lists, about 81 KB and 400 KB, are far
below either bound.
"""


LIFETIMES: Mapping[str, float] = MappingProxyType(
    {
        "/": DEFAULT_TTL,
        **dict.fromkeys(sorted(RELEASE_DATES_PATHS), RELEASE_DATES_TTL),
        UN_TRADE_PATH: UN_TRADE_TTL,
        COMMODITIES_PATH: COMMODITIES_TTL,
    }
)
"""Seconds the cache keeps an answer, by path prefix: every path, four of them longer.

Core's ``MemoryCache`` matches the longest prefix that a request's path starts with
(sdk-core ADR-0040, decision 3), so ``"/"`` keeps every answer for ``DEFAULT_TTL`` that
no longer prefix names.
"""

cache = MemoryCache(lifetimes=LIFETIMES)
"""Core's response cache, shared by every caller of ``client`` in the process.

Only HTTP 200 answers of up to ``CACHE_MAX_BYTES`` are stored, each for its lifetime in
``LIFETIMES``: five minutes by default, the Census release-date lists for an hour, the UN
Trade answers and the commodities list for a day. A hit sends nothing, so the rate limiter
and the quota
policy never see it (sdk-core ADR-0037).
"""


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
    "CACHE_MAX_BYTES",
    "COMMODITIES_PATH",
    "COMMODITIES_TTL",
    "DEFAULT_TTL",
    "ENV_VARS",
    "LIFETIMES",
    "RATE_LIMIT",
    "RELEASE_DATES_PATHS",
    "RELEASE_DATES_TTL",
    "SOURCE",
    "UN_TRADE_PATH",
    "UN_TRADE_TTL",
    "auth",
    "cache",
    "classify",
    "client",
    "config",
    "gateway",
]
