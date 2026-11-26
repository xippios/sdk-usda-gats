- The three series tasks refuse a range over the ceiling in core's wording before the
  first request, naming the range, the ceiling, where the MCP server's is lower
  `--series-months`, and that nothing was sent, their class `InvalidRequestError` kept. A
  request after the first month that fails raises its error, its class kept, naming the
  months answered before it, and the series returns nothing. (https://github.com/xippios/sdk-core/issues/315, https://github.com/xippios/sdk-usda-gats/issues/33)
