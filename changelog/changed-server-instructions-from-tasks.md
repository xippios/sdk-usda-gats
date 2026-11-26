- The MCP server's instructions come from `tasks.MCP_INSTRUCTIONS`, and the hook that
  applies `--series-months` takes the parsed options alone, so a host applies the tool
  set's options as `tools.apply_options(tools.option_defaults())`. (https://github.com/xippios/sdk-core/issues/476)
