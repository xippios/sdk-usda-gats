- `tasks.mcp_apply_options`, the hook that applies `--series-months`, takes the parsed
  options alone and returns nothing, so the host's call that 0.3.0 gave,
  `tools.apply_options(tools.option_defaults(), server)`, raises `TypeError` and becomes
  `tools.apply_options(tools.option_defaults())`. The MCP server's instructions come from
  `tasks.MCP_INSTRUCTIONS`. (https://github.com/xippios/sdk-core/issues/476)
