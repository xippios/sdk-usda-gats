- `list_countries(region_code=...)` refuses a region that the packaged regions list lacks with
  `UnknownCode`, naming the closest regions, and `list_commodities(product_type=...)` refuses
  a product type that no record of the HS10 list carries with `InvalidRequestError`, naming
  the four it carries and saying that the list was read, where both answered an empty list.
  The comparison stays exact, so `"r05"` names `R05` and `"x"` names `X`. (sdk-core ADR-0045, https://github.com/xippios/sdk-usda-gats/issues/31)
