- `tasks.series_ceiling`, `tasks.set_series_ceiling`, `tasks.SERIES_MAX_MONTHS` and
  `tasks.MCP_SERIES_MAX_MONTHS` are removed, so a caller's use of any fails, and one
  `Ceiling` of core's, `tasks.SERIES`, holds the series' ceiling of 60 months in their place,
  24 on the MCP server and `--series-months` to set another: `SERIES.value` reads it and
  `SERIES.set(months)` sets it. (sdk-core ADR-0054, https://github.com/xippios/sdk-core/issues/315, https://github.com/xippios/sdk-usda-gats/issues/33)
