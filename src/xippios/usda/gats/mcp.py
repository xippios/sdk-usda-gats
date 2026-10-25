"""MCP server for USDA FAS Global Agricultural Trade System.

Every task in ``tasks.__all__`` is a read-only tool. No logic lives here (ADR-0001).
Entry point: ``xippios-usda-gats-mcp``.
"""

from xippios.core.mcp import build_server, main

from xippios.usda.gats import tasks
from xippios.usda.gats._client import SOURCE
from xippios.usda.gats._version import __version__

INSTRUCTIONS = (
    "USDA FAS Global Agricultural Trade System via xippios. "
    "Tools are read-only. Where list tools (usda_gats_list_*) exist, "
    "call them first to find valid codes, then query."
)

server = build_server(
    SOURCE,
    [getattr(tasks, name) for name in tasks.__all__],
    version=__version__,
    instructions=INSTRUCTIONS,
    caps=getattr(tasks, "MCP_CAPS", None),
)


def run() -> None:
    """Run the server: stdio by default, ``--http`` for streamable HTTP."""
    main(server)
