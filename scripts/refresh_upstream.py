"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

The script declares the snapshot, a ``Snapshot`` of ``xippios.core.refresh``, and runs it on
core's frame (conventions §3): the fetch through core's client, which the frame builds without
credentials and names after the package, the attribution check, ``FETCHED.md``, the write and
``--check`` are the frame's, the same in every source. The FAS Open Data Services portal
(https://apps.fas.usda.gov/opendatawebV2/) documents ESR, GATS and PSD alike, and what the three
FAS sources read of it is the kit of the shared package, ``xippios.usda.fas.portal``'s
``Portal``: the portal's pages, the cut of its two Swagger documents to one service's paths, the
backend document that the classic Swagger UI names, the comparison of the two, and the
paragraphs that say how. This script keeps what is GATS's own: the prefix ``/api/gats/``, the
check that the paths the cut leaves out fall under exactly ``/api/esr/`` and ``/api/psd/``, the
GATS application page, which redirects to a screen-detection page, the FAS data page that the
CDN refuses, their notes and the paragraph on them. It writes:

- ``openapi/portal-document.json``: the GATS part of the portal's document;
- ``openapi/backend-docs-v1.json``: the GATS part of the API's own document;
- ``FETCHED.md``: written whole by the frame, one row per file and per page recorded without
  a file (the two shells and the GATS application's screen-detection page), and the FAS data
  page the CDN refuses to headless clients under ``Not fetched``.

No key is needed or read. Run from the repository root::

    uv run scripts/refresh_upstream.py            # fetch and write
    uv run scripts/refresh_upstream.py --check    # fetch and compare, write nothing
"""

import re

from xippios.core.refresh import Page, Response, Row, Snapshot, changed, parse_json, run
from xippios.usda.fas.portal import Portal, shell_text

PORTAL = Portal("/api/gats/")
"""The portal as GATS's snapshot reads it: its pages first, and its hooks."""

DROP_PREFIXES = ("/api/esr/", "/api/psd/")
"""The other services both documents describe; a path the cut leaves out under any other
prefix stops the run."""
GATS_APP_URL = "https://apps.fas.usda.gov/gats/default.aspx"
"""The GATS application, this package's ``Upstream`` URL, which redirects on its host to a
screen-detection page."""
GATS_APP_MARKER = 'top.location.href="detectscreen.aspx?action=set"'
"""The one script of the screen-detection page, which sends the browser on."""
GATS_APP_NOTE = (
    "screen-detection page, no documentation text: its one script sends the browser on to "
    "`detectscreen.aspx?action=set` with the screen's size"
)
"""The note of the GATS application's row, after the redirect that the frame names."""
FAS_DATA_URL = "https://www.fas.usda.gov/data"
"""The FAS data page, which the CDN edge refuses to headless clients."""

_PREFIX = re.compile(r"/api/[^/]+/")


def reduce(page: Page, response: Response) -> bytes:
    """A document's GATS part, once the paths the cut leaves out are the other two services'.

    The kit cuts the document and holds it to upstream's text; the check reads the document
    as served, since it writes nothing of it.
    """
    content = PORTAL.reduce(page, response)
    paths = parse_json(response)["paths"]
    left = sorted(
        {
            match.group(0) if (match := _PREFIX.match(path)) else path
            for path in paths
            if not path.startswith(PORTAL.prefix)
        }
    )
    if left != sorted(DROP_PREFIXES):
        raise changed(response.url, f"the paths left out are {left}, not {list(DROP_PREFIXES)}")
    return content


def note(row: Row) -> str:
    """The row's note: the GATS application's, once it is still the shell, else the kit's."""
    if row.page.url == GATS_APP_URL:
        shell_text(row.response, GATS_APP_MARKER)
        return GATS_APP_NOTE
    return PORTAL.note(row)


OWN = (
    "The script stops unless the paths that its cut leaves out fall under exactly `/api/esr/` "
    f"and `/api/psd/`. The GATS application page, {GATS_APP_URL}, redirects to a "
    "screen-detection page whose one script sends the browser on, and gets no file, only a row "
    "with its HTTP status and the size and sha256 of its body. The FAS data page, "
    f"{FAS_DATA_URL}, answers 403 Access Denied at the CDN edge to headless clients, a body "
    "that carries a per-request reference number."
)
"""GATS's own paragraph of "How this is captured", after the kit's four."""


SNAPSHOT = Snapshot(
    name="USDA FAS Global Agricultural Trade System",
    slug="usda-gats",
    pages=(
        *PORTAL.pages,
        Page(GATS_APP_URL),
        Page(
            FAS_DATA_URL,
            status=403,
            stable=False,
            names="Access Denied",
            note="the FAS data page; 403 Access Denied at the CDN edge",
        ),
    ),
    capture=f"{PORTAL.capture}\n\n{OWN}",
    reduce=reduce,
    linked=PORTAL.linked,
    note=note,
    sections=PORTAL.sections,
)
"""The snapshot: the portal's shell and its document, the classic Swagger UI and the backend
document it names, the GATS application's screen-detection page, and the FAS data page the CDN
refuses. Neither document states a copyright line, a licence or terms, so the attribution is
empty, and the frame stops a run on a page that comes to state one."""


if __name__ == "__main__":
    raise SystemExit(run(SNAPSHOT))
