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
from xippios.usda.gats import get_census_exports, get_census_release_dates
from xippios.usda.gats.models import ProductType

result = get_census_exports("CH", 2026, 8, hs10_code="02")  # US exports to China, August 2026
len(result.data)  # 26: the month's HS10 products of chapter 02, of 777 in all
row = result.data[0]
row.hs10_code, row.value, row.quantity1  # "0201206000", Decimal("30819.0"), Decimal("1018.0")
result.meta.vintage  # "2026-10-06T08:00:00": the month's release time, as upstream states it
result.meta.published_at  # None: upstream's release time carries no time zone
result.meta.request  # {"partner_code": "CH", "year": 2026, "month": 8, "hs10_code": "02"}
result.meta.retrieved_at

releases = get_census_release_dates(ProductType.X)  # X exports, M imports
releases.data[0]  # statistical_year_month="202608", release_time_stamp=2026-10-06 08:00 (naive)
```

`partner_code` is GATS's own two-character code, not ISO (`"CH"` China, `"MX"` Mexico,
`"JA"` Japan, `"IC"` Iceland), checked against the countries list packaged in
`reference/` before any call, since GATS answers an unknown code with an empty list. An
unknown code is refused, naming close codes (an ISO or GENC code leads to its partner
code first: `"CHN"` names `CH` before `CN`) or pointing to `list_countries` when none is
close. A code GATS discontinued (`discontinuedOn`, 26 of them) is refused by the Census
tasks for a month after its last, naming the listed codes of the same name: `"SZ"`
(Switzerland) ended in 198712, so 2026-08 is refused and `SR` named, while 1987-06
passes. `month` is 1 to 12 and `year` four digits; `hs10_code` keeps the products whose
code starts with it, a full ten-digit code for one product or a prefix such as a
chapter, applied after the one data request. `get_census_imports` takes the same
arguments and adds five consumption and CIF fields per record; `get_census_reexports`
answers the exports' record for US re-exports.

The customs-district forms answer the same partner-month by US customs district, one
record per district and HS10 code, and take `customs_district_id` too, checked against
the packaged districts list (an unknown id names the nearest listed ones):

```python
from xippios.usda.gats import get_customs_district_imports

fillets = get_customs_district_imports("IC", 2026, 8, hs10_code="0304", customs_district_id=10)
len(fillets.data)  # 13: fish fillets from Iceland through New York, of 51 in all districts
```

Each data task makes two requests, a release list and the month, or only the second
while the client's cache holds the list, for an hour. The imports forms check the
imports list; the exports forms and the re-exports forms check the exports list, the
latter by assumption, since upstream publishes no re-export release list. A month the
list lacks (not released yet, or before January 1967) raises `NotFoundError` naming the
months released; a listed partner without trade in a released month is an empty list.
`meta.vintage` is the month's release time from that list, as upstream states it
(`"2026-10-06T08:00:00"` for August 2026): upstream's identifier of the release that
last revised the figures, since Census applies corrections once a year and the list
records only each month's latest release. The month itself is in `meta.request` and in
every record's `date`. For up to an hour after a release the cached list may still give
a revised month the previous release's time, or refuse a month just released, and the
refusal says when the list was fetched: an accepted lag. `meta.published_at` stays
`None`: core's `ResultMeta` takes only a timezone-aware time, and FAS states no zone for
its release times, which `get_census_release_dates` returns as upstream states them.

### Month series

The three series tasks answer one partner over a range of months, at most 60, as one
flat list in month order; every record carries its month in `date`:

```python
from xippios.usda.gats import get_census_import_series

fish = get_census_import_series("IC", 2026, 7, 2026, 8, hs10_code="03")  # fish from Iceland
len(fish.data)  # 85: 42 records for July, then 43 for August, each month in upstream order
row = fish.data[0]
row.date, row.hs10_code, row.value  # "202607", "0302140003", Decimal("1252640.0")
fish.meta.vintage  # "2026-10-06T08:00:00": the newest release among the months, August's
fish.meta.request  # the six arguments: partner_code, start_year, ..., hs10_code="03"
```

`get_census_export_series`, `get_census_import_series` and `get_census_reexport_series`
take `partner_code`, `start_year`, `start_month`, `end_year`, `end_month` and
`hs10_code`, which filters every month. Everything is checked before the first request,
the partner code for the start and for the end month, so a code discontinued inside the
range is refused (`"SZ"` for 1987-06 to 1988-01 names 198712); a start after the end or
more than 60 months is refused too. The flow's release list is read once, and every month
of the range must be in it: a range ending in a month not released yet raises
`NotFoundError` naming that month and the latest released, rather than returning the
months that are. `meta.vintage` is the newest release time among the range's months,
which across Census's annual revision can be an earlier month's than the end month's
(2025-12 to 2026-02 gives December's revised `2026-06-24T08:00:00`);
`get_census_release_dates` has each month's own.

**Pacing.** A series spends one keyed request per month, plus the release list unless
the client's cache holds it, and sends them one after another at the client's pace of
one request per second, never at once: 60 months take about a minute and 60 of the
key's 1,000 requests per hour. A quota spent partway raises `RateLimitError`, and none of
the months is returned.

## UN Trade data

> **The UN half of GATS is frozen.** As recorded on 2026-10-26, both UN Trade release
> lists end with statistical year 2019, and their newest release is dated 2021-01-18: no
> later year has appeared since. The package wraps this data faithfully, as GATS serves
> it, so that a product-level comparison with UN Comtrade is possible elsewhere; it maps
> no code. Reporter, partner and HS6 codes stay GATS's own (`list_countries`,
> `list_hs6_commodities`), not UN Comtrade's and not ISO.

GATS serves trade "as reported by UN COMTrade", one reporter and one statistical year per
request, one record per partner and HS6 code:

```python
from xippios.usda.gats import get_un_exports, get_un_release_dates
from xippios.usda.gats.models import ProductType

fish = get_un_exports("IC", 2019, hs6_code="03")  # Iceland's 2019 exports, HS chapter 03
len(fish.data)  # 1024 records, partner by partner, of 3,980 for the whole year
row = fish.data[0]
row.partner_country_code, row.hs6_code, row.value  # "AE", "030211", Decimal("10620.0")
fish.meta.vintage  # "2020-06-03T05:50:46": Iceland 2019's release time in the exports list
fish.meta.request  # {"reporter_code": "IC", "year": 2019, "partner_code": None, "hs6_code": "03"}

coverage = get_un_release_dates(ProductType.X, reporter_code="IC")
[r.statistical_year for r in coverage.data]  # ["2019", "2018", ..., "1989"]: 31 years
```

`get_un_exports`, `get_un_imports` and `get_un_reexports` take `reporter_code`, `year`
and two filters applied after the one data request, `partner_code` (exact) and
`hs6_code` (a full code from the packaged HS6 list, or a prefix of 1 to 5 digits). The
records keep GATS's codes as the data carries them, older ones included: the countries
list marks `AS` (Australia), `DA` (Denmark), `IT` (Italy), `NO` (Norway) and `NZ` (New
Zealand) discontinued in 1987, yet the UN data uses them for later years and never their
same-name successors (`A2`, `N3`, ...). So the UN tasks check both country codes for
membership in the packaged list only; the Census tasks' discontinuation rule does not
apply. Before the data request a task checks the reporter-year against the flow's UN
release list: the imports task the imports list, the exports task and, by assumption,
the re-exports task the exports list, since upstream publishes no re-export list. GATS
answers an unknown reporter, a future year and an unreleased year alike with an empty
list, so a reporter-year the list lacks raises `NotFoundError` naming the reporter's
listed years and the latest year; a listed reporter-year without trade is an empty list
(Iceland's 2019 re-exports). `meta.vintage` is the reporter-year's release time as
upstream states it; `meta.published_at` stays `None`, as for the Census tasks. One
reporter-year can be large: Iceland's 2019 imports are 23,396 records (about 5.2 MB),
India's 2016 exports 75,919 (about 17 MB). `get_un_release_dates(product_type,
reporter_code=None, year=None)` returns either list, one record per reporter and year,
3,796 for exports and 3,832 for imports as recorded.

## Reference lists

Five GATS lists ship with the package under `reference/`, and their `list_*` tasks
answer from them without a call; `meta.vintage` is the day the package fetched the
list, `meta.retrieved_at` when the task answered:

```python
from xippios.usda.gats import list_countries, list_hs6_commodities
from xippios.usda.gats.enums import UnitOfMeasureId

list_countries(search="CHN").data  # [Country(country_code="CH", ..., iso3_code="CHN", ...)]
list_countries(region_code="R05").data  # CA, GL, MX, SB, US (North America)
list_hs6_commodities(search="0201").data  # the three HS6 codes of heading 0201
UnitOfMeasureId.KILOGRAMS  # 47, the unit id of the data records
```

`list_regions()` (15), `list_countries(region_code=None, search=None)` (322 codes,
current and discontinued; `search` on the code, the name, the ISO and the GENC code),
`list_hs6_commodities(search=None)` (2,909; `search` on the code, the name and the
description), `list_units_of_measure()` (108, ids 0 to 107, which `enums.UnitOfMeasureId`
names) and `list_customs_districts()` (53, e.g. 10 NEW YORK, N.Y.).

The HS10 list is not packaged: 24,936 records and about 7.6 MB. `list_commodities(search=None,
hs10_code=None, product_type=None)` fetches it live, in one request the client keeps for
a day, and filters it: `search` on the name and the description, `hs10_code` a prefix of
the code, `product_type` exact. Upstream's product types are `"X"` (exports, 5,919
records), `"M"` (imports, 14,469), `"T"` (2,704) and `"B"` (1,844); upstream documents
none of them, and the `T` and `B` records carry seven-digit codes padded with three
spaces, kept as sent. On a cache hit `meta.retrieved_at` is when the list was fetched.

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
200 rows or 64 KB unless a tool has a cap of its own, with a note on the rows left out
that names the tool's filters: one partner-month is one row per HS10 product (777 rows
for exports to China in August 2026, 3,294 for imports, 1,697 by customs district), so
the notes of the Census data tools name `hs10_code`, and those of the customs-district
tools `customs_district_id` too, while the series tools' notes say the rows run oldest
month first and name `hs10_code` and fewer months; `usda_gats_list_hs6_commodities`
names `search`, `usda_gats_list_commodities` its three filters. The UN Trade data tools name
`partner_code` and `hs6_code` (one reporter-year is one row per partner and HS6 code,
3,980 rows for Iceland's 2019 exports), and `usda_gats_get_un_release_dates` names
`reporter_code` and `year` (3,796 reporter-years in the exports list).
`usda_gats_list_countries` has a cap of its own, 400 rows or 100,000 bytes, so its 322
codes arrive whole. `usda_gats_get_census_release_dates`, which has no filter, returns
the newest 200 months, more than sixteen years, with a note that says so. `--http`
serves streamable HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `GATSData_GetCensusExports` (`censusExports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_census_exports(partner_code, year, month, hs10_code=None)` | `usda_gats_get_census_exports` | alpha |
| `GATSData_GetCensusImport` (`censusImports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_census_imports(partner_code, year, month, hs10_code=None)` | `usda_gats_get_census_imports` | alpha |
| `GATSData_GetCensusReExports` (`censusReExports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_census_reexports(partner_code, year, month, hs10_code=None)` | `usda_gats_get_census_reexports` | alpha |
| `GATSData_GetCensusExports`, one request per month | `get_census_export_series(partner_code, start_year, start_month, end_year, end_month, hs10_code=None)`, at most 60 months | `usda_gats_get_census_export_series` | alpha |
| `GATSData_GetCensusImport`, one request per month | `get_census_import_series(partner_code, start_year, start_month, end_year, end_month, hs10_code=None)`, at most 60 months | `usda_gats_get_census_import_series` | alpha |
| `GATSData_GetCensusReExports`, one request per month | `get_census_reexport_series(partner_code, start_year, start_month, end_year, end_month, hs10_code=None)`, at most 60 months | `usda_gats_get_census_reexport_series` | alpha |
| `GATSData_GetCustomsDistrictsExports` (`customsDistrictExports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_customs_district_exports(partner_code, year, month, hs10_code=None, customs_district_id=None)` | `usda_gats_get_customs_district_exports` | alpha |
| `GATSData_GetCustomsDistrictsImports` (`customsDistrictImports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_customs_district_imports(partner_code, year, month, hs10_code=None, customs_district_id=None)` | `usda_gats_get_customs_district_imports` | alpha |
| `GATSData_GetCustomsDistrictsReExports` (`customsDistrictReExports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_customs_district_reexports(partner_code, year, month, hs10_code=None, customs_district_id=None)` | `usda_gats_get_customs_district_reexports` | alpha |
| `GATSData_GetCensusExportDataReleaseInfo` (`census/data/exports/dataReleaseDates`) | `get_census_release_dates("X")`; read by the exports and re-exports tasks and series too | `usda_gats_get_census_release_dates` | alpha |
| `GATSData_GetCensusImportDataReleaseInfo` (`census/data/imports/dataReleaseDates`) | `get_census_release_dates("M")`; read by the imports tasks and series too | `usda_gats_get_census_release_dates` | alpha |
| `GATSData_GetUNTradeExports` (`UNTradeExports/reporterCode/{reporterCode}/year/{year}`) | `get_un_exports(reporter_code, year, partner_code=None, hs6_code=None)` | `usda_gats_get_un_exports` | alpha |
| `GATSData_GetUNTradeImports` (`UNTradeImports/reporterCode/{reporterCode}/year/{year}`) | `get_un_imports(reporter_code, year, partner_code=None, hs6_code=None)` | `usda_gats_get_un_imports` | alpha |
| `GATSData_GetUNTradeReExports` (`UNTradeReExports/reporterCode/{reporterCode}/year/{year}`) | `get_un_reexports(reporter_code, year, partner_code=None, hs6_code=None)` | `usda_gats_get_un_reexports` | alpha |
| `GATSData_GetUNTradeExportDataReleaseInfo` (`UNTrade/data/exports/dataReleaseDates`) | `get_un_release_dates("X", reporter_code=None, year=None)`; read by the UN exports and re-exports tasks too | `usda_gats_get_un_release_dates` | alpha |
| `GATSData_GetUNTradeImportDataReleaseInfo` (`UNTrade/data/imports/dataReleaseDates`) | `get_un_release_dates("M", reporter_code=None, year=None)`; read by the UN imports task too | `usda_gats_get_un_release_dates` | alpha |
| `GATSData_GetCommodities` (`commodities`) | `list_commodities(search=None, hs10_code=None, product_type=None)`, live, cached for a day | `usda_gats_list_commodities` | alpha |
| `GATSData_GetRegions` (`regions`) | `list_regions()`, packaged as `reference/regions.json` | `usda_gats_list_regions` | alpha |
| `GATSData_GetCountries` (`countries`) | `list_countries(region_code=None, search=None)`, packaged as `reference/countries.json`, which checks the Census `partner_code` and the UN Trade `reporter_code` and `partner_code` filter | `usda_gats_list_countries` | alpha |
| `GATSData_GetHS6Commodities` (`HS6Commodities`) | `list_hs6_commodities(search=None)`, packaged as `reference/HS6Commodities.json`, which checks a six-digit `hs6_code` | `usda_gats_list_hs6_commodities` | alpha |
| `GATSData_GetUnitsOfMeasure` (`unitsOfMeasure`) | `list_units_of_measure()`, packaged as `reference/unitsOfMeasure.json`; `enums.UnitOfMeasureId` | `usda_gats_list_units_of_measure` | alpha |
| `GATSData_GetCustomsDistricts` (`customsDistricts`) | `list_customs_districts()`, packaged as `reference/customsDistricts.json`, which checks `customs_district_id` | `usda_gats_list_customs_districts` | alpha |

All nineteen operations of the snapshot (`docs/upstream/`) are wrapped.
Alpha: the public surface may change in a minor version before 1.0 (conventions §12);
`CHANGELOG.md` lists every change.

Every request counts against api.data.gov's quota of 1,000 requests per hour per key,
shared by every package using the same `DATA_GOV_API_KEY` (xippios-usda-psd and
xippios-usda-esr among them); a release list answered from the client's cache spends
none, and so does the commodities list answered from it within its day. A month series
spends one request per month. The client
keeps its own pace of one request per second; once the quota is spent it
waits for the quota to come back when that takes at most 30 s, and otherwise raises
`RateLimitError` with `retry_after` instead of sending.

## Upstream terms and attribution

Data comes from USDA FAS Global Agricultural Trade System (https://apps.fas.usda.gov/gats/default.aspx) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
