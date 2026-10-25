# xippios-usda-gats

Typed Python client, MCP server and FastAPI routes for
[USDA FAS Global Agricultural Trade System](https://apps.fas.usda.gov/gats/default.aspx), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries release metadata (source, endpoint,
retrieved_at, published_at, vintage).

## Install

```bash
uv add xippios-usda-gats            # client only
uv add "xippios-usda-gats[mcp]"     # + MCP server
uv add "xippios-usda-gats[http]"    # + FastAPI router
```

Set `DATA_GOV_API_KEY` in the environment. Nothing is read from files.

## 30-second example

```python
from xippios.usda.gats import tasks

# result = tasks.<task>(...)
# result.data, result.meta.retrieved_at, result.meta.request
```

Task functions are listed in the status table below as they are added.

## MCP

```json
{
  "mcpServers": {
    "usda-gats": {
      "command": "uvx",
      "args": ["--from", "xippios-usda-gats[mcp]", "xippios-usda-gats-mcp"],
      "env": { "DATA_GOV_API_KEY": "..." }
    }
  }
}
```

Tools are read-only and named `usda_gats_<verb>_<noun>`. Results are capped, at
200 rows or 64 KB unless a tool has a cap of its own, with a note on how to see the rest.
`--http` serves streamable HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| (none yet) | | | |

## Upstream terms and attribution

Data comes from USDA FAS Global Agricultural Trade System (https://apps.fas.usda.gov/gats/default.aspx) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
