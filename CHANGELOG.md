# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for USDA FAS Global Agricultural Trade System, empty task layer, MCP server and FastAPI router
  wired to it, test harness, CI, the nightly live tests and publishing.
- Upstream documentation snapshot in `docs/upstream/` (2026-10-25): the GATS part of
  the FAS Open Data Services Swagger 2.0 document as the portal loads it
  (`openapi/portal-document.json`) and as the API serves it itself
  (`openapi/backend-docs-v1.json`), nineteen `/api/gats/` operations each, the ESR and
  PSD paths left out. `FETCHED.md` records the full documents' sizes and sha256 and the
  pages that hold no documentation text.
- `scripts/refresh_upstream.py`: regenerates the snapshot reproducibly, stdlib only and
  without a key (`uv run scripts/refresh_upstream.py`); `Fetched` is the UTC time of the
  run.
- The api.data.gov gateway client (`_client.py`), in sdk-usda-psd's adopted shape:
  `X-Api-Key` from `DATA_GOV_API_KEY`, a self-imposed pace of 60 requests per minute,
  core's `QuotaPolicy` on the gateway's hourly quota (ADR-0010, ADR-0015), and `classify`
  for the gateway's `API_KEY_*`, `OVER_RATE_LIMIT` and `NOT_FOUND` answers with host-free
  messages. Core's response cache keeps the two Census release-date lists, and nothing
  else, for an hour (`cache_filter`).
- Endpoint wrappers for five GATS operations, named after the snapshot's operationIds:
  `GATSData_GetCountries`, `GATSData_GetCensusExportDataReleaseInfo`,
  `GATSData_GetCensusImportDataReleaseInfo`, `GATSData_GetCensusExports` and
  `GATSData_GetCensusImport`, with models from the recorded answers (`Country`,
  `DataReleaseInfo`, `CensusExport`, `CensusImport`; quantities and values `Decimal`) and
  `ProductType`, upstream's `productType` codes `X` (exports) and `M` (imports).
- Tasks `get_census_exports(partner_code, year, month, hs10_code=None)` and
  `get_census_imports(partner_code, year, month, hs10_code=None)`, as MCP tools
  `usda_gats_get_census_exports` and `usda_gats_get_census_imports` and HTTP routes: one
  partner and one month across every HS10 product. The arguments are checked before any
  call; the flow's release list (cached for an hour) refuses a month it lacks as
  `NotFoundError` naming the months released; `hs10_code` keeps the products whose code
  starts with it. `meta.vintage` is the month's release time from that list, as
  upstream states it (`"2026-10-06T08:00:00"` for 2026-08), the release that last
  revised the figures; for up to an hour after a release the cached list may still give
  the previous release's time. The month itself is in `meta.request`.
  `meta.published_at` stays `None`, since `ResultMeta` takes only an aware time and FAS
  states no zone. An empty list for a listed partner in a released month is an empty
  result. Over MCP both keep 200 rows or 64 KB with a note naming `hs10_code`
  (`tasks.MCP_CAPS`, ADR-0016).
- Task `get_census_release_dates(product_type)`, as MCP tool
  `usda_gats_get_census_release_dates` and HTTP route: the exports (`"X"`) or imports
  (`"M"`) release list, one record per month with the time of its latest release as
  upstream states it; a cache hit's stored time is `meta.retrieved_at`. Over MCP it
  keeps 200 rows or 64 KB, with a note that the rows shown are the newest months.
- The GATS countries list packaged as `reference/countries.json` (322 records, fetched
  2026-10-25) by `scripts/refresh_reference.py`, and `params.validate_partner_code`,
  which refuses a code the list lacks as `errors.UnknownCode`, an `InvalidRequestError`
  naming close codes, or example codes when none is close: GATS answers an unknown
  partner with an empty list.
  `params.validate_year`, `validate_month` and `validate_hs10_code` check the other
  arguments.
- `scripts/check-siblings.sh` and `.github/workflows/siblings.yml`: the ADR-0006 sibling
  proof with xippios-usda-psd from PyPI and xippios-usda-nass from git main.
