- Every answer names the codes of its rows in `meta.names` by the packaged lists: partners
  and reporters, `{"country_code": {"CH": "China"}}`, customs districts, HS6 codes, the
  four unit ids, and a country's region and parent, and the tasks name the partner,
  reporter, district and full HS6 code a call asks for, so an answer without rows names
  them. A row's code that the packaged list lacks is left out of the names and said in
  `meta.notes`, so no answer is withheld for it. (https://github.com/xippios/sdk-core/issues/478, https://github.com/xippios/sdk-usda-gats/issues/34)
