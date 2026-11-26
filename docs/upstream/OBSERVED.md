# What GATS does but never documents

Notes, written by hand, on what USDA FAS Global Agricultural Trade System's API does that no
page of this snapshot states (sdk-core's conventions §3, sdk-core ADR-0028). The two Swagger
documents under `openapi/` are the reference for names and parameters: they type
`partnerCode` and `reporterCode` as strings, the Census `year` and `month` as `int32` and the
UN Trade `year` as a string, describe every operation's answer as HTTP 200 with a schema of
`type: object`, define no schema beside it and list JSON and XML among the forms that each
operation produces. The answers' shapes, GATS's empty answers and the gateway's refusals
below come from the wire, and `models.py`, the checks of `params.py`, `_client.classify`
and `tests/fixtures/` follow it. `scripts/refresh_upstream.py` neither writes nor checks
this file, and `FETCHED.md` lists it in a row of its own.

Each note ends with its probe: the date, the operation by the `operationId` the snapshot
gives it, and the sample, a fixture named by its path under `tests/fixtures/`, whose
`recorded_at` gives the time of the request. A probe that kept no answer says so and names
its request. The notes moved here on 2026-11-26 from the README and the docstrings of the
package's modules, the measures that left the tools' descriptions among them; no request
was sent to write this file.

## The answers' shapes

### A Census record

An answer of `GATSData_GetCensusExports` holds one record per HS10 code that the partner
traded that month, in code order, each with `date`, the statistical month as six digits
(`"202608"`), `countryCode`, `hS10Code`, four unit ids (`censusUOMId1`, `censusUOMId2`,
`fasConvertedUOMId` and `fasNonConvertedUOMId`), `quantity1`, `quantity2` and `value`, the
last three JSON numbers with one fractional digit (`20672.0`). No field names a currency
or a release. `GATSData_GetCensusImport` answers the same fields and five before them,
`consumptionQuantity1`, `consumptionQuantity2`, `consumptionValue`, `consumptionCIFValue`
and `cifValue`, and `GATSData_GetCensusReExports` the exports' fields alone.

Exports to China in August 2026 were 777 records and 153,835 bytes of JSON, imports from
China 3,294 records and 1,099,638 bytes. Iceland's August exports were 92 records, its
imports 74 and its re-exports 12, four of them in chapter 62, the largest; its July answers
were 105, 83 and 19 records. So a series over July and August 2026 holds 197 exports
records, 157 imports records, 85 of them fish (HS10 codes under `03`), and 31 re-exports
records, 7 of them in chapter 62.

Probe: 2026-10-25 and 2026-10-26, `GATSData_GetCensusExports`, `GATSData_GetCensusImport`
and `GATSData_GetCensusReExports`; samples
`tests/fixtures/get_census_exports/CH_2026_8.json` and
`tests/fixtures/get_census_import/CH_2026_8.json`, recorded 2026-10-25, and
`tests/fixtures/get_census_exports/IC_2026_8.json`,
`tests/fixtures/get_census_exports/IC_2026_7.json`,
`tests/fixtures/get_census_import/IC_2026_8.json`,
`tests/fixtures/get_census_import/IC_2026_7.json`,
`tests/fixtures/get_census_re_exports/IC_2026_8.json` and
`tests/fixtures/get_census_re_exports/IC_2026_7.json`, recorded 2026-10-26.

### A customs-district record

The three customs-district operations answer one record per US customs district and HS10
code, the Census record of the same flow with `customsDistrictId` before its fields, an
integer of `GATSData_GetCustomsDistricts`. Each code's values add up across the districts
to its value in the Census answer of the same flow, partner and month. For August 2026
Iceland's exports were 107 records in 14 districts, 16 of them in district 10 (NEW YORK,
N.Y.), and China's 1,697 in 31 districts; Iceland's imports were 123 records in 21
districts, 28 of them in district 10 and 51 fish fillets (HS10 codes under `0304`), 13 of
the fillets in district 10, and its re-exports 13 records in 5 districts, 5 of them in
district 10.

Probe: 2026-10-26, `GATSData_GetCustomsDistrictsExports`,
`GATSData_GetCustomsDistrictsImports` and `GATSData_GetCustomsDistrictsReExports`, against
the Census answers of the same day; samples
`tests/fixtures/get_customs_districts_exports/IC_2026_8.json`,
`tests/fixtures/get_customs_districts_exports/CH_2026_8.json`,
`tests/fixtures/get_customs_districts_imports/IC_2026_8.json` and
`tests/fixtures/get_customs_districts_re_exports/IC_2026_8.json`.

### A UN Trade record

`GATSData_GetUNTradeExports` and its two siblings answer one record per partner and HS6
code, each with `year` as text (`"2019"`), `reporterCountryCode`, `partnerCountryCode`,
`hS6Code`, the four unit ids, `quantity1`, `quantity2` and `value`, JSON numbers. The codes
are GATS's own, as `GATSData_GetCountries` and `GATSData_GetHS6Commodities` list them,
never UN Comtrade's and never ISO, and a partner can be a region code of `R99`, `"15"`
(Areas, not elsewhere specified). Iceland's 2019 exports were 3,980 records and 884,964
bytes, 646 HS6 codes to 115 partners, 1,024 of the records in chapter 03; Sao Tome and
Principe's 2019 imports 2,377 records, 1,026 HS6 codes from 58 partners, 957 of the records
from Portugal (`"PO"`); and Macau's 2019 re-exports 421 records, every quantity 0, 27 of
them to `"AS"`.

Probe: 2026-10-26, `GATSData_GetUNTradeExports`, `GATSData_GetUNTradeImports` and
`GATSData_GetUNTradeReExports`; samples `tests/fixtures/get_un_trade_exports/IC_2019.json`,
`tests/fixtures/get_un_trade_imports/TP_2019.json` and
`tests/fixtures/get_un_trade_re_exports/MC_2019.json`.

### One UN Trade answer is a reporter's whole year

A UN Trade answer is one reporter-year across every partner and product and has no paging:
Iceland's 2019 imports were 23,396 records and about 5.2 MB of JSON, India's 2016 exports
75,919 records and about 17 MB, more than the 16 MiB that the client's cache stores.

Probe: 2026-10-26, `GATSData_GetUNTradeImports` for `IC` and 2019 and
`GATSData_GetUNTradeExports` for `IN` and 2016; both answers were measured and not kept.

### The UN data keeps codes discontinued in 1987

The countries list marks `AS` (Australia), `DA` (Denmark), `IT` (Italy), `NO` (Norway) and
`NZ` (New Zealand) discontinued in 1987, yet the UN Trade answers for 2019 carry them and
never their successors of the same name (`A2`, `N3`, ...). The UN Trade release lists follow
no rule on the codes themselves: both hold `AS` and never `A2` (Australia), `NO` and never
`N3` (Norway), but `F1` and never `FR` (France), `SR` and never `SZ` (Switzerland), and both
`GM` and `GE` (Germany), `GE` to 1990 and `GM` from 1991.

Probe: 2026-10-26, `GATSData_GetUNTradeExports`, `GATSData_GetUNTradeImports`,
`GATSData_GetUNTradeReExports`, `GATSData_GetUNTradeExportDataReleaseInfo` and
`GATSData_GetUNTradeImportDataReleaseInfo`, against `GATSData_GetCountries` of 2026-10-25;
samples `tests/fixtures/get_un_trade_exports/IC_2019.json`,
`tests/fixtures/get_un_trade_imports/TP_2019.json`,
`tests/fixtures/get_un_trade_re_exports/MC_2019.json`,
`tests/fixtures/get_un_trade_export_data_release_info/all.json`,
`tests/fixtures/get_un_trade_import_data_release_info/all.json` and
`tests/fixtures/get_countries/all.json`.

### The Census release lists and their release times

Each Census release list holds one record per statistical month, newest first, with
`statisticalYearMonth` (`"202608"`), `productType` (`"X"` or `"M"`), `reporterCode`
(`"US"`) and `releaseTimeStamp`, a date and a time without a zone or a fraction
(`"2026-10-06T08:00:00"`). Both lists held 716 months, from 196701 to 202608, and each
month's latest release alone. A month comes out in the second month after it: 202608 on
2026-10-06 and 202607 on 2026-09-03. The annual revision re-released 202301 to 202512 at
`2026-06-24T08:00:00` and the twelve months of 2022 at `2025-06-24T08:00:00`, so the newest
release among 202512 to 202602 is December's, and the 492 months from 196701 to 200712 all
carry `2008-01-01T08:00:00`. Upstream publishes no release list for Census re-exports.

Probe: 2026-10-25, `GATSData_GetCensusExportDataReleaseInfo` and
`GATSData_GetCensusImportDataReleaseInfo`; samples
`tests/fixtures/get_census_export_data_release_info/all.json` and
`tests/fixtures/get_census_import_data_release_info/all.json`.

### The re-exports' codes are export codes

Every HS10 code of the recorded re-export answers, 29 codes, stands under product type `"X"`
in `GATSData_GetCommodities`.

Probe: 2026-10-26, `GATSData_GetCensusReExports`, `GATSData_GetCustomsDistrictsReExports`
and `GATSData_GetCommodities`; samples
`tests/fixtures/get_census_re_exports/IC_2026_8.json`,
`tests/fixtures/get_census_re_exports/IC_2026_7.json`,
`tests/fixtures/get_customs_districts_re_exports/IC_2026_8.json` and
`tests/fixtures/get_commodities/all.json`.

### The UN Trade release lists end in 2019

Each UN Trade release list holds one record per reporter and statistical year, newest year
first, with `statisticalYear` as text (`"2019"`), `productType`, `reporterCode` and
`releaseTimeStamp`, a time without a zone. The exports list held 3,796 records for 206
reporters and the imports list 3,832 for 207, 32 reporters for 2019 in each, and 32
reporter-years stood in the exports list alone and 68 in the imports list alone; Iceland's
exports are listed for 31 years, 1989 to 2019. Both lists end with statistical year 2019,
and their newest release time is 2021-01-18, the Netherlands' 2014 (`"2021-01-18T01:25:58"`
in the exports list): no reporter-year had been released for more than five years, so the
feed is frozen. Upstream publishes no release list for UN Trade re-exports.

Probe: 2026-10-26, `GATSData_GetUNTradeExportDataReleaseInfo` and
`GATSData_GetUNTradeImportDataReleaseInfo`; samples
`tests/fixtures/get_un_trade_export_data_release_info/all.json` and
`tests/fixtures/get_un_trade_import_data_release_info/all.json`.

### The lists of codes

The countries list held 322 codes, each with `countryCode`, `regionCode`,
`countryParentCode`, `countryName`, `description`, `isO3Code`, `discontinuedOn` and
`gencCode`. 26 carry `discontinuedOn`, a month as six digits (`"198712"`); a code whose
`countryParentCode` is its own code is no other code's parent by that alone, and 19 of the
26 are the parent of another code. The two-digit codes `"01"` (Caribbean,nes) to `"18"`
(ASEAN) stand in region `R99` beside codes such as `AY` (Antarctica) and `BV` (Bouvet
Island). The regions list held 15 regions, `R99` among them, the HS6 list 2,909 codes, the
units list 108 ids from 0 to 107 and the customs-district list 53 districts.

Probe: 2026-10-25 and 2026-10-26, `GATSData_GetCountries`, `GATSData_GetRegions`,
`GATSData_GetHS6Commodities`, `GATSData_GetUnitsOfMeasure` and
`GATSData_GetCustomsDistricts`; samples `tests/fixtures/get_countries/all.json`, recorded
2026-10-25, and `tests/fixtures/get_regions/all.json`,
`tests/fixtures/get_hs6_commodities/all.json`,
`tests/fixtures/get_units_of_measure/all.json` and
`tests/fixtures/get_customs_districts/all.json`, recorded 2026-10-26.

### The HS10 commodities list

`GATSData_GetCommodities` answers one list, 24,936 records and 7,592,916 bytes of JSON, with
no paging. Each record holds `hS10Code`, `startDate` and `endDtate`, upstream's spelling,
months as six digits, `productType`, `commodityName`, 16 characters at most,
`commodityDescription`, `isAgCommodity` and the four unit ids. Its product types are `"X"`
(5,919 records), `"M"` (14,469), `"T"` (2,704) and `"B"` (1,844), and the snapshot documents
none of them; every `T` and `B` record carries a seven-digit code padded with three spaces
(`"0011010   "`). A code repeats across product types and with a later `startDate`:
`"0207410000"` under `"M"` is chicken cuts from `"198901"` and ducks from `"201201"`.

Probe: 2026-10-26, `GATSData_GetCommodities`; sample `tests/fixtures/get_commodities/all.json`.

## Empty answers and refusals

### An unknown code answers the empty list

An unknown partner code answers HTTP 200 with `[]` (`ZZ` for August 2026), the same answer
as a listed partner without trade (`BV`, Bouvet Island, for August 2026), and so does an
unknown reporter code (`ZZ` for 2019): nothing in the answer tells the two apart.

Probe: 2026-10-25 and 2026-10-26, `GATSData_GetCensusExports` and
`GATSData_GetUNTradeExports`; samples `tests/fixtures/get_census_exports/unknown_partner.json`
and `tests/fixtures/get_census_exports/no_data_valid_partner.json`, recorded 2026-10-25, and
`tests/fixtures/get_un_trade_exports/unknown_reporter.json`, recorded 2026-10-26.

### A period not released answers the empty list

A month after the latest release answers HTTP 200 with `[]` (China, 2035-01), and so do a
year after every reporter's latest (Iceland, 2035) and a year that the release lists do not
hold for the reporter (Iceland, 2020): the same answer as a partner or a reporter without
trade. A listed reporter-year without trade answers `[]` too: Iceland's 2019 re-exports,
while its 2019 exports stand in the exports list.

Probe: 2026-10-25 and 2026-10-26, `GATSData_GetCensusExports`, `GATSData_GetUNTradeExports`
and `GATSData_GetUNTradeReExports`; samples
`tests/fixtures/get_census_exports/future_month.json`, recorded 2026-10-25, and
`tests/fixtures/get_un_trade_exports/future_year.json`,
`tests/fixtures/get_un_trade_exports/unreleased_year.json` and
`tests/fixtures/get_un_trade_re_exports/IC_2019.json`, recorded 2026-10-26.

### Month 0, month 13 and a year that is no number answer HTTP 404 with an empty body

Month 0 and month 13 answer HTTP 404 with an empty `text/plain` body (China, 2026), and so
does a UN Trade year that is not a number (`abc` for Iceland), which the snapshot types as a
string.

Probe: 2026-10-25 and 2026-10-26, `GATSData_GetCensusExports` and
`GATSData_GetUNTradeExports`; samples `tests/fixtures/get_census_exports/month_0.json` and
`tests/fixtures/get_census_exports/month_13.json`, recorded 2026-10-25, and
`tests/fixtures/get_un_trade_exports/year_text.json`, recorded 2026-10-26.

### A parent code answers for its children

Two parents answered August 2026 under their own codes: `"Y1"` (Leeward-Windward Islands,
discontinued 198801) held every HS10 code of `"AC"` (Antigua and Barbuda), one of the nine
codes under it, at no lower a value, as the sum of its children would, and `"AS"`
(Australia, discontinued 198712) answered the 669 records of its child `"A2"` apart from the
code, while `"NF"` (Norfolk Island), another child of `AS`, answered none.

Probe: 2026-10-28, `GATSData_GetCensusExports`; samples
`tests/fixtures/get_census_exports/Y1_2026_8.json`,
`tests/fixtures/get_census_exports/AC_2026_8.json`,
`tests/fixtures/get_census_exports/AS_2026_8.json`,
`tests/fixtures/get_census_exports/A2_2026_8.json` and
`tests/fixtures/get_census_exports/NF_2026_8.json`.

### The region codes `01` and `18` answer the empty list

`"01"` (Caribbean,nes) and `"18"` (ASEAN), codes of region `R99` that no record names as its
parent, answered August 2026 with `[]`, which no answer tells from a listed partner without
trade.

Probe: 2026-10-28, `GATSData_GetCensusExports`; samples
`tests/fixtures/get_census_exports/01_2026_8.json` and
`tests/fixtures/get_census_exports/18_2026_8.json`.

### A discontinued code that is no parent answers the empty list

`"GC"` (Germany, Democratic Republic, discontinued 199009, its parent `GM`), a code that no
record names as its parent, answered August 2026 with `[]`.

Probe: 2026-10-28, `GATSData_GetCensusExports`; sample
`tests/fixtures/get_census_exports/GC_2026_8.json`.

### The gateway refuses an invalid key

An invalid key answers HTTP 403 with `application/json`, `{"error": {"code":
"API_KEY_INVALID", "message": "An invalid api_key was supplied. Get one at
https://api.fas.usda.gov:443"}}`, and no quota headers.

Probe: 2026-10-25, `GATSData_GetRegions`; sample `tests/fixtures/get_regions/invalid_key.json`.

### The gateway's hourly quota

Every answer to a valid key recorded carries `x-ratelimit-limit: 1000` and
`x-ratelimit-remaining`, the 404s included, and `via` names api.data.gov's API Umbrella; no
answer carries a header that says when the quota resets. No 429 was recorded for GATS.

Probe: 2026-10-25 to 2026-10-28, every operation recorded; samples every fixture under
`tests/fixtures/` but `tests/fixtures/get_regions/invalid_key.json`, among them
`tests/fixtures/get_census_exports/CH_2026_8.json` and
`tests/fixtures/get_census_exports/month_0.json`.
