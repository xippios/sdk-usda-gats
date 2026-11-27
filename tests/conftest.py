# Core's plugin keeps the default run offline and free of real keys (sdk-core ADR-0035),
# runs anyio tests on asyncio and serves the family check in tests/test_family.py; it sets
# each secret variable of ENV_VARS in _client.py to its placeholder, so none is named here.
pytest_plugins = ["xippios.core.testing.plugin"]
