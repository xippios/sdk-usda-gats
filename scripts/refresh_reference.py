"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Every list in ``LISTS``, ``ID_LISTS`` or ``TABLES`` is fetched through its layer-1 wrapper
in ``api/``, never through a task that might answer from the package, and once every list
is fetched each is written to ``reference/<name>.json`` by ``PackagedList.write``: the
list's name, the upstream operation it came from, the UTC time of the fetch to the second
and upstream's records under upstream's field names (``dump_upstream``), a value list as
records of one field named by the list (conventions §3). A fetch that fails stops the run
before the first file is written. Each request is sent once (``metered``): a 5xx or a 429
spends no second call of the key's quota, and the run prints the requests it sent and the
quota left that the gateway reported, a failed run's too. Then ``enums.py`` is regenerated
from the packaged files by one ``xippios.core.reference.render_enums`` call, a ``StrEnum``
per value list in ``LISTS`` and an ``IntEnum`` per list of integer ids and names in
``ID_LISTS`` (``id_name_pairs``), so that a member compares equal to the id in upstream's
data, each class named after its id field by core's default and naming the day its list
was fetched; and formatted with ``ruff format`` and ``ruff check --fix``, as it is
committed (sdk-core ADR-0031). Where a member name derives to
nothing, or two collide, name it by hand in ``render``'s call:
``render_enums(member_names=...)``, per list and value (an id for an ``IntEnum``).
``TABLES`` are record lists packaged without an enum.

GATS packages five of its lists, all of them records, packaged under upstream's field
names: ``unitsOfMeasure`` is an id list, which makes
``UnitOfMeasureId`` (``unitOfMeasureId`` to ``unitOfMeasureName``, ids 0 to 107; the name
``"Crates"`` of ids 33 and 105 gets ``_<id>`` appended, ``CRATES_33`` and ``CRATES_105``);
``regions``, ``countries``, ``HS6Commodities`` and ``customsDistricts`` stay tables, not
enums: ``params`` checks partner codes and customs-district ids against two of them, and
the ``list_*`` tasks answer from all five. GATS has no value list, so ``LISTS`` stays
empty. The HS10 list, ``GATSData_GetCommodities``, is not packaged: 24,936 records and
7.6 MB, which ``tasks.list_commodities`` fetches live. The list endpoints take the
api.data.gov key, so ``DATA_GOV_API_KEY`` must be in the environment; run from the
repository root::

    uv run python scripts/refresh_reference.py

Five requests against api.data.gov's hourly quota, each sent once. Then update the dates
and the counts in ``reference/README.md``. Only lists that are the same for every caller
are packaged; a multi-tenant source packages no tenant data (sdk-core ADR-0036), which GATS
is not.

``--only <list> ...`` fetches the named lists alone, e.g. ``--only countries``, and keeps
every other list's file: both are checked before the first request, the named lists
against ``params.PACKAGED_LISTS`` and the kept ones for a packaged file.

``--render-only`` regenerates ``enums.py`` from the packaged ``reference/*.json`` alone,
without a request and without a key: after a core release changes the renderers
(conventions §15, item 6), it changes ``enums.py`` and nothing else.
"""

import argparse
import subprocess
import sys
from collections.abc import Callable, Coroutine, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from xippios.core import AsyncClient, PackagedList, RetryPolicy, UpstreamModel, sync
from xippios.core.reference import id_name_pairs, render_enums

from xippios.usda.gats import api
from xippios.usda.gats._client import client
from xippios.usda.gats.params import PACKAGED_LISTS

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/usda/gats"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"

QUOTA_HEADER: str | None = "x-ratelimit-remaining"
"""The response header in which api.data.gov reports the requests left in the key's hourly
quota, on every keyed GATS answer recorded."""

Fetcher = Callable[[], Coroutine[Any, Any, Sequence[UpstreamModel]]]
"""An endpoint wrapper in ``api/`` that returns a list's records, named after its operation."""

LISTS: dict[str, Callable[[], Coroutine[Any, Any, list[str]]]] = {}
"""Value lists, packaged as records of one field named by the list, one ``StrEnum`` each:
none packaged; GATS's lists are records."""

ID_LISTS: dict[str, tuple[str, str, Fetcher]] = {
    "unitsOfMeasure": ("unitOfMeasureId", "unitOfMeasureName", api.get_units_of_measure),
}
"""Lists of integer ids and names, one ``IntEnum`` each (conventions §3), in module order.

List name, as the upstream path names it, to (id field, name field, wrapper), the fields
as upstream names them in the recorded answer. Packaged as upstream's records under
upstream's field names (``dump_upstream``). Each enum is keyed by its id field and named
after it by ``render_enums``' default, as sdk-usda-psd's are, so ``unitOfMeasureId`` makes
``UnitOfMeasureId``,
whose docstring reads "Values of ``unitOfMeasureId``". The name field is
``unitOfMeasureName`` (``"Kilograms"``), not ``unitOfMeasureCode`` (``"KG"``): codes
repeat as names do (``"CRT"`` is 33 and 105) and many are no identifier (``"24LBC"``,
``"MT50%"``).
"""

TABLES: dict[str, Fetcher] = {
    "regions": api.get_regions,
    "countries": api.get_countries,
    "HS6Commodities": api.get_hs6_commodities,
    "customsDistricts": api.get_customs_districts,
}
"""Record lists packaged as tables, with no enum: region, partner, HS6 and district codes.

List name, as the upstream path names it, to its wrapper, in the snapshot's order.
Packaged like an id list, as upstream's records under upstream's field names, which
``params`` reads; together with ``LISTS`` and ``ID_LISTS`` they are
``params.PACKAGED_LISTS``.
"""

OPERATIONS: dict[Callable[[], object], str] = {
    api.get_regions: "GATSData_GetRegions",
    api.get_countries: "GATSData_GetCountries",
    api.get_hs6_commodities: "GATSData_GetHS6Commodities",
    api.get_units_of_measure: "GATSData_GetUnitsOfMeasure",
    api.get_customs_districts: "GATSData_GetCustomsDistricts",
}
"""The upstream operation of each wrapper above, verbatim, as its ``endpoint=`` names it:
the wrapper's own name is the operation in snake case (conventions §2)."""


class Meter:
    """What a run spent: the requests it sent and the quota left that upstream reported.

    The client's ``observe`` hook, which core calls with every response from the wire. It
    calls the hook the client had first, the gateway's quota policy (sdk-core ADR-0037),
    and keeps the last count that upstream sent in ``QUOTA_HEADER``. A request is counted
    by its response: with no retry each has one, but for one that fails in transport, whose
    error ends the run.
    """

    def __init__(self, observe: Callable[[httpx.Response], None] | None) -> None:
        self.sent = 0
        self.left: int | None = None
        self._observe = observe

    def __call__(self, response: httpx.Response) -> None:
        """Count ``response`` and keep the quota it reports, after the hook it replaces."""
        if self._observe is not None:
            self._observe(response)
        self.sent += 1
        value = response.headers.get(QUOTA_HEADER) if QUOTA_HEADER else None
        if value is not None and value.isascii() and value.isdigit():
            self.left = int(value)

    def report(self) -> str:
        """The requests sent and the quota left, as upstream last reported it, one line."""
        left = "not reported" if self.left is None else f"{self.left} ({QUOTA_HEADER})"
        return f"requests sent: {self.sent}; quota left: {left}"


@contextmanager
def metered(target: AsyncClient) -> Iterator[Meter]:
    """``target`` for the block: one attempt per request, each counted, then the report.

    ``RetryPolicy(max_attempts=1)`` keeps a 5xx or a 429 from spending a second call of the
    key's quota. ``target``'s configuration is restored after the block, and the report is
    printed, a failed run's too.
    """
    configured = target.config
    meter = Meter(configured.observe)
    target.config = replace(configured, retry=RetryPolicy(max_attempts=1), observe=meter)
    try:
        yield meter
    finally:
        target.config = configured
        print(meter.report())  # noqa: T201


def operation(fetch: Callable[[], object]) -> str:
    """The upstream operation a wrapper calls, verbatim, the packaged file's ``endpoint``."""
    return OPERATIONS[fetch]


def packaged(name: str, endpoint: str, records: Sequence[dict[str, Any]]) -> PackagedList:
    """The list ``name`` as just fetched from ``endpoint``, for ``reference/<name>.json``."""
    return PackagedList(
        param=name, endpoint=endpoint, fetched=datetime.now(UTC), records=list(records)
    )


def write(fetched: PackagedList) -> None:
    """Write ``reference/<name>.json`` with ``PackagedList.write``: fetched then, to the second."""
    path = REFERENCE / f"{fetched.param}.json"
    fetched.write(path)
    print(f"{path.name}: {len(fetched.records)} records from {fetched.endpoint}")  # noqa: T201


def read(name: str) -> PackagedList:
    """The packaged ``reference/<name>.json``, as ``write`` wrote it."""
    path = REFERENCE / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not packaged yet: run the script without --render-only")
    return PackagedList.model_validate_json(path.read_text(encoding="utf-8"))


def module() -> str:
    """The text of ``enums.py`` from the packaged files, before ruff formats it.

    One ``render_enums`` call: a ``StrEnum`` per value list, keyed by the list, and an
    ``IntEnum`` per id list, keyed by its id field and named after it by core's default
    (``unitOfMeasureId`` makes ``UnitOfMeasureId``), each class docstring naming the day its
    list was fetched.
    """
    lists: dict[str, Sequence[str] | Sequence[tuple[int, str]]] = {}
    fetched: dict[str, str] = {}
    for name in LISTS:
        values = read(name)
        lists[name] = [record[name] for record in values.records]
        fetched[name] = f"{values.fetched:%Y-%m-%d}"
    for name, (id_field, name_field, _) in ID_LISTS.items():
        ids = read(name)
        lists[id_field] = id_name_pairs(ids.records, id_field=id_field, name_field=name_field)
        fetched[id_field] = f"{ids.fetched:%Y-%m-%d}"
    return render_enums(lists, fetched=fetched, generator=GENERATOR)


def render() -> None:
    """Regenerate ``enums.py`` from the packaged files and format it as it is committed."""
    text = module()
    ENUMS.write_text(text, encoding="utf-8")
    sys.stdout.flush()
    for command in (["format"], ["check", "--fix"]):
        run = subprocess.run([sys.executable, "-m", "ruff", *command, str(ENUMS)], cwd=ROOT)
        if run.returncode:
            raise SystemExit(f"ruff {' '.join(command)} left {ENUMS.name} failing")
    print(f"{ENUMS.name}: {len(LISTS) + len(ID_LISTS)} enums")  # noqa: T201


def refresh(only: Sequence[str] = ()) -> None:
    """Fetch every list, then write its file, then regenerate ``enums.py`` from the files.

    ``only``, the lists ``--only`` names, fetches those alone and keeps every other list's
    file, which must be packaged already. Both are checked before the first request, and
    every list is fetched before the first file is written.
    """
    names = [*LISTS, *ID_LISTS, *TABLES]
    if sorted(names) != sorted(PACKAGED_LISTS):
        raise SystemExit("LISTS, ID_LISTS and TABLES name other lists than params.PACKAGED_LISTS")
    if unknown := [name for name in only if name not in names]:
        raise SystemExit(f"--only: no list {', '.join(unknown)} in {', '.join(names)}")
    chosen = set(only or names)
    kept = [name for name in names if name not in chosen]
    if missing := [name for name in kept if not (REFERENCE / f"{name}.json").is_file()]:
        raise SystemExit(f"{', '.join(missing)} is not packaged yet: run without --only")
    with metered(client):
        lists = [
            *(
                packaged(name, operation(fetch), [{name: value} for value in sync(fetch)()])
                for name, fetch in LISTS.items()
                if name in chosen
            ),
            *(
                packaged(name, operation(fetch), [r.dump_upstream() for r in sync(fetch)()])
                for name, (_, _, fetch) in ID_LISTS.items()
                if name in chosen
            ),
            *(
                packaged(name, operation(fetch), [r.dump_upstream() for r in sync(fetch)()])
                for name, fetch in TABLES.items()
                if name in chosen
            ),
        ]
    REFERENCE.mkdir(exist_ok=True)
    for fetched in lists:
        write(fetched)
    render()


def main(argv: Sequence[str] | None = None) -> None:
    """Refresh from upstream, some lists with ``--only``, or ``enums.py`` alone."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate enums.py from the packaged reference/*.json, without a request or a key",
    )
    choice.add_argument(
        "--only",
        nargs="+",
        default=[],
        metavar="LIST",
        help="fetch these lists of PACKAGED_LISTS alone and keep every other list's file",
    )
    args = parser.parse_args(argv)
    if args.render_only:
        render()
    else:
        refresh(args.only)


if __name__ == "__main__":
    main()
