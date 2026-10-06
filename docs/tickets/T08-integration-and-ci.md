# T08 - Integration tests, E2E, CI

**ADRs:** 0009

## Scope
- PostGIS cross-check test (`ST_Area(geography)`, `ST_Length(geography)`).
- E2E script: compose up, upload without wait, poll to COMPLETED, assert measurements.
- GitHub Actions: lint, type check, tests with PostGIS service, E2E with compose.

## Acceptance
- All green locally and in CI.
