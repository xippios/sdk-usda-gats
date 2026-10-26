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
  proof, this wheel installed with xippios-usda-psd, xippios-usda-nass and
  xippios-usda-esr, all three from PyPI, as portions of the `xippios.usda` namespace;
  `PSD_REQUIREMENT`, `NASS_REQUIREMENT` and `ESR_REQUIREMENT` override each. nass and esr
  came from git main until their 0.1.0 was published.
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
- Endpoint wrappers for the five UN Trade operations, named after the snapshot's
  operationIds: `GATSData_GetUNTradeExports`, `GATSData_GetUNTradeImports` and
  `GATSData_GetUNTradeReExports` (path parameters `reporterCode` and `year`, both text as
  the snapshot types them), and the release-date lists
  `GATSData_GetUNTradeExportDataReleaseInfo` and
  `GATSData_GetUNTradeImportDataReleaseInfo`, with models from the answers recorded on
  2026-10-26: `UNTradeRecord` (eleven fields, one record per partner and HS6 code, the
  same for all three flows) and `UNTradeDataReleaseInfo` (one record per reporter and
  statistical year, `statisticalYear` text). The client caches the two UN release lists
  for an hour with the Census ones.
- Tasks `get_un_exports`, `get_un_imports` and `get_un_reexports(reporter_code, year,
  partner_code=None, hs6_code=None)`, as MCP tools `usda_gats_get_un_*` and HTTP routes:
  one reporter and one statistical year across every partner and HS6 code, in GATS's own
  codes, nothing mapped onto another source's (ADR-0003). The UN Trade data is frozen
  upstream: as recorded on 2026-10-26 both release lists end with 2019, their newest
  release dated 2021-01-18. The arguments are checked first, the two country codes for
  membership only; the flow's UN release list then refuses a reporter-year it lacks as
  `NotFoundError` naming the reporter's listed years and the list's latest year. The
  imports task checks the imports list, the exports task and, by assumption, the
  re-exports task the exports list. `meta.vintage` is the reporter-year's
  `releaseTimeStamp` as upstream states it; `meta.published_at` stays `None`.
  `partner_code` (exact) and `hs6_code` (a prefix) apply after the one data request; over
  MCP 200 rows or 64 KB with a note naming both.
- Task `get_un_release_dates(product_type, reporter_code=None, year=None)`, as MCP tool
  `usda_gats_get_un_release_dates` and HTTP route: the UN exports (`"X"`) or imports
  (`"M"`) release list, filtered by reporter or year after the one request; a cache hit's
  stored time is `meta.retrieved_at`. Over MCP 200 rows or 64 KB with a note naming both
  filters. `ProductType`'s docstring now covers both programs' lists.
- `params.validate_country_code(code, param, reason=...)`, the countries-list membership
  check named by its parameter, which `validate_partner_code` (Census) and the new
  `validate_reporter_code` (UN Trade) call; `params.validate_hs6_code`, 1 to 6 digits, a
  full code from the packaged HS6 list, refused otherwise as `UnknownCode` naming the
  listed codes that share its leading digits (`"020119"` names `020110`, `020120`,
  `020130`). `UnknownCode` carries a reason per use (`errors.REPORTER_REASON`,
  `UN_PARTNER_REASON`, `HS6_REASON`), and the year message names both data series.
- Tasks `get_census_export_series`, `get_census_import_series` and
  `get_census_reexport_series(partner_code, start_year, start_month, end_year, end_month,
  hs10_code=None)`, as MCP tools `usda_gats_get_census_*_series` and HTTP routes: one
  partner over a range of months, one data request per month, oldest first, one after
  another at the client's pace, never concurrently. A call spans at most
  `tasks.series_ceiling()` months: 60 in Python and over HTTP (`tasks.SERIES_MAX_MONTHS`)
  and 24 over MCP by default (`tasks.MCP_SERIES_MAX_MONTHS`), where the MCP server's
  `--series-months MONTHS`, 1 to 60, sets another. The entry point `xippios-usda-gats-mcp`
  sets the MCP ceiling: core's `main` applies the option through the hooks
  `tasks.mcp_add_options` and `tasks.mcp_apply_options` (ADR-0014), which `mcp.py` passes
  as it passes `MCP_CAPS`, so a host that imports `xippios.usda.gats.mcp.server` and
  serves it another way keeps 60. The ceiling is process-wide, so a Python or HTTP call
  made inside an MCP server's process meets the MCP ceiling too: `tasks.series_ceiling()`
  reads it, `tasks.set_series_ceiling(months)` sets it and refuses anything but a whole
  number from 1 to 60 as `InvalidRequestError`, which stops the server at start with exit
  status 2. Every argument is checked before any call, the partner code through
  `validate_partner_month` for the start and the end month, so a code discontinued inside
  the range is refused; a start after the end, or a range longer than the ceiling, is
  `InvalidRequestError`, the latter naming the ceiling in force and, below 60, that it is
  the ceiling set for this process and that `--series-months` raises it. The flow's
  release list is fetched once (exports for exports and, by assumption, re-exports;
  imports for imports), and a range with a month the list lacks is refused whole as
  `NotFoundError` naming the first such month and the latest released, never trimmed.
  The records come back as one list in month order, `hs10_code` applied to every month, a
  month without trade adding nothing. `meta.vintage` is the newest release time among
  the range's months, as upstream states it; `meta.published_at` stays `None`. Over MCP
  200 rows or 64 KB with a note naming `hs10_code` and fewer months.
