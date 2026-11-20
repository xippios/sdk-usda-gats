- `xippios.usda.gats.mcp.build()` returns the read-only tool set that
  `xippios-usda-gats-mcp` serves, xippios-core's `ToolSet` with the caps of
  `tasks.MCP_CAPS` and the hooks of `--series-months`, so a host serves the same tools
  beside other sources' in one server and applies the 24-month ceiling as the entry point
  does. `ENV_VARS`, beside `SOURCE`, names the one variable the package reads,
  `DATA_GOV_API_KEY`, secret and required.
  (https://github.com/xippios/sdk-core/issues/245,
  https://github.com/xippios/sdk-template/issues/81)
