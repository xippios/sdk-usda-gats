- The comment above `PathCaches` in `_client.py`, the client's cache with a lifetime per
  path, cites the public issue of sdk-core that declines such a lifetime while one source
  asks for it, where it named an item of an internal list. The docstrings of
  `scripts/refresh_upstream.py` and the paragraph it writes into `docs/upstream/FETCHED.md`
  say when and where the portal's Swagger document was found without naming who found it,
  and `FETCHED.md` takes that text at its next capture.
  (https://github.com/xippios/sdk-core/issues/48,
  https://github.com/xippios/sdk-usda-gats/issues/21)
