- The arguments that identify a record stay positional in the order of upstream's path, and
  every filter and every argument of the package's own, the series' four months among them,
  is keyword-only: `get_census_exports("CH", 2026, 8, hs10_code="02")`,
  `get_census_export_series("IC", start_year=2026, start_month=7, end_year=2026,
  end_month=8)`, `get_un_exports("IC", 2019, hs6_code="03")` and
  `list_countries(region_code="R05")`, where 0.3.0 took the same values by position. Over
  MCP and HTTP nothing changes, since a tool and a route take their arguments by name.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-usda-esr/issues/60, https://github.com/xippios/sdk-usda-gats/issues/57)
