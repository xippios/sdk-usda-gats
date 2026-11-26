"""``scripts/refresh_reference.py`` offline: its declaration on core's frame and its render.

The script declares the five packaged lists in one ``Lists`` of ``xippios.core.refresh``,
whose run, fetches, writes, ``--only`` and count of requests are core's and tested there
(sdk-core ADR-0062). These tests hold what is the package's own: the declaration, each
list's operation and wrapper, the one enum, the gateway's quota header, and that
``--render-only`` on the frame writes ``enums.py`` and the provenance rows of
``reference/README.md`` as committed, without a request.
"""

import ast
import importlib.util
import inspect
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest
import respx
from xippios.core import PackagedList
from xippios.core.refresh import Lists, run
from xippios.usda.fas import REMAINING_HEADER

from xippios.usda.gats._client import client
from xippios.usda.gats.params import PACKAGE, PACKAGED_LISTS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_reference.py"
DIRECTORY = ROOT / "src" / "xippios" / "usda" / "gats"
REFERENCE = DIRECTORY / "reference"
OPERATIONS = {
    "unitsOfMeasure": ("GATSData_GetUnitsOfMeasure", "get_units_of_measure"),
    "regions": ("GATSData_GetRegions", "get_regions"),
    "countries": ("GATSData_GetCountries", "get_countries"),
    "HS6Commodities": ("GATSData_GetHS6Commodities", "get_hs6_commodities"),
    "customsDistricts": ("GATSData_GetCustomsDistricts", "get_customs_districts"),
}
"""Each packaged list: the operation it comes from and its wrapper, the fixture directory."""


def _load(name: str, path: Path) -> ModuleType:
    """The module at ``path``, loaded without running its ``__main__`` block."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load("refresh_reference", SCRIPT)


def _endpoint_literals(wrapper: Callable[[], object]) -> list[object]:
    """Every ``endpoint=`` the wrapper's module passes, read from its source."""
    tree = ast.parse(inspect.getsource(sys.modules[wrapper.__module__]))
    return [
        keyword.value.value if isinstance(keyword.value, ast.Constant) else keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "endpoint"
    ]


def test_the_script_declares_the_five_lists_on_cores_frame() -> None:
    """One ``Lists``, one ``Listed`` per packaged list (conventions §3): the frame writes a
    list's ``endpoint`` from the operation its ``Listed`` names, not from the wrapper's name
    (conventions §2), so the declared operation is the packaged file's ``endpoint``, the one
    ``endpoint=`` literal its wrapper passes and the first line of the wrapper's docstring;
    the wrapper names the list's fixture directory (conventions §10). ``unitsOfMeasure``
    alone makes an enum, and the quota left is read from the gateway's header, the shared
    package's ``REMAINING_HEADER``."""
    lists = script.LISTS
    assert isinstance(lists, Lists)
    assert (lists.package, set(lists.packaged)) == (PACKAGE, set(PACKAGED_LISTS))
    assert lists.client is client
    assert lists.quota_header == REMAINING_HEADER == "x-ratelimit-remaining"
    assert [listed.name for listed in lists.lists] == list(OPERATIONS)
    enums = [(listed.name, listed.enum) for listed in lists.lists if listed.enum is not None]
    assert [(name, enum.ids, enum.names) for name, enum in enums] == [
        ("unitsOfMeasure", "unitOfMeasureId", "unitOfMeasureName")
    ]
    for listed in lists.lists:
        operation, wrapper = OPERATIONS[listed.name]
        fetch = listed.fetch
        assert (listed.endpoint, getattr(fetch, "__name__", None)) == (operation, wrapper)
        assert (Path(__file__).parent / "fixtures" / wrapper / "all.json").is_file()
        assert operation == PackagedList.load(PACKAGE, listed.name).endpoint, listed.name
        assert _endpoint_literals(fetch) == [operation], listed.name
        assert (fetch.__doc__ or "").splitlines()[0] == f"Call ``{operation}``.", listed.name


def test_each_list_is_fetched_by_the_wrapper_the_live_comparison_reads() -> None:
    """Core's reference frame and its nightly comparison take a wrapper's ``Answer`` and read
    its payload (conventions §3, §10): each ``Listed`` of the script and each entry of
    ``LIVE_LISTS`` in ``tests/test_live.py`` fetch a list by the same ``api/`` wrapper."""
    live = _load("live_lists", Path(__file__).parent / "test_live.py")
    fetches = {listed.name: listed.fetch for listed in script.LISTS.lists}
    assert {name: fetch for name, (_, fetch) in live.LIVE_LISTS.items()} == fetches
    assert live.NO_LIVE_LIST == {}


@pytest.fixture
def committed() -> Iterator[dict[Path, bytes]]:
    """The files ``--render-only`` writes, as committed, put back after the test whatever it
    wrote: ``enums.py``, the provenance table and the packaged lists."""
    paths = [DIRECTORY / "enums.py", *sorted(REFERENCE.iterdir())]
    before = {path: path.read_bytes() for path in paths if path.is_file()}
    yield before
    for path, content in before.items():
        if path.read_bytes() != content:
            path.write_bytes(content)


def test_render_only_writes_the_committed_enums_and_rows_without_a_request(
    committed: dict[Path, bytes], monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    """``--render-only`` runs the frame on the packaged files alone, with no request and no
    key (conventions §15): it renders ``UnitOfMeasureId`` by core's default name for its id
    field, ``CRATES_33`` and ``CRATES_105`` for the name two ids share, and rewrites each
    provenance row under the frame's one header, ``| File | Origin | Fetched |``, from the
    file's ``fetched``. Every file it writes is the committed one, byte for byte."""
    monkeypatch.chdir(ROOT)
    assert run(script.LISTS, ["--render-only"]) == 0
    assert not respx_mock.calls
    assert {path: path.read_bytes() for path in committed} == committed
    readme = (REFERENCE / "README.md").read_text(encoding="utf-8")
    assert "| File | Origin | Fetched |\n| --- | --- | --- |\n" in readme
