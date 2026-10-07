# T13 - Home page, responsive uploads, faster measurement

## Scope
- Home page at `/`: drag-and-drop upload with progress, live status polling, register of measured files with totals, sample files, clear error notices. Shares a theme with the viewer.
- Upload endpoint must not block the event loop: inline `?wait=true` processing previously froze every other request.
- Reject oversized uploads from `Content-Length` before the body is read.
- Cache projection transformers by snapping centres to a 0.01° grid.

## Acceptance
- A health check during a large inline upload answers in milliseconds (regression test).
- 60 MB upload gets 413 without the body being read.
- 12,000 features process in about 2 s; snapped and exact centres agree to 1e-8 (test).
- Home page and viewer checked at desktop and phone width, light and dark.
