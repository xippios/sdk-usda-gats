"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Every list in ``LISTS``, ``ID_LISTS`` or ``TABLES`` is fetched through its layer-1 wrapper
in ``api/``, never through a task that might answer from the package, and written to
``reference/<name>.json`` by ``PackagedList.write``: the list's name, the upstream
operation it came from, the UTC time of the fetch to the second and upstream's records
under upstream's field names (``dump_upstream``), a value list as records of one field
named by the list (conventions §3). Then ``enums.py`` is regenerated from the packaged
files by one ``xippios.core.reference.render_enums`` call, a ``StrEnum`` per value list in
``LISTS`` and an ``IntEnum`` per list of integer ids and names in ``ID_LISTS``
(``id_name_pairs``), so that a member compares equal to the id in upstream's data, each
class naming the day its list was fetched; and formatted with ``ruff format`` and
``ruff check --fix``, as it is committed (ADR-0008). Where a member name derives to
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

Five requests against api.data.gov's hourly quota. Then update the dates and the counts
in ``reference/README.md``. Only lists that are the same for every caller are packaged; a
multi-tenant source packages no tenant data (ADR-0014), which GATS is not.

``--render-only`` regenerates ``enums.py`` from the packaged ``reference/*.json`` alone,
without a request and without a key: after a core release changes the renderers
(conventions §15, item 6), it changes ``enums.py`` and nothing else.
"""

import argparse
import subprocess
import sys
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xippios.core import PackagedList, UpstreamModel, sync
from xippios.core.reference import id_name_pairs, render_enums

from xippios.usda.gats import api
from xippios.usda.gats.params import PACKAGED_LISTS

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/usda/gats"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"

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
upstream's field names (``dump_upstream``). Each enum is keyed by its id field and
named after it, as sdk-usda-psd's are, so ``unitOfMeasureId`` makes ``UnitOfMeasureId``,
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


def operation(fetch: Callable[[], object]) -> str:
    """The upstream operation a wrapper calls, verbatim, the packaged file's ``endpoint``."""
    return OPERATIONS[fetch]


def write(name: str, endpoint: str, records: Sequence[dict[str, Any]]) -> None:
    """Write ``reference/<name>.json`` with ``PackagedList.write``: fetched now, to the second."""
    path = REFERENCE / f"{name}.json"
    PackagedList(
        param=name, endpoint=endpoint, fetched=datetime.now(UTC), records=list(records)
    ).write(path)
    print(f"{path.name}: {len(records)} records from {endpoint}")  # noqa: T201


def read(name: str) -> PackagedList:
    """The packaged ``reference/<name>.json``, as ``write`` wrote it."""
    path = REFERENCE / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not packaged yet: run the script without --render-only")
    return PackagedList.model_validate_json(path.read_text(encoding="utf-8"))


def render() -> None:
    """Regenerate ``enums.py`` from the packaged files and format it as it is committed.

    One ``render_enums`` call: a ``StrEnum`` per value list, keyed by the list, and an
    ``IntEnum`` per id list, keyed and named by its id field (``unitOfMeasureId`` makes
    ``UnitOfMeasureId``), each class docstring naming the day its list was fetched.
    """
    lists: dict[str, Sequence[str] | Sequence[tuple[int, str]]] = {}
    fetched: dict[str, str] = {}
    class_names: dict[str, str] = {}
    for name in LISTS:
        values = read(name)
        lists[name] = [record[name] for record in values.records]
        fetched[name] = f"{values.fetched:%Y-%m-%d}"
    for name, (id_field, name_field, _) in ID_LISTS.items():
        ids = read(name)
        lists[id_field] = id_name_pairs(ids.records, id_field=id_field, name_field=name_field)
        fetched[id_field] = f"{ids.fetched:%Y-%m-%d}"
        class_names[id_field] = id_field[:1].upper() + id_field[1:]
    module = render_enums(lists, fetched=fetched, class_names=class_names, generator=GENERATOR)
    ENUMS.write_text(module, encoding="utf-8")
    sys.stdout.flush()
    for command in (["format"], ["check", "--fix"]):
        run = subprocess.run([sys.executable, "-m", "ruff", *command, str(ENUMS)], cwd=ROOT)
        if run.returncode:
            raise SystemExit(f"ruff {' '.join(command)} left {ENUMS.name} failing")
    print(f"{ENUMS.name}: {len(lists)} enums")  # noqa: T201


def refresh() -> None:
    """Fetch every list, write its file and regenerate ``enums.py`` from the files."""
    if {*LISTS, *ID_LISTS, *TABLES} != set(PACKAGED_LISTS):
        raise SystemExit("LISTS, ID_LISTS and TABLES name other lists than params.PACKAGED_LISTS")
    REFERENCE.mkdir(exist_ok=True)
    for name, fetch in LISTS.items():
        write(name, operation(fetch), [{name: value} for value in sync(fetch)()])
    for name, fetch_records in TABLES.items():
        records = [record.dump_upstream() for record in sync(fetch_records)()]
        write(name, operation(fetch_records), records)
    for name, (_, _, fetch_records) in ID_LISTS.items():
        records = [record.dump_upstream() for record in sync(fetch_records)()]
        write(name, operation(fetch_records), records)
    render()


def main() -> None:
    """Refresh from upstream, or with ``--render-only`` regenerate ``enums.py`` alone."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate enums.py from the packaged reference/*.json, without a request or a key",
    )
    args = parser.parse_args()
    if args.render_only:
        render()
    else:
        refresh()


if __name__ == "__main__":
    main()
