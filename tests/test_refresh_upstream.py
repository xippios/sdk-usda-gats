"""``scripts/refresh_upstream.py``'s own code, offline: its ``Snapshot`` and its own hooks.

The script declares a ``Snapshot`` that sdk-core's frame runs, ``xippios.core.refresh``
(conventions §3): the fetch through core's client, ``FETCHED.md``, the write and ``--check``
are the frame's, and core's tests hold them. The portal's pages, the hooks that read them and
the paragraphs that say how are the kit of the FAS portal in ``xippios.usda.fas``, whose tests
hold its units. The tests here hold what the script declares on the kit, its own pages, its own
paragraph, its own notes and its check of the paths the cut leaves out, and that the cut
reproduces the committed GATS part. Nothing here sends a request or writes under
``docs/upstream/``. ``OBSERVED.md`` is the one file under ``docs/upstream/`` written by hand
(conventions §3, sdk-core ADR-0028).
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from xippios.core.refresh import Page, Response, Row, dump_json
from xippios.usda.fas.portal import Portal

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"
UPSTREAM = ROOT / "docs" / "upstream"
PORTAL_FILE = "openapi/portal-document.json"
"""The committed GATS part of the portal's document, the file of the kit's second page."""
PORTAL = UPSTREAM / PORTAL_FILE


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def portal_page() -> Page:
    pages: tuple[Page, ...] = script.SNAPSHOT.pages
    (page,) = [page for page in pages if page.file == PORTAL_FILE]
    return page


def answer(url: str, status: int, body: bytes, content_type: str) -> Response:
    """An answer as a run reads it, composed by the test.

    It is an input of the test, not an answer from USDA FAS Global Agricultural Trade System.
    """
    return Response(
        url=url,
        status=status,
        body=body,
        content_type=content_type,
        etag=None,
        last_modified=None,
        redirects=(),
    )


def document(*others: str) -> Response:
    """The portal's document as a run reads it, composed from the committed GATS part.

    NOT RECORDED as served: the GATS part that the capture of 2026-10-25 kept in ``PORTAL``,
    read at test time, with one path of its own under each prefix in ``others``, in the shape
    upstream answered the whole document, the text ``json.dumps(indent=2,
    ensure_ascii=False)`` reproduces. The tests assert what the script makes of it, never
    that upstream sends it. The answer is an input of the test, not an answer from USDA FAS
    Global Agricultural Trade System. (conventions §10; sdk-core ADR-0064, decision 9)
    """
    whole: dict[str, Any] = json.loads(PORTAL.read_bytes())
    for prefix in others:
        whole["paths"][f"{prefix}example"] = {"get": {"operationId": "Example"}}
    return answer(portal_page().url, 200, dump_json(whole), "application/json")


def test_the_script_builds_on_the_kit_of_the_portal_for_gats() -> None:
    """One ``Portal`` for GATS's prefix, whose hooks the snapshot takes, but ``reduce``, which
    checks the paths the cut leaves out, and ``note``, which names the script's own page."""
    assert isinstance(script.PORTAL, Portal)
    assert (script.PORTAL.prefix, script.PORTAL.service) == ("/api/gats/", "GATS")
    snapshot = script.SNAPSHOT
    assert (snapshot.name, snapshot.slug) == (
        "USDA FAS Global Agricultural Trade System",
        "usda-gats",
    )
    assert snapshot.reduce is script.reduce
    assert snapshot.note is script.note
    assert snapshot.linked == script.PORTAL.linked
    assert snapshot.sections == script.PORTAL.sections


def test_reduce_cuts_a_document_to_its_gats_part_as_committed() -> None:
    """The cut of a document that holds one path each of ESR and PSD beside GATS's gives back
    the committed part byte for byte, and the document's row counts what it kept."""
    page, response = portal_page(), document(*script.DROP_PREFIXES)
    content = script.SNAPSHOT.reduce(page, response)
    assert content == PORTAL.read_bytes()
    assert script.SNAPSHOT.note(Row(page, response, content, page.note)) == (
        "GATS part: kept 19 `/api/gats/` paths; dropped 1 `/api/esr/`, 1 `/api/psd/` (out of "
        "scope here, own packages); kept 0 of 0 definitions"
    )


@pytest.mark.parametrize(
    "others",
    [("/api/esr/",), ("/api/esr/", "/api/psd/", "/api/other/"), ()],
    ids=["psd_gone", "a_fourth_service", "gats_alone"],
)
def test_reduce_stops_unless_the_paths_left_out_are_esr_s_and_psd_s(
    others: tuple[str, ...],
) -> None:
    """A document whose cut leaves out other prefixes than exactly ``/api/esr/`` and
    ``/api/psd/`` stops the run before anything is written."""
    with pytest.raises(SystemExit, match="the paths left out are"):
        script.SNAPSHOT.reduce(portal_page(), document(*others))


def test_the_snapshot_declares_its_pages_in_order() -> None:
    """The kit's pages first, the portal's three, whose own tests hold them; then GATS's own:
    the application page, which the frame follows through its redirect on its host, and the
    FAS data page the CDN refuses, which goes to ``Not fetched``."""
    pages = script.SNAPSHOT.pages
    assert pages[:3] == script.PORTAL.pages
    assert [(page.url, page.file, page.status) for page in pages[3:]] == [
        (script.GATS_APP_URL, None, 200),
        (script.FAS_DATA_URL, None, 403),
    ]
    refused = pages[4]
    assert (refused.stable, refused.names) == (False, "Access Denied")
    assert script.SNAPSHOT.attribution == (), "neither document states a copyright line"


def test_the_gats_application_s_row_names_the_screen_detection_page() -> None:
    """The script's own note for the application page while it is still the small shell with
    its one script; a page without that script stops the run."""
    page = next(page for page in script.SNAPSHOT.pages if page.url == script.GATS_APP_URL)
    shell = f"<html><head><script>{script.GATS_APP_MARKER};</script></head></html>".encode()
    found = answer(script.GATS_APP_URL, 200, shell, "text/html")
    assert script.note(Row(page, found, None, page.note)) == script.GATS_APP_NOTE
    other = answer(script.GATS_APP_URL, 200, b"<html><body>GATS</body></html>", "text/html")
    with pytest.raises(SystemExit, match="mount point"):
        script.note(Row(page, other, None, page.note))


def test_the_capture_is_the_kit_s_then_gats_s_own_paragraph() -> None:
    """How this is captured: the kit's four paragraphs, then GATS's own on its check and its
    two pages, which leaves the shells' bound to the kit's and names no private place."""
    capture = script.SNAPSHOT.capture
    assert capture.startswith(f"{script.PORTAL.capture}\n\n")
    own = capture.removeprefix(f"{script.PORTAL.capture}\n\n")
    assert own.startswith("The script stops unless the paths that its cut leaves out")
    assert "\n\n" not in own, "one paragraph of the script's own"
    assert "bytes" not in own, "the shells' bound is the kit's to state"
    assert "scratch" not in capture
    assert "scratch" not in SCRIPT.read_text(encoding="utf-8")
