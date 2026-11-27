# Layout

The files that every source of the family holds are laid out once, in the tree of
sdk-template's README,
[What gets generated](https://github.com/xippios/sdk-template/blob/main/README.md#what-gets-generated).
This file holds what `xippios-usda-gats` adds to that tree, a module, a task file, a
script or a test of its own, each with what it holds, and the change that adds one updates it.

The import path is `xippios.usda.gats` (sdk-core ADR-0006); `src/xippios/` is a
namespace package, and so is `src/xippios/usda/`, the provider level.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this file says so (conventions §2).

```
src/xippios/usda/gats/
  _client.py       also LIFETIMES, how long the cache keeps every answer, by path prefix,
                   and the gateway of xippios.usda.fas, with no data path, whose policy
                   keeps the key's quota
  errors.py        the reasons UnknownCode names for GATS's codes (conventions §5)
  models.py        also ProductType, written by hand for the value set the two release lists
                   document; each code field declares the packaged list that names it
  api/             one module per upstream operation, named after it in snake case without
                   the GATSData_ prefix, e.g. get_census_exports, get_countries,
                   get_un_trade_export_data_release_info; each returns core's Answer, and
                   get_commodities keeps the parsed HS10 records of the cached answer
  tasks.py         also SERIES, the series' ceiling, core's Ceiling, and its two hooks
  params.py        also COUNTRIES, REGIONS, HS6_CODES, UNITS and DISTRICTS, the packaged lists
                   that a check or a name reads, and the checks of the arguments
  enums.py         IntEnum UnitOfMeasureId from the packaged unitsOfMeasure; never edited by
                   hand
  reference/       countries, regions, HS6Commodities, unitsOfMeasure and customsDistricts as
                   packaged
tests/
  test_api.py      replay tests for the endpoint wrappers
  test_client.py   the client's wiring, the gateway's policy on a 429 through the client, and
                   the cache's paths and lifetimes
  test_lists.py    the list tasks answer the packaged lists without a call, and the HS10 list
                   live, from the cache
  test_params.py   the packaged lists, the enum and the argument checks
  test_refresh_reference.py  the reference script's one Lists and its render-only run
  test_refresh_upstream.py   the snapshot script's own hooks on the kit of the FAS portal,
                   offline
docs/
  upstream/        also openapi/, the GATS parts of the portal's document and the backend's
                   document, and OBSERVED.md, the notes by hand on what GATS does but never
                   documents
```
