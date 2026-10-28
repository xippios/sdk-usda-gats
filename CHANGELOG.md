# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

## [0.2.0] - 2026-10-28

The floor of this release is xippios-core 0.3.0 and sdk-template v0.3.0, with
conventions 1.22: it depends on `xippios-core~=0.3.0`, a breaking bound while core is
0.x. The Census data tasks and series and the UN Trade data tasks now set
`meta.published_at` to upstream's release time, kept without a zone; the packaged list
tasks take their `meta` from the packaged list; and the endpoint wrappers carry the
upstream operation names in snake case, while the twenty tasks, their MCP tools and
their HTTP routes keep their names. Two tasks gain a filter, `get_census_release_dates`
and `list_hs6_commodities`; the Census data tasks and series accept for every month the
parent codes GATS marks discontinued; and the client keeps the frozen UN Trade release
lists for a day.

### Added

- `get_census_release_dates(product_type, statistical_year=None)`: `statistical_year`
  keeps one year's months, newest first (2026 gives the eight months 202601 to 202608
  as recorded); a year the list lacks gives an empty list. The filter applies after the
  one request and is recorded in `meta.request`; the MCP tool's note on a cut list names
  it.
- `list_hs6_commodities(search=None, hs6_code=None)`: `hs6_code` keeps the packaged codes
  that start with it, 1 to 6 digits, as `list_commodities`' `hs10_code` does (`"0201"`
  gives the three codes of heading 0201); a prefix no code starts with gives an empty
  list. `meta.request` records it, and the MCP tool's note names it beside `search`.
  `params.validate_hs6_prefix` is its check.

### Changed

- Adopted xippios-core 0.3.0, sdk-template v0.3.0 and conventions 1.22 (conventions §15),
  the §2 name rule included: the nineteen endpoint wrappers and their fixture
  directories now carry the upstream operation name in snake case, without the
  `GATSData_` prefix every operation shares (conventions 1.22 §2, §10).
  `api.GATSData_GetCensusImport` is `api.get_census_import` in
  `api/get_census_import.py`, and `tests/fixtures/GATSData_GetUNTradeExports/` is
  `tests/fixtures/get_un_trade_exports/`. The tasks, the MCP tools and the HTTP routes
  are unchanged, and so is `meta.endpoint`, which keeps upstream's operation id; the CI
  fixture-cap step counts an exact move as a rename, ahead of the same fix in sdk-template.
- **Breaking:** depends on `xippios-core~=0.3.0` and its `mcp`, `http` and `testing`
  extras likewise; a core minor keeps no compatibility with the one before it while core
  is 0.x (conventions §12).
- The Census data tasks and series and the UN Trade data tasks set `meta.published_at` to
  the release record's `releaseTimeStamp`, kept without a zone as FAS prints it, with
  `meta.published_at_naive` set; `meta.vintage` keeps upstream's text. It was `None`.
- The five packaged `list_*` tasks take their `meta` from the packaged list:
  `meta.retrieved_at` is when the package fetched the list (the UTC time of the fetch,
  to the second) and `meta.vintage` is `None`; before, `vintage` held the fetch day and
  `retrieved_at` the time of the call. Every task's `meta.request` leaves out a filter
  left `None`.
- The UN Trade tasks are marked as a frozen series: their README status rows read
  "frozen, last release 2021-01-18" and their docstrings say so.
- The api.data.gov key, the gateway's documented answers and its hourly quota come from
  `xippios.core.data_gov`'s `Gateway`: one quota policy per process for
  `DATA_GOV_API_KEY`, shared with every package behind the gateway in that process, whose
  refusal before sending speaks for `api.data.gov`. `_client.policy` and
  `_client.stored_at` are gone (`Gateway.policy`, `client.get_answer`).
- A code the packaged lists lack is refused with core's `UnknownCode`, its message "... in
  the packaged <list> list (fetched <day>)"; `errors.UnknownCode`, `params.PackagedList`
  and `params.packaged_values` are gone (`xippios.core.UnknownCode`,
  `PackagedList.load(params.PACKAGE, name)`). On core's class `closest` is a tuple of
  `(code, name)` pairs, where it was a list, and `fetched` an aware `datetime`, where it
  was ISO text. A release-list refusal names when the list was fetched, from the cache or
  not.
- The sibling check is the template's: `.github/workflows/siblings.yml` runs
  `.github/scripts/check-siblings.sh`, which finds the siblings on PyPI itself;
  `scripts/check-siblings.sh` is gone. `CLAUDE.md` imports the family rules from
  `.claude/family.md`.
- The client keeps the two UN Trade release-date lists for a day, where it kept them for
  an hour with the Census ones: the UN Trade feed is frozen (statistical year 2019 its
  latest, 2021-01-18 its last release), so a UN task spends one request per flow per day
  on its list. A refusal from the cached UN list says it is kept for a day. The Census
  release lists stay at an hour (`_client.UN_RELEASE_DATES_TTL`,
  `_client.un_release_dates_cache`).
- `list_commodities` parses the HS10 list into records once for each day the client
  keeps it, where it parsed the 24,936 records on every search: the endpoint wrapper
  keeps the records beside the cache entry they came from and returns them for every
  answer from that entry; a new entry is parsed again. `meta.retrieved_at` is still the
  entry's stored time.
- The UN Trade tasks refuse an ISO or GENC code that several listed codes share naming
  first the codes the flow's release list holds as reporters: `get_un_exports("AUS",
  2019)` names `AS`, the code the UN data uses, before `A2`, where it named `A2` first.
  The recorded lists follow no rule on the codes (the parent reports for Australia and
  Norway, the child for France and Switzerland, both for Germany), so such a refusal
  reads the list first, which the task reads anyway, and still comes before the data
  request; when the list cannot be read (no key, a spent quota, the network) the refusal
  comes unranked, never as the list's error. Every other refusal still comes before any
  request, and the Census tasks keep the current code first.
  `params.validate_country_code` and `params.validate_reporter_code` take the
  `reporters` to rank by; `params.shared_three_letter_code` says when a value is such a
  code.
- The three Census series tasks' descriptions, the MCP tools' text, say that the entry
  point `xippios-usda-gats-mcp` starts the MCP server with a ceiling of 24 months, which
  its `--series-months` sets from 1 to 60, against 60 in Python and over HTTP; they said
  the MCP server starts with 24.
- The client's cache stores a body of up to 16 MiB (`_client.CACHE_MAX_BYTES`), twice
  core's default: the HS10 commodities list, 7.6 MB, sat less than 10 % under the
  default, and a list grown past it would no longer have been cached for the day.
- The five packaged lists (regions, countries, HS6 commodities, units of measure and
  customs districts) were refreshed from GATS on 2026-10-28, and no record changed: 15
  regions, 322 countries, 2,909 HS6 codes, 108 units and 53 customs districts, as
  before. Each file's `fetched` is now the UTC time of the fetch to the second, where it
  was a bare day; the refusals that name the list's fetch day name the new day.
  `enums.py` was re-rendered: `UnitOfMeasureId` keeps its name and its 108 members, and
  its docstring names the new day.

### Fixed

- The Census data tasks and series refused every code GATS marks discontinued for the
  months after its `discontinuedOn`, parent codes included, although GATS answers the
  parents recorded for current months: for 2026-08, `Y1` (Leeward-Windward Islands)
  holds every HS10 code of `AC` (Antigua and Barbuda) at no lower a value, and `AS`
  (Australia) answers the records of `A2` apart from the code. A parent, a code another
  record names as its `countryParentCode` (21 of them, 19 discontinued), now passes for
  every month. The seven discontinued codes that are no other code's parent (`D1`, `DA`,
  `GC`, `GE`, `RB`, `YE`, `YS`) are still refused after their month, and the refusal
  says so and names the code's own parent where it has one; `GC` answered 2026-08 with
  an empty list. The two-digit codes of region `R99`, `01` (Caribbean,nes) to `18`
  (ASEAN), are documented as passing; `01` and `18` answered 2026-08 with an empty list,
  which means no data. Eight recorded answers for 2026-08 back this, for `18`, `AS`,
  `A2`, `Y1`, `NF`, `AC`, `GC` and `01`, under `tests/fixtures/get_census_exports/`.

## [0.1.0] - 2026-10-26

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template) v0.2.0: configured
  client for USDA FAS Global Agricultural Trade System, MCP server and FastAPI router wired
  to the task layer, test harness, CI, the nightly live tests and publishing.
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
  `PSD_REQUIREMENT`, `NASS_REQUIREMENT` and `ESR_REQUIREMENT` override each.
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
  `customs_district_id` too.
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
