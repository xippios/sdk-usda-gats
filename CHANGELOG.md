# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for USDA FAS Global Agricultural Trade System, empty task layer, MCP server and FastAPI router
  wired to it, test harness, CI, the nightly live tests and publishing.
- Upstream documentation snapshot in `docs/upstream/` (2026-10-25): the GATS part of
  the FAS Open Data Services Swagger 2.0 document as the portal loads it
  (`openapi/portal-document.json`) and as the API serves it itself
  (`openapi/backend-docs-v1.json`), nineteen `/api/gats/` operations each, the ESR and
  PSD paths left out. `FETCHED.md` records the full documents' sizes and sha256 and the
  pages that hold no documentation text.
- `scripts/refresh_upstream.py`: regenerates the snapshot reproducibly, stdlib only and
  without a key (`uv run scripts/refresh_upstream.py`); `Fetched` is the UTC time of the
  run.
