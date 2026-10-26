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
`"JA"` Japan), checked against the countries list packaged in `reference/` before any
call; an unknown code is refused, naming close codes where the list has any and example
codes otherwise, since GATS answers it with an empty list. `month` is 1 to 12 and `year`
four digits; `hs10_code` keeps the products whose code starts with it, a full ten-digit
code for one product or a prefix such as a chapter, applied after the one data request.
`get_census_imports` takes the same arguments and adds five consumption and CIF fields
per record.

Each data task makes two requests, its flow's release list and the month, or only the
second while the client's cache holds the list, for an hour. A month the list lacks (not
released yet, or before January 1967) raises `NotFoundError` naming the months released;
a listed partner without trade in a released month is an empty list. `meta.vintage` is
the month's release time from that list, as upstream states it (`"2026-10-06T08:00:00"`
for August 2026): upstream's identifier of the release that last revised the figures,
since Census applies corrections once a year and the list records only each month's
latest release. The month itself is in `meta.request` and in every record's `date`. For
up to an hour after a release the cached list may still give a revised month the
previous release's time, or refuse a month just released, and the refusal says when the
list was fetched: an accepted lag. `meta.published_at` stays `None`: core's `ResultMeta`
takes only a timezone-aware time, and FAS states no zone for its release times, which
`get_census_release_dates` returns as upstream states them.

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
200 rows or 64 KB unless a tool has a cap of its own, with a note on the rows left out:
one partner-month is one row per HS10 product (777 rows for exports to China in August
2026, 3,294 for imports), so the notes of `usda_gats_get_census_exports` and
`usda_gats_get_census_imports` name `hs10_code`; `usda_gats_get_census_release_dates`,
which has no filter, returns the newest 200 months, more than sixteen years, with a note
that says so. `--http` serves streamable HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `GATSData_GetCensusExports` (`censusExports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_census_exports(partner_code, year, month, hs10_code=None)` | `usda_gats_get_census_exports` | alpha |
| `GATSData_GetCensusImport` (`censusImports/partnerCode/{partnerCode}/year/{year}/month/{month}`) | `get_census_imports(partner_code, year, month, hs10_code=None)` | `usda_gats_get_census_imports` | alpha |
| `GATSData_GetCensusExportDataReleaseInfo` (`census/data/exports/dataReleaseDates`) | `get_census_release_dates("X")`; read by `get_census_exports` too | `usda_gats_get_census_release_dates` | alpha |
| `GATSData_GetCensusImportDataReleaseInfo` (`census/data/imports/dataReleaseDates`) | `get_census_release_dates("M")`; read by `get_census_imports` too | `usda_gats_get_census_release_dates` | alpha |
| `GATSData_GetCountries` (`countries`) | none yet: packaged as `reference/countries.json`, which checks `partner_code` | none yet | packaged |

The other fourteen GATS operations of the snapshot (`docs/upstream/`) are not wrapped yet.
Alpha: the public surface may change in a minor version before 1.0 (conventions §12);
`CHANGELOG.md` lists every change.

Every request counts against api.data.gov's quota of 1,000 requests per hour per key,
shared by every package using the same `DATA_GOV_API_KEY` (xippios-usda-psd and
xippios-usda-esr among them); a release list answered from the client's cache spends
none. The client keeps its own pace of one request per second; once the quota is spent it
waits for the quota to come back when that takes at most 30 s, and otherwise raises
`RateLimitError` with `retry_after` instead of sending.

## Upstream terms and attribution

Data comes from USDA FAS Global Agricultural Trade System (https://apps.fas.usda.gov/gats/default.aspx) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
