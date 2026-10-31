# Kernel Test Bench

The browser console is at `web/kernel.html` and is intentionally a diagnostic interface, not a trading terminal.

## What it can test
- Load the local demo snapshot and inspect the presence of a signal and execution safety flag.
- Validate event-envelope shape and version 1.0, including rejection of unknown fields, unsupported event types and malformed timestamps.
- Verify that `trade.execute` is not a valid event type and that a health event cannot assert `execution_allowed=true`.
- Optionally call a configured Accounts API's read-only `GET /v1/health` and `GET /v1/dashboard` endpoints.

## What it does not do
- It does not calculate indicators, generate signals or run the Python kernel in the browser.
- It does not submit orders, write strategy configuration, or ask for broker credentials.
- A successful browser contract check is not a Python-kernel test. The real Python engine and Worker integration remain covered by the GitHub Actions test suite.
- The dashboard endpoint may require an authenticated session. Configure the API URL only for a trusted deployment.

## Open
Serve the `web/` directory as static files and open `kernel.html`. The main dashboard links can be added separately; no build framework is required.
