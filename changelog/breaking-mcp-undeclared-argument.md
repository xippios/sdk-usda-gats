- A tool refuses an argument that it does not declare before it runs, whatever its value:
  `usda_gats_list_countries` called with `serach` for `search` answers
  `error: InvalidRequestError: serach: Not an argument of this tool` and names the
  arguments it takes, where the argument was dropped and the tool answered all 322
  countries. (https://github.com/xippios/sdk-core/issues/84)
