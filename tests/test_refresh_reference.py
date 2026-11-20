"""``scripts/refresh_reference.py`` offline: its run, ``--only`` and its render.

A run sends each request once and counts it, fetches every list before it writes one, and
with ``--only`` fetches the lists it names alone, after checking them and the lists it
keeps before any request. These tests read the committed files, write under ``tmp_path``
alone and send no request: the fetchers are replaced, or a route of respx answers.
"""

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from xippios.core import PackagedList, RetryPolicy, UpstreamError
from xippios.core.testing import ReplayFixture

from xippios.usda.gats import api
from xippios.usda.gats._client import BASE_URL, client
from xippios.usda.gats.params import PACKAGED_LISTS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_reference.py"
PACKAGE = ROOT / "src" / "xippios" / "usda" / "gats"
REFERENCE = PACKAGE / "reference"
ENUMS = PACKAGE / "enums.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_reference", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()

Fetcher = Callable[[], Coroutine[Any, Any, list[Any]]]


class Record:
    """A record as a wrapper returns it, for the tests that replace the fetchers."""

    def __init__(self, name: str) -> None:
        self.name = name

    def dump_upstream(self) -> dict[str, str]:
        return {"name": self.name}


@pytest.fixture
def reference_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The packaged files copied under ``tmp_path`` and the script pointed at them: a test
    reads what a run writes, and nothing in the package moves."""
    reference = tmp_path / "reference"
    shutil.copytree(REFERENCE, reference)
    monkeypatch.setattr(script, "REFERENCE", reference)
    return reference


def files(reference: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(reference.iterdir())}


def replace_fetchers(monkeypatch: pytest.MonkeyPatch, fetch: Callable[[str], Fetcher]) -> None:
    """Every list's wrapper replaced by ``fetch(name)``, its operation kept."""
    tables = {name: fetch(name) for name in script.TABLES}
    ids = {
        name: (id_field, name_field, fetch(name))
        for name, (id_field, name_field, _) in script.ID_LISTS.items()
    }
    operations = {
        **{tables[name]: script.OPERATIONS[wrapper] for name, wrapper in script.TABLES.items()},
        **{
            ids[name][2]: script.OPERATIONS[wrapper]
            for name, (_, _, wrapper) in script.ID_LISTS.items()
        },
    }
    monkeypatch.setattr(script, "TABLES", tables)
    monkeypatch.setattr(script, "ID_LISTS", ids)
    monkeypatch.setattr(script, "OPERATIONS", operations)


def test_refresh_fetches_every_list_before_it_writes_one(
    reference_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetch that fails after others succeeded leaves every packaged file as it was, so a
    failed run is run again whole, and ``enums.py`` is not rendered."""
    before = files(reference_copy)
    fetched: list[str] = []

    def fetch(name: str) -> Fetcher:
        async def records() -> list[Any]:
            fetched.append(name)
            if len(fetched) == 3:
                raise UpstreamError("503 from upstream", status=503, body="", source="usda-gats")
            return [Record("new")]

        return records

    def rendered() -> None:
        raise AssertionError("enums.py rendered after a failed fetch")

    replace_fetchers(monkeypatch, fetch)
    monkeypatch.setattr(script, "render", rendered)
    with pytest.raises(UpstreamError):
        script.refresh()
    assert len(fetched) == 3
    assert files(reference_copy) == before


def test_refresh_writes_every_list_once_all_are_fetched(
    reference_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The five packaged lists, each written once every fetch is done, then ``enums.py``
    rendered from the files."""
    order: list[str] = []

    def fetch(name: str) -> Fetcher:
        async def records() -> list[Any]:
            order.append(name)
            return [Record(name)]

        return records

    def write(fetched: PackagedList) -> None:
        order.append(f"write {fetched.param}")

    replace_fetchers(monkeypatch, fetch)
    monkeypatch.setattr(script, "write", write)
    monkeypatch.setattr(script, "render", lambda: order.append("render"))
    script.refresh()
    names = [*script.ID_LISTS, *script.TABLES]
    assert sorted(names) == sorted(PACKAGED_LISTS)
    assert order == [*names, *(f"write {name}" for name in names), "render"]


def test_only_refuses_a_list_it_does_not_package_before_any_request(
    reference_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fetch(name: str) -> Fetcher:
        async def records() -> list[Any]:
            raise AssertionError("a request sent before --only was checked")

        return records

    replace_fetchers(monkeypatch, fetch)
    with pytest.raises(SystemExit, match="--only: no list countrys, commodities in "):
        script.refresh(["countrys", "regions", "commodities"])


def test_only_refuses_before_any_request_when_a_kept_list_is_not_packaged(
    reference_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--only`` keeps every other list's file, so each must be packaged already: a list
    added to the tables and never fetched stops the run before its first request."""

    def fetch(name: str) -> Fetcher:
        async def records() -> list[Any]:
            raise AssertionError("a request sent before the kept lists were checked")

        return records

    replace_fetchers(monkeypatch, fetch)
    (reference_copy / "customsDistricts.json").unlink()
    with pytest.raises(SystemExit, match="customsDistricts is not packaged yet: run without"):
        script.refresh(["regions"])


def test_only_fetches_the_named_lists_and_keeps_every_other_file(
    reference_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--only regions unitsOfMeasure`` writes those two files and renders ``enums.py``;
    the other packaged files keep their bytes."""
    before = files(reference_copy)
    fetched: list[str] = []
    rendered: list[bool] = []

    def fetch(name: str) -> Fetcher:
        async def records() -> list[Any]:
            fetched.append(name)
            return [Record("ZZ")]

        return records

    replace_fetchers(monkeypatch, fetch)
    monkeypatch.setattr(script, "render", lambda: rendered.append(True))
    script.refresh(["regions", "unitsOfMeasure"])
    after = files(reference_copy)
    assert sorted(fetched) == ["regions", "unitsOfMeasure"]
    assert {name for name in after if after[name] != before[name]} == {
        "regions.json",
        "unitsOfMeasure.json",
    }
    assert rendered == [True]
    regions = PackagedList.model_validate_json(after["regions.json"])
    assert (regions.endpoint, regions.records) == ("GATSData_GetRegions", [{"name": "ZZ"}])


def test_only_and_render_only_exclude_each_other() -> None:
    with pytest.raises(SystemExit) as info:
        script.main(["--render-only", "--only", "regions"])
    assert info.value.code == 2


@pytest.mark.anyio
async def test_metered_sends_each_request_once_and_reports_the_count(
    respx_mock: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    """NOT RECORDED: a bare 503, a body of no shape upstream was seen to send, to show that
    the run leaves it to core (conventions §10). Inside ``metered`` the client sends it
    once, where its retry policy would send it again, and the count is printed after the
    block, a failed run's too. The client's configuration is restored after the block."""
    route = respx_mock.get(f"{BASE_URL}/api/gats/regions").mock(return_value=httpx.Response(503))
    configured = client.config
    assert configured.retry.max_attempts > 1
    meters: list[Any] = []
    retries: list[RetryPolicy] = []

    async def run() -> None:
        with script.metered(client) as meter:
            meters.append(meter)
            retries.append(client.config.retry)
            await api.get_regions()

    with pytest.raises(UpstreamError):
        await run()
    assert retries == [RetryPolicy(max_attempts=1)]
    assert route.call_count == 1
    assert [meter.sent for meter in meters] == [1]
    assert client.config is configured
    assert capsys.readouterr().out == "requests sent: 1; quota left: not reported\n"


@pytest.mark.anyio
async def test_metered_reports_the_quota_the_gateway_left(
    replay_fixture: ReplayFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """The recorded regions answer carries api.data.gov's ``x-ratelimit-remaining``, which
    the report gives as the quota left after the run."""
    replay_fixture("get_regions", "all")
    with script.metered(client) as meter:
        regions = await api.get_regions()
    assert len(regions) == 15
    assert (meter.sent, meter.left) == (1, 966)
    assert capsys.readouterr().out == "requests sent: 1; quota left: 966 (x-ratelimit-remaining)\n"


def test_render_writes_enums_py_as_committed() -> None:
    """``--render-only``'s text, formatted as the script formats it, is ``enums.py`` byte for
    byte: core's default names ``UnitOfMeasureId`` after its id field, as the script's own
    line did (https://github.com/xippios/sdk-core/issues/95). The text goes through ruff on
    stdin with the repository's configuration; nothing is written."""
    text = script.module()
    for command in (["format"], ["check", "--fix", "--quiet", "--exit-zero"]):
        text = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                *command,
                "--stdin-filename",
                str(ENUMS.relative_to(ROOT)),
                "-",
            ],
            input=text,
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout
    assert text == ENUMS.read_text(encoding="utf-8")
