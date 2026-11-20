- A Census or UN Trade release list or the HS10 commodities list that upstream answers
  with a 200 whose body is no JSON is asked for again on the next call, where the client's
  cache kept that answer and raised the same `ValidationError` without a request for an
  hour, or for a day. (https://github.com/xippios/sdk-core/issues/122)
