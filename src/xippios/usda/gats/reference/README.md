# Reference data for USDA FAS Global Agricultural Trade System

Five of the lists GATS publishes ship here as JSON, versioned with the package, and load
through `xippios.usda.gats.params` (built on `xippios.core.reference`):

```python
from xippios.usda.gats.params import packaged_values

packaged_values("countries").records  # [{"countryCode": "01", ...}, ...], no network call
```

Each file holds upstream's records verbatim, under upstream's field names and in
upstream order, plus the list name (`param`, as the upstream path names it), the
operation it came from (`endpoint`) and the UTC fetch date (`fetched`).

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script also regenerates
  `enums.py` with `xippios.core.reference`: one `StrEnum` per value list
  (`render_str_enums`), or one `IntEnum` per list of integer ids (`render_int_enums`).
  GATS's one id list is `unitsOfMeasure`, which makes `UnitOfMeasureId`
  (`UnitOfMeasureId.KILOGRAMS == 47`; the name "Crates" of ids 33 and 105 gives
  `CRATES_33` and `CRATES_105`); regions, countries, HS6 commodities and customs
  districts stay tables, not enums.
- Files keep upstream's names: a file is named as the upstream path names its list, and
  a table and a list of integer ids alike hold their records under upstream's field
  names.
- Every file has a row below naming the endpoint it came from, the date and the count.
- A multi-tenant source packages no tenant data (ADR-0014); GATS is single-tenant, every
  list is the same for every caller of the api.data.gov key.
- Use: `params.validate_partner_code` checks the `partner_code` of the six Census data
  tasks against `countries.json` before any call, since GATS answers an unknown partner
  code with an empty list, the same as a partner without trade, and refuses a code for a
  month after its `discontinuedOn`; `params.validate_customs_district_id` checks the
  `customs_district_id` filter of the three customs-district tasks against
  `customsDistricts.json`.
- Agents get a lookup task for every packaged list so they can form valid calls: one
  lookup task per list, `list_<thing>`, served as the MCP tool
  `usda_gats_list_<thing>`: `list_regions`, `list_countries`, `list_hs6_commodities`,
  `list_units_of_measure`, `list_customs_districts`. They answer from these files without
  an upstream call, with the file's `endpoint` as `meta.endpoint` and its `fetched` date
  as `meta.vintage`.
- The HS10 list, `GATSData_GetCommodities` (24,936 records, about 7.6 MB of JSON), is not
  packaged: `list_commodities` fetches it live, and the client keeps it for a day.
- Freshness: the live tests (`tests/test_live.py`, `XIPPIOS_LIVE_TESTS=1`) fetch each
  list through its endpoint wrapper and fail when the packaged records differ, naming
  what is gone and what is new.
- Refresh policy: `/refresh-reference-data` inside `/release-prep`, and whenever a
  validation failure names a code the package lacks.

| File | Origin | Fetched (UTC) | Records |
| --- | --- | --- | --- |
| `regions.json` | `GET https://api.fas.usda.gov/api/gats/regions` (`GATSData_GetRegions`) | 2026-10-26 | 15 |
| `countries.json` | `GET https://api.fas.usda.gov/api/gats/countries` (`GATSData_GetCountries`) | 2026-10-25 | 322 |
| `HS6Commodities.json` | `GET https://api.fas.usda.gov/api/gats/HS6Commodities` (`GATSData_GetHS6Commodities`) | 2026-10-26 | 2,909 |
| `unitsOfMeasure.json` | `GET https://api.fas.usda.gov/api/gats/unitsOfMeasure` (`GATSData_GetUnitsOfMeasure`) | 2026-10-26 | 108 |
| `customsDistricts.json` | `GET https://api.fas.usda.gov/api/gats/customsDistricts` (`GATSData_GetCustomsDistricts`) | 2026-10-26 | 53 |

The 2026-10-25 file was written by `scripts/refresh_reference.py` from the answer
recorded the same evening in `tests/fixtures/GATSData_GetCountries/all.json`
(21:00:34 UTC), served to the script's wrapper through `respx`, so the refresh spent no
second keyed call. The four 2026-10-26 files were written by the script's own functions
(`upstream_record`, `write`, `render`) from the answers recorded that morning in
`tests/fixtures/<operation>/all.json`, served to the wrappers through `respx` in the same
way: `GATSData_GetRegions` at 04:55:45 UTC, `GATSData_GetHS6Commodities` at 04:55:54,
`GATSData_GetUnitsOfMeasure` at 04:55:55 and `GATSData_GetCustomsDistricts` at 04:55:56;
`countries.json` was left as it was, so it keeps its own date. Every file's records
equal the recorded ones, field for field and in order (`tests/test_params.py` and
`tests/test_lists.py` check it).
