- `xippios-usda-gats-mcp` names itself in its usage line and its errors, an out-of-range
  `--series-months 61` ending in `xippios-usda-gats-mcp: error: the series ceiling`, where
  they named the server, `xippios-usda-gats`. Its help says that `--allow-remote` changes
  nothing, since this read server is not held to loopback, where it offered to serve a
  write server beyond loopback. (https://github.com/xippios/sdk-core/issues/167)
