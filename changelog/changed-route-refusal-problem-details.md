- A route answers an argument that its schema refuses, a `year` of `abc`, a
  `product_type` of `Z` or a missing `month` say, as problem details before the task runs:
  HTTP 422, the title `InvalidRequestError` and the detail `<argument>: <message>`, which
  echoes no input, where FastAPI's own 422 listed its error details with the input.
  (https://github.com/xippios/sdk-core/issues/66)
