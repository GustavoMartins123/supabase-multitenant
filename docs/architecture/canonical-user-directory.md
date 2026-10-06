# Canonical user revocation

The Authelia YAML is the durable source of user presence, active state and
groups. Studio reads it under the mutation filesystem lock before issuing user
headers/tokens or checking local administrative permissions. Cached Authelia
session groups and the UI user cache are not authorization evidence.

The token contains the SHA-256 revision of the exact YAML. Before resolving any
API user, the API reads `/internal/users/directory` from Studio over the existing
HTTP callback channel. The request uses service HMAC; the response is HMAC-bound
to that request's random nonce. No password/hash is exported. HTTPS validates
the configured CA and hostname. Failure blocks with 503, never cached grants.

Each exported full snapshot receives an fsynced monotonically increasing
sequence under the YAML lock. Migration 0010 persists the confirmed revision
and sequence. Reconciliation is transactional and serialized: absent users are
disabled and lose all groups; disabled entries and removed groups are included.
Older snapshots cannot replace newer, different revisions. Tokens for another
revision are rejected. Identical concurrent revisions do not roll back ordering.

Worker zero retries the complete current YAML every five seconds without a
finite attempt budget. YAML survives worker restarts and API outages. The
individual user mutation helper now submits this same full-directory protocol;
there is no independent partial-write authorization path. Transactional
rollback of a failed UI mutation remains supported.

Human jobs confirm the directory before API dispatch and the host-agent reads
it again immediately before execution, taking active/global-admin facts from
that fresh proof rather than stored groups. Project membership remains a
current control-plane check. This prevents queued work from relying on a revoked
account. Already running operations are not retroactively cancelled.

## Deployment, including split-node

- Run `tools/configure_studio_runtime.py --studio-origin https://host:port --force`
  on upgrade. It creates `.studio-directory-sequence` only when absent and sets
  `STUDIO_CACHE_INVALIDATION_URL` in the server env when that file is available.
- In split-node, explicitly copy that URL into the server configuration: both
  the API container and host-agent must reach the externally visible Studio
  endpoint. DNS `nginx` inside Docker is not a host-agent callback address.
- Distribute Studio's public CA to `servidor/certs/ca.pem`. The API uses its
  mounted CA path; the host-agent uses the host's `certs/ca.pem`. No private CA
  key is needed. Restart API and host-agent after configuration changes.
- Preserve `.studio-directory-sequence` with the YAML. Never reset it on reload
  or force configuration. A restored, older sequence fails closed against a
  newer database state; recovery must explicitly restore a consistent pair.
- Full-directory reads increase filesystem and database work. Authorization
  availability now intentionally depends on the canonical Studio callback.

## Evidence

`test_studio_directory.py` runs the production lock/YAML/sequence/HMAC/actor
headers and retry timer in Docker OpenResty (ID export is mocked).
`test_authorization_behavior.py` exercises transactional reconciliation, outage,
removal, snapshot ordering and queued-agent revocation in real PostgreSQL. With
`STUDIO_DIRECTORY_TEST_URL`, it additionally uses real OpenResty snapshots to
revoke an active global admin through the real API. These boundary tests do not
claim a complete real Authelia/Traefik split-node installation test.

`tools/run_auth_security_tests.py` creates the mandatory disposable PostgreSQL
and OpenResty harnesses, rejecting any skipped test. CI runs it in the
`authorization-security-live` job. See
[security validation](../operations/security-validation.md) for exact commands
and the full-stack acceptance that these boundary tests do not cover.
