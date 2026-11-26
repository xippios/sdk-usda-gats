- Three filters take the name of upstream's field that they read, in Python, over MCP and
  over HTTP, and in `meta.request`: the UN Trade data tasks' `partner_code` is
  `partner_country_code`, `get_un_release_dates`' `year` is `statistical_year` and
  `get_census_release_dates`' `statistical_year` is `statistical_year_month`. The last takes
  text, a year such as `"2026"` or a month such as `"202608"`, and keeps the records whose
  `statisticalYearMonth` starts with it, so one month can now be asked for. (sdk-core ADR-0061, https://github.com/xippios/sdk-usda-gats/issues/57)
