# Studio mutation origin

Run `tools/configure_studio_runtime.py` with the externally visible HTTPS Studio
origin (including its non-default port) during installation **and upgrade**. It
persists `/config/.studio-origin`, shared with OpenResty. Missing or malformed
configuration refuses mutations with 503. Request Host is not a source of trust.

Browser mutations under `/api/` and `/storage/v1` require this exact Origin.
Present Fetch Metadata must say `same-origin`. JSON handlers reject simple form
content types with 415. The service-HMAC-only `/api/internal/push` is exempt only
without a cookie; internal subrequests are not browser requests. Removed
`/object/sign` aliases return 410; use the canonical Storage endpoint.

`tests/integration/test_studio_csrf.py` exercises the production guard in real
OpenResty with two TLS ports, including a browser form POST carrying a synthetic
valid cookie. This isolates the CSRF boundary; it does not claim full Authelia
session integration.
