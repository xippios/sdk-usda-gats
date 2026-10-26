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
  messages. Core's response cache keeps the two Census release-date lists for an hour
  and the HS10 commodities list for a day, and nothing else (`cache_filter`).
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
  proof with xippios-usda-psd from PyPI and xippios-usda-nass and xippios-usda-esr from
  git main.
- Endpoint wrappers for nine more GATS operations: the reference lists
  `GATSData_GetRegions`, `GATSData_GetCommodities`, `GATSData_GetHS6Commodities`,
  `GATSData_GetUnitsOfMeasure` and `GATSData_GetCustomsDistricts`, and the data
  operations `GATSData_GetCensusReExports`, `GATSData_GetCustomsDistrictsExports`,
  `GATSData_GetCustomsDistrictsImports` and `GATSData_GetCustomsDistrictsReExports`,
  with models from the answers recorded on 2026-10-26 (`Region`, `Commodity`,
  `HS6Commodity`, `UnitOfMeasure`, `CustomsDistrict`, `CustomsDistrictExport`,
  `CustomsDistrictImport`; re-exports reuse `CensusExport`). `Commodity.end_dtate` keeps
  upstream's spelling `endDtate`; the padded seven-digit codes of product types `T` and
  `B` stay as sent. The HS10 commodities answer, 24,936 records, is committed whole as a
  fixture (8.4 MB).
- Four more lists packaged under `reference/` next to `countries.json`, fetched
  2026-10-26 from the recorded answers by `scripts/refresh_reference.py`:
  `regions.json` (15), `HS6Commodities.json` (2,909), `unitsOfMeasure.json` (108) and
  `customsDistricts.json` (53). `enums.UnitOfMeasureId`, an `IntEnum` of the unit ids 0
  to 107 rendered by core's `render_int_enums` (`KILOGRAMS = 47`; the name Crates of ids
  33 and 105 gives `CRATES_33` and `CRATES_105`).
- List tasks answering from the package without a call, as MCP tools
  `usda_gats_list_*` and HTTP routes: `list_regions()`, `list_countries(region_code=None,
  search=None)` (search on code, name, ISO and GENC code; over MCP whole, through a cap
  of 400 rows or 100,000 bytes), `list_hs6_commodities(search=None)` (search on code,
  name and description; over MCP 200 rows or 64 KB with a note naming `search`),
  `list_units_of_measure()` and `list_customs_districts()`. `meta.vintage` is the
  packaged fetch date.
- `list_commodities(search=None, hs10_code=None, product_type=None)`, as MCP tool
  `usda_gats_list_commodities`: the HS10 list, fetched live in one request and filtered
  after it (`search` on name and description, `hs10_code` a prefix, `product_type`
  exact). The client caches `/api/gats/commodities` for a day (`COMMODITIES_TTL`), the
  release-date lists still for an hour: `_client.cache` is `PathCaches`, a
  `CacheBackend` over one `MemoryCache` per TTL. On a hit `meta.retrieved_at` is the
  stored time.
- Tasks `get_census_reexports(partner_code, year, month, hs10_code=None)` and
  `get_customs_district_exports`, `get_customs_district_imports` and
  `get_customs_district_reexports(partner_code, year, month, hs10_code=None,
  customs_district_id=None)`, as MCP tools and HTTP routes, in the Census tasks' shape.
  The imports form checks the imports release list; the exports forms and, by
  assumption, the re-exports forms the exports list, since upstream publishes no
  re-export list; `meta.vintage` is that list's release time for the month.
  `customs_district_id` is checked against the packaged districts
  (`params.validate_customs_district_id`) and applied after the call. Over MCP 200 rows
  or 64 KB with notes naming the filters.
- `params.validate_partner_month`: the six Census data tasks refuse a partner code for a
  month after its `discontinuedOn`, naming the listed codes of the same name: `SZ`
  (Switzerland, 198712) for 2026-08 names `SR`; a month at or before it passes. An
  unknown partner code names an ISO or GENC code's partner code first (`CHN` leads to
  `CH` before `CN`), and the refusal without a close code points to `list_countries`.
  `errors.UnknownCode` words its message over the parameter and the list, so it serves
  `customs_district_id` too. Nothing is released yet, so this is part of 0.1.0's Census
  tasks, not a change to them.
