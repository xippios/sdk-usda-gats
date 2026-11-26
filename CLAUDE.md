# sdk-usda-gats — instructions for Claude Code

`xippios-usda-gats` wraps USDA FAS Global Agricultural Trade System as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and what only it knows. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file. The
rules that no change breaks stand in `.claude/rules/never.md`, which Claude Code loads with
this file.

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA FAS Global Agricultural Trade System, https://apps.fas.usda.gov/gats/default.aspx |
| API base URL | `https://api.fas.usda.gov` |
| Documentation | https://apps.fas.usda.gov/opendatawebV2/, snapshotted in `docs/upstream/` |
| Credentials | `DATA_GOV_API_KEY` from the environment, sent as the `X-Api-Key` header by the `Gateway` of `xippios.usda.fas`, the shared package of the FAS sources (`_client.auth` is `gateway.auth`); the key is api.data.gov's, shared by every package that reads it (sdk-core ADR-0032) |
| Rate limit | 60 requests per minute, burst 1; a self-imposed pace: upstream documents no per-second or per-minute limit (sdk-core ADR-0033); enforced client-side in `_client.py`. The hourly quota is the gateway's, 1,000 requests per rolling hour for the key (`x-ratelimit-limit` on every keyed answer recorded), shared by every package on the key: one `QuotaPolicy` per process, `Gateway.policy` of `xippios.usda.fas`, which once the quota is spent waits within 30 s or refuses before sending, a refusal that says `quota spent` and speaks for `api.data.gov` (sdk-core ADR-0032, sdk-core ADR-0033, sdk-core ADR-0037) |
| Response cache | core's `MemoryCache` with a lifetime per path prefix, `LIFETIMES` in `_client.py`, for every answer, by the maintainer's decision of 2026-11-26 (https://github.com/xippios/sdk-usda-gats/issues/57, part 7; sdk-core ADR-0061, decisions 9 and 11): core's default of 300 s for every path, so that a narrower filter on an answer already read and the next rows of a cut tool send no request; the two Census release-date lists for an hour, since every Census data task reads its flow's list first; every UN Trade answer, its data and its two release-date lists, for a day, since that feed is frozen; and the HS10 commodities list for a day. `cache_max_bytes` is 16 MiB, twice core's default of 8 MiB, because the HS10 list, 7,592,916 bytes as recorded, sits 9.5 % under the default and would silently stop being cached if a refresh grew it past (sdk-core ADR-0040, decision 3); `tests/test_client.py` fails once the recorded list passes 75 % of the bound. A larger answer, as one UN Trade reporter-year can be, is not stored, so the UN Trade data tools and the series take no paged cap |
| Write tools | no, this package is read-only |
| Depends on | `xippios-usda-fas~=0.1.0`, key `DATA_GOV_API_KEY`: a source package's task layer and its models only, never `api/` or `_client`, and this package's servers serve its own tasks, so an agent that wants that source's tools runs its server (sdk-core ADR-0021); a publisher's shared package's public names (sdk-core ADR-0065 decision 3). The package takes from it the api.data.gov gateway, `Gateway` and `API_KEY_ENV`, for `_client.py`, `REMAINING_HEADER` for the reference script, and the kit of the FAS portal, `Portal` and `shell_text` of `xippios.usda.fas.portal`, for the snapshot script (sdk-core ADR-0021, decision 6) |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API.

## Layout

What this package adds to the family's tree, and its import path, stand in `docs/layout.md`,
imported here:

@docs/layout.md

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 -I scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1, DATA_GOV_API_KEY

uv run xippios-usda-gats-mcp   # stdio; add --http for streamable HTTP
```

`.github/workflows/live.yml` runs the live tests nightly at 02:57 UTC, a time derived from
the slug so that sources sharing a key never start together, and on demand; a pull request never runs them.
Only its `uv run pytest -m live --tb=short --assert=plain` step sees the key, from the org secret `DATA_GOV_API_KEY`.
Every live run takes `--tb=short --assert=plain`, since the log of `live.yml` is public:
the first keeps a failing test's frame arguments out of it, a raw upstream payload among
them, and the second the values a failed `assert` compares. A live test asserts on shapes
and counts, never on a raw payload.

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15). The
update never overwrites a file this package fills, those that `_skip_if_exists` lists in
sdk-template's [`copier.yml`](https://github.com/xippios/sdk-template/blob/main/copier.yml),
and sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

The update writes every other file it renders again, since they are the template's,
`.claude/rules/never.md` among them. This package keeps no text of its own in them, the
docstring of `mcp.py` included: its own words go into a file it fills. A line it has to
add to one, such as a dependency in `pyproject.toml`, the update carries into the new
render, silently where the release leaves the lines around it alone and as a conflict
where it changes them.

## USDA FAS Global Agricultural Trade System specifics

`_client.py` builds on the `Gateway` of `xippios.usda.fas` (sdk-core ADR-0032, decision 5;
sdk-core ADR-0065, decision 1), which holds what every source behind api.data.gov shares: the
`X-Api-Key` auth, the one `QuotaPolicy` per process on `x-ratelimit-*` and the `API_KEY_*`,
`OVER_RATE_LIMIT` and `NOT_FOUND` mappings with host-free messages, tested in the shared
package. `Gateway(SOURCE)` names no data path: GATS answers a month or a year without data
with `[]` and never with FAS's empty 404, so no answer of GATS's is the shared package's
`NoDataForYear`. `classify` asks `gateway.classify` first and maps nothing of GATS's own.

The series' ceiling is `tasks.SERIES`, core's one `Ceiling`: 60 months in Python and over
HTTP, 24 on the MCP server and `--series-months` to set another, its hooks
`tasks.mcp_add_options` and `tasks.mcp_apply_options`, which the tool set carries (sdk-core
ADR-0054, ADR-0063, decision 7).
