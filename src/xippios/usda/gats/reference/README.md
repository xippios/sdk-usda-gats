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
fetch, to the second, as `PackagedList.write` wrote it into the file's `fetched`.

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
| `regions.json` | `GET https://api.fas.usda.gov/api/gats/regions` (`GATSData_GetRegions`) | 2026-10-28T19:22:39Z | 15 |
| `countries.json` | `GET https://api.fas.usda.gov/api/gats/countries` (`GATSData_GetCountries`) | 2026-10-28T19:22:40Z | 322 |
| `HS6Commodities.json` | `GET https://api.fas.usda.gov/api/gats/HS6Commodities` (`GATSData_GetHS6Commodities`) | 2026-10-28T19:22:42Z | 2,909 |
| `unitsOfMeasure.json` | `GET https://api.fas.usda.gov/api/gats/unitsOfMeasure` (`GATSData_GetUnitsOfMeasure`) | 2026-10-28T19:22:43Z | 108 |
| `customsDistricts.json` | `GET https://api.fas.usda.gov/api/gats/customsDistricts` (`GATSData_GetCustomsDistricts`) | 2026-10-28T19:22:42Z | 53 |

The five files were written by `scripts/refresh_reference.py` on 2026-10-28 from
upstream's answers, one keyed call per list, each answered 200. No record changed: every
file's records equal the ones recorded in `tests/fixtures/<wrapper>/all.json`
(`get_countries` on 2026-10-25, the other four on 2026-10-26), field for field and in
order (`tests/test_params.py` and `tests/test_lists.py` check it).
