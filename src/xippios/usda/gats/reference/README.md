# Reference data for USDA FAS Global Agricultural Trade System

Five of the lists GATS publishes ship here, versioned with the package (conventions §3):
each `reference/<name>.json` holds `{"param", "endpoint", "fetched", "records"}` and an
optional `"note"`, upstream's records verbatim under upstream's field names and in
upstream order, written by `/refresh-reference-data`'s script with `PackagedList.write`,
never by hand, and read with `PackagedList.load`:

```python
from xippios.core import PackagedList

PackagedList.load("xippios.usda.gats", "countries").records  # [{"countryCode": "01", ...}, ...]
```

One row per file: Origin is the endpoint it was fetched from, Fetched the UTC time of that
fetch; these files keep the bare day the 0.1.0 script wrote, which core reads as its
00:00 UTC until the next refresh writes the time.

GATS's one id list, `unitsOfMeasure`, makes `UnitOfMeasureId` in `enums.py`
(`UnitOfMeasureId.KILOGRAMS == 47`; the name "Crates" of ids 33 and 105 gives `CRATES_33`
and `CRATES_105`); regions, countries, HS6 commodities and customs districts are tables,
not enums. `params` checks the Census `partner_code` and the UN Trade `reporter_code`
and `partner_code` against `countries.json`, the customs-district filter against
`customsDistricts.json` and a six-digit `hs6_code` against `HS6Commodities.json`, before
any call, since GATS answers an unknown code with an empty list; the five `list_*` tasks
answer from the files without a call. The HS10 list, `GATSData_GetCommodities` (24,936
records, about 7.6 MB of JSON), is not packaged: `list_commodities` fetches it live. The
live tests (`tests/test_live.py`) fetch each list through its endpoint wrapper and fail
when the packaged records differ, naming what is gone and what is new.

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
second keyed call. The four 2026-10-26 files were written by the 0.1.0 script's own
functions from the answers recorded that morning in
`tests/fixtures/<operation>/all.json`, served to the wrappers through `respx` in the same
way: `GATSData_GetRegions` at 04:55:45 UTC, `GATSData_GetHS6Commodities` at 04:55:54,
`GATSData_GetUnitsOfMeasure` at 04:55:55 and `GATSData_GetCustomsDistricts` at 04:55:56;
`countries.json` was left as it was, so it keeps its own date. Every file's records
equal the recorded ones, field for field and in order (`tests/test_params.py` and
`tests/test_lists.py` check it).
