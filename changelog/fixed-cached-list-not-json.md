- A Census or UN Trade release list that upstream answers with a 200 the package cannot
  read, no JSON or no list of releases, is asked for again on the next call, and so is
  the HS10 commodities list for a body that is no JSON, where the client's cache kept
  such an answer and raised the same `ValidationError` without a request for an hour, or
  for a day. (https://github.com/xippios/sdk-core/issues/122)
