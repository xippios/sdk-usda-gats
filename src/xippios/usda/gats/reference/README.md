# Reference data for USDA FAS Global Agricultural Trade System

The GATS countries list ships here as JSON, versioned with the package, and loads
through `xippios.usda.gats.params` (built on `xippios.core.reference`):

```python
from xippios.usda.gats.params import packaged_values

packaged_values("countries").records  # [{"countryCode": "01", ...}, ...], no network call
```

The file holds upstream's records verbatim, under upstream's field names and in
upstream order, plus the list name (`param`, as the upstream path names it), the
operation it came from (`endpoint`) and the UTC fetch date (`fetched`).

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script also regenerates
  `enums.py` with `xippios.core.reference`: one `StrEnum` per value list
  (`render_str_enums`), or one `IntEnum` per list of integer ids (`render_int_enums`).
  The countries list is a table, packaged without an enum, so `enums.py` has no class
  yet.
- Files keep upstream's names: a file is named as the upstream path names its list, and
  a table and a list of integer ids alike hold their records under upstream's field
  names.
- Every file has a row below naming the endpoint it came from, the date and the count.
- A multi-tenant source packages no tenant data (ADR-0014); GATS is single-tenant, every
  list is the same for every caller of the api.data.gov key.
- Use: `params.validate_partner_code` checks the `partner_code` of the Census tasks
  against `countries.json` before any call, since GATS answers an unknown partner code
  with an empty list, the same as a partner without trade.
- Agents get a lookup task for every packaged list so they can form valid calls: one
  lookup task per list, `list_<thing>`, served as the MCP tool
  `usda_gats_list_<thing>`. `list_countries` is not provided yet; it comes with the
  other GATS lists, and until then the task docstrings and the refusal of an unknown
  code name example codes.
- Refresh policy: `/refresh-reference-data` inside `/release-prep`, and whenever a
  validation failure names a code the package lacks.

| File | Origin | Fetched (UTC) | Records |
| --- | --- | --- | --- |
| `countries.json` | `GET https://api.fas.usda.gov/api/gats/countries` (`GATSData_GetCountries`) | 2026-10-25 | 322 |

The 2026-10-25 file was written by `scripts/refresh_reference.py` from the answer
recorded the same evening in `tests/fixtures/GATSData_GetCountries/all.json`
(21:00:34 UTC), served to the script's wrapper through `respx`, so the refresh spent no
second keyed call; the records equal the recorded ones, field for field and in order
(`tests/test_params.py` checks it).
