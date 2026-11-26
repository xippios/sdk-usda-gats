- The six Census month tools, `usda_gats_get_census_exports`, `usda_gats_get_census_imports`,
  `usda_gats_get_census_reexports` and the three `usda_gats_get_customs_district_*` tools,
  take `offset`, the rows of a cut answer already shown, and answer the rows after them from
  the client's cache, sending no request, so all 777 rows of exports to China in August 2026
  can be read over MCP. The note of every page but the last names the `offset` to continue
  with. (sdk-core ADR-0047, https://github.com/xippios/sdk-usda-gats/issues/32)
