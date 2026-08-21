# Spec: multiple opaque API keys per project

Status: core implemented; Docker-stack validation and the ES256/JWKS phase pending
Branch: `opaque-keys`  
Last technical review: 2026-08-12

## 1. Objective

Replace public `anon` and `service_role` JWTs with opaque API keys, allow
multiple independent credentials per project, and separate three cycles:

1. client-component identity, represented by the opaque API key;
2. internal `anon` or `service_role` authorization, represented by JWTs kept
   only on the server;
3. signing and expiration of session JWTs issued by Auth.

The time-based lifetime of each slot is optional policy. A version may have
`expires_at` set or remain valid without a deadline until an explicit
lifecycle transition.

After a project's cutover, its gateway operates only in opaque mode. Legacy
JWTs sent as `apikey` are not accepted as an alternate path.

## 2. Architectural decision

Official Supabase self-hosting supports one `sb_publishable_*` key and one
`sb_secret_*` key. The managed platform accepts multiple keys per project and
recommends one secret key per component. This project implements the latter
semantics in self-hosting through its own registry, without changing internal
Supabase services.

```text
client
  -> project Nginx
       -> auth_request / key-authorizer
            -> PostgreSQL in the control plane
       -> validates project, gateway, key, role, service, and time
       -> translates the opaque key to an internal anon/service_role JWT
       -> preserves the user's session JWT when present
       -> Supabase service
```

The `key-authorizer` is a data plane separate from the Projects API. It uses
its own PostgreSQL role, without superuser or `BYPASSRLS`, with `SELECT` only
on required columns and `UPDATE` only on `last_used_at`.

## 3. Primary references

- [Supabase — Understanding API keys](https://supabase.com/docs/guides/getting-started/api-keys): separates application identity from user authentication and recommends one secret key per component.
- [Supabase self-hosted — New API Keys and Asymmetric Authentication](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-keys): documents the one-key-per-role limitation, translation to an internal JWT, and Realtime flow.
- [Supabase self-hosted — Envoy API Gateway](https://supabase.com/docs/guides/self-hosting/self-hosted-envoy): current reference for routes, translation, and Realtime's `x-api-key`.
- [Supabase — User sessions](https://supabase.com/docs/guides/auth/sessions): short-lived access JWT, refresh token, and session-expiration policy.
- [Supabase — JWT Signing Keys](https://supabase.com/docs/guides/auth/signing-keys): key states, JWKS, and rotation without ending sessions whose JWTs remain valid.
- [Nginx `auth_request`](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html): subrequest authorization; only 2xx allows the request.
- [Nginx njs request reference](https://nginx.org/en/docs/njs/reference.html): documents that `$arg_*` returns the first argument, ignores case, and does not percent-decode; the authorizer compensates with raw `$args` as well.
- [Traefik access logs](https://doc.traefik.io/traefik/reference/install-configuration/observability/logs-and-accesslogs/): allows query parameters to be removed from logs; necessary because the Realtime WebSocket carries `apikey` in the URL.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): generation, least privilege, automation, auditing, rotation, revocation, and expiration.
- [AWS Secrets Manager rotation functions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html): reference for preparing, installing, testing, and completing a rotation.
- [JWT Best Current Practices — RFC 8725](https://datatracker.ietf.org/doc/rfc8725): basis for future signing migration.
- [Python `secrets`](https://docs.python.org/3/library/secrets.html): CSPRNG and constant-time comparison.
- [GitHub — token formats](https://github.blog/engineering/behind-githubs-new-authentication-token-formats/): identifiable prefix, separator, and checksum.
- [NIST SP 800-57 Part 1 Rev. 5](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): cryptographic-material management and distinct cryptoperiods.

## 4. Invariants

### 4.1 Fail-closed and no fallback

- The opaque gateway never compares a public credential with
  `ANON_KEY_PROJETO` or `SERVICE_ROLE_KEY_PROJETO`.
- Failure of the authorizer, database, gateway-exclusive token, or translation
  blocks the request.
- A key outside the canonical format is rejected before lookup.
- When configured, time-based expiration is enforced by PostgreSQL's clock in
  the authorization path; it does not depend on the scheduler having updated
  persisted status.
- An old key is never extended automatically.
- After a confirmed `activate_at`, the old key is never accepted again, even
  if the pending key expires before the scheduler persists cutover.
- There is no dual acceptance between a legacy public JWT and an opaque key
  after cutover.
- Transactional rollback of a write is allowed. After gateway cutover begins,
  canonical recovery is to complete the same cutover again; the legacy
  protocol is not restored automatically.

### 4.2 Separation of responsibilities

- `publishable` identifies a public component and translates to `anon`.
- `secret` identifies a confidential component and translates to
  `service_role`.
- `allowed_services` restricts each slot to an explicit subset of
  `auth`, `rest`, `graphql`, `realtime`, `storage`, and `functions`.
- RLS remains the data boundary for `publishable`.
- `secret` retains `service_role` impact and must never be embedded in a
  frontend, mobile app, or distributed artifact.
- The user's session JWT is preserved and validated by the destination service.
- Internal JWTs are not returned by `/config`, the Projects API, or the UI.

### 4.3 Secrets and auditing

- Each API key contains 32 random bytes generated by a CSPRNG.
- The registry persists only SHA-256 of the complete token.
- Plaintext appears only in a create/rotation response or in the encrypted
  reveal of the key version.
- The reveal is deleted when the version it belongs to stops authenticating.
- Plaintext responses use `Cache-Control: no-store`.
- Auditing and notifications record UUID, slot, action, and `token_hint`;
  never the token, hash, or internal JWT.
- Nginx does not produce an access log for the WebSocket route and Traefik
  removes all query parameters from access logs because Realtime transports
  the key in the upgrade URL.
- Each gateway's exclusive token is stored in the project `.env`, and the
  control plane persists only its hash.

## 5. Domain model

### 5.1 Slot

A slot represents a durable consumer, such as `web`, `android`,
`billing-worker`, or `backup`.

Tabela `project_api_key_slots`:

| Field | Contract |
| --- | --- |
| `id` | canonical UUID |
| `project_id` | cascading FK |
| `name` | `^[a-z][a-z0-9_-]{2,39}$`, no silent normalization |
| `kind` | `publishable` or `secret` |
| `allowed_services` | canonical, non-empty list without API duplicates |
| `automatic_rotation_enabled` | inherits the project option on creation |
| `rotation_interval_days` | `NULL` for no expiration or between 1 and 3650; default 90 |
| `status` | `active` or `disabled` |
| blocking fields | explicit automatic failure requiring intervention |
| `created_by` and timestamps | traceability |

There is at most one version persisted as `active` and one as `pending` per
slot. Different slots are different identities and may coexist.

The canonical contract uses the existing field as policy: `NULL` means
`never` and an integer means a timed lifetime. There is no redundant enum.
`automatic_rotation_enabled = true` requires an interval; an interval with
automation disabled is valid and means "expires without automatic replacement".
When switching from timed to `never`, the client must explicitly send both
fields; the API does not silently replace `true` with `false`.

### 5.2 Key version

Tabela `project_api_keys`:

| Field | Contract |
| --- | --- |
| `id` | public audit UUID |
| `slot_id` | consumer FK |
| `secret_hash` | globally unique digest |
| `token_hint` | non-authenticating visual identifier |
| `status` | `pending`, `active`, `revoked`, or `expired` |
| `activate_at` | scheduled cutover instant |
| `expires_at` | `NULL` for no time-based expiration or an absolute limit enforced in the data plane |
| `activated_at`, `revoked_at` | transition timestamps |
| `revealed_at`, `confirmed_at` | consumer delivery and confirmation |
| `last_used_at` | five-minute sampled telemetry |
| `replaces_key_id` | rotation lineage |
| `rotation_trigger` | `initial`, `manual`, or `automatic` |

`status` represents persisted state; `currently_accepted` is calculated from
slot and version state, confirmation, `activate_at`, `expires_at`, and the
existence of a new effective version. A row still persisted as `active` is
never accepted after a defined `expires_at`. `expires_at = NULL` removes
only this time event; revocation, disable, and cutover still apply.

### 5.3 Reveal

`project_api_keys_reveals` contains one row per key version, encrypted by the
project DEK with purpose/AAD including the key ID. `claim` decrypts without
consuming: a publishable key is readable by any project member and a secret key
requires project admin plus step-up on every read.

The row lives exactly as long as the version it belongs to. Rotation,
revocation, slot disable, and expiration delete the material of the version
that stops authenticating; `claim` on a key without stored material receives
`410 Gone`. `revealed_at` records the first delivery and still gates the
migration cutover.

### 5.4 Project state

`projects` contains:

- `api_keyset_version`: monotonic set version;
- `api_gateway_token_hash`: authenticates that project's Nginx;
- `opaque_keys_prepared_at`: initial prepared record;
- `opaque_gateway_cutover_started_at`: legacy entry removal has started and
  abort is no longer allowed;
- `opaque_keys_activated_at`: initial keys were activated;
- `opaque_gateway_ready_at`: opaque gateway started successfully.

Exposed states:

```text
legacy -> prepared -> gateway_recovery_required -> active
```

`prepared` can return transactionally to `legacy` only before cutover starts.
`gateway_recovery_required` advances to `active` only by repeating and
completing cutover.

## 6. Key format

```text
sb_publishable_<43-char-base64url>_<8-char-checksum>
sb_secret_<43-char-base64url>_<8-char-checksum>
```

- 43 characters encode 32 bytes without padding;
- checksum is the Base64URL prefix of
  `SHA-256(project_uuid || "|" || prefix || random)`;
- the checksum binds the token to the project and detects copy errors; it does
  not replace the authenticating hash;
- length, case, alphabet, separators, and whitespace must be canonical;
- the format is deliberately longer than the official self-host's 22 random
  characters.

## 7. Gateway rules

### 7.1 API-key sources

- `apikey` header for Auth, REST, GraphQL, Storage, and Functions.
- `apikey` query parameter for the Realtime WebSocket.
- Simultaneous header and query are accepted only when identical.
- Query must use exactly lowercase `apikey=<value>`, once, without
  percent-encoding. The authorizer compares `$arg_apikey` with raw `$args`
  to neutralize Nginx's permissive behavior.

### 7.2 Authorization

For protected routes:

1. without `Authorization`: injects `Bearer <internal-role-jwt>`;
2. `Bearer` containing the same opaque key: replaces it with the internal JWT;
3. another canonical `Bearer`: preserves it byte-for-byte as the user's session;
4. another opaque key or ambiguous value: rejects it.

Storage accepts requests without an API key to preserve signed URLs and SigV4.
In this case the authorizer still validates the project and gateway and
preserves `Authorization`. Storage and Functions also preserve custom
non-Bearer schemes when a valid API key is present.

Functions continues to require an API key according to this project's previous
policy. This is a deliberate divergence from the current official gateway,
which leaves Storage and Functions without API-key enforcement.

Realtime removes the opaque API key from the forwarded query, injects the
internal JWT into the query and `x-api-key` header, and preserves the other
arguments.

Existing public Auth verification/callback/authorize routes remain without an
API key. The rest of Auth, REST, GraphQL, Realtime, and Functions requires a
valid key. The exact `/rest/v1/` path requires the `service_role` role.

## 8. Canonical APIs

Any project member can query these routes. For the `member` role, the response
is filtered server-side and contains only `publishable` slots/reveals:

```text
GET    /api/projects/{project}/api-key-slots
GET    /api/projects/{project}/api-key-reveals
GET    /api/projects/{project}/opaque-api-keys/migration
```

Only a project or global admin can change the lifecycle:

```text
POST   /api/projects/{project}/api-key-slots
PATCH  /api/projects/{project}/api-key-slots/{slot_id}
POST   /api/projects/{project}/api-key-slots/{slot_id}/rotation
POST   /api/projects/{project}/api-key-slots/{slot_id}/rotation-confirmation
POST   /api/projects/{project}/api-key-slots/{slot_id}/activation
DELETE /api/projects/{project}/api-key-slots/{slot_id}/rotation
DELETE /api/projects/{project}/api-key-slots/{slot_id}

POST   /api/projects/{project}/opaque-api-keys/migration/prepare
POST   /api/projects/{project}/opaque-api-keys/migration/cutover
DELETE /api/projects/{project}/opaque-api-keys/migration
```

Claiming a `publishable` is allowed for any member. A claim, creation, or
rotation that returns `secret` plaintext simultaneously requires a project or
global admin and step-up authentication. The browser sends the current
account's password only to `POST /api/security/step-up`; OpenResty fixes the
session username, validates the password in Authelia, and discards the new
cookie produced by `/auth/api/firstfactor`.

The returned grant uses the `su1` prefix, an HMAC domain different from
`X-User-Token`, fixed five-minute validity, and binding to the user UUID,
login-cookie fingerprint, action, project ref, resource, and nonce. The
Projects API revalidates all bindings and consumes the nonce once in
PostgreSQL, in the operation's transaction whenever it is already
transactional. Password, grant, and plaintext do not enter a provider, cache,
database, audit, or logs. Failure of Authelia, signing, session,
authorization, expiration, or consumption produces an explicit error.

There are no legacy aliases. Listings return metadata; creation, immediate
rotation, and claim are the only responses that may contain plaintext.

The lifetime policy uses a single nullable representation:

```json
{
  "automatic_rotation_enabled": false,
  "rotation_interval_days": null
}
```

This state means "never expires". An integer from 1 to 3650 represents a timed
policy; `automatic_rotation_enabled` may be `true` or `false` in that
case. `true` with a `null` interval is rejected by the API and database.
Responses serialize `expires_at: null` without a sentinel date. Even the
3650-day limit remains a real expiration, never an alias for `never`.

## 9. Lifecycle and expiration

All lifecycle time decisions use PostgreSQL's transactional `now()`, the same
source used by the authorizer. The process clock does not advance or postpone
cutover.

There are two modes:

- integer `rotation_interval_days`: each new version receives `expires_at`;
  the version stops being accepted at that instant;
- `rotation_interval_days = NULL`: each new version receives
  `expires_at = NULL` and remains valid until rotation, revocation, disable,
  or another explicit cutover.

Changing the policy atomically updates only a still-valid active key. A change
to an interval counts the new lifetime from the database's `now()`. A
time-expired key cannot be revived by PATCH: it requires hard rotation. A
lifetime change with a manual or already-effective pending key is rejected; when
switching to `never` with simultaneous opt-out, an automatic preparation that
is not yet effective is canceled in the same transaction.

### 9.1 Creation and immediate rotation

A transaction locks the project and slot, revokes the active version, creates
the new active version with the current lifetime policy, increments
`api_keyset_version`, and records an audit event. There is no overlap. If the
secret response is lost, recovery is another explicit rotation.

### 9.2 Scheduled rotation

1. creates a `pending` version with `activate_at` and the slot's lifetime policy;
2. reveals the token;
3. the operator installs it in the consumer and confirms the key ID;
4. from `activate_at`, the authorizer accepts the confirmed pending key and
   stops accepting the previous one, even before the scheduler persists the
   transition;
5. the scheduler converts the pending key to `active`, revokes the previous
   one, and audits it.

Without confirmation, the pending key is not accepted. In a timed slot, the
previous key remains valid only until its original `expires_at` and is never
extended. In a slot without expiration, an unconfirmed manual preparation also
does not cut the previous key; the operator must confirm, cancel, or perform
hard rotation. A confirmed pending key cannot be canceled after `activate_at`;
logical cutover is monotonic and must converge to persisted `active`. An
explicit immediate rotation can replace it atomically, even if it has already
expired, without re-enabling the previous key.

### 9.3 Automatic rotation

- The project option starts as `true` and each slot inherits this value.
- Only timed slots can enable automatic rotation. Slots with
  `rotation_interval_days = NULL` are excluded from expiration, lead-time,
  and automatic-preparation queries.
- The scheduler uses an advisory lock and `FOR UPDATE SKIP LOCKED`.
- At lead time, it prepares a pending version with `activate_at` exactly equal
  to the active version's expiration.
- An admin receives a notification, claims, installs, and confirms it.
- At expiration, only the new confirmed key is accepted.
- Without confirmation or replacement, the slot fails closed and is blocked
  with an auditable error.
- Disabling the project or slot option cancels only automatic preparations
  before `activate_at`; it does not change active keys, an already-effective
  cutover, or manual rotations.
- Explicitly changing the slot policy to `NULL` is distinct from opt-out:
  besides disabling automation, it removes `expires_at` from the still-valid
  active key.

### 9.4 Relationship to JWTs

This delivery resolves public coupling: an opaque API key has no JWT `exp` and
does not change when the internal JWT is regenerated. Internal HS256
`anon`/`service_role` JWTs remain 90 days long and use the existing
scheduler, but are operational gateway secrets.

User session JWTs continue to expire according to Auth policy. This is intended
and is not solved by API keys. While the session is valid, the refresh token
issues a new access JWT; an API key cannot renew or extend a session.

Therefore, three TTLs must not be confused: opaque API-key lifetime, plaintext
reveal window, and JWT/session lifetime. Changing any one does not change the
other two.

The future ES256/JWKS phase addresses signing and signing-key rotation, not the
validity of each session. Its protocol will have explicit states `standby`,
`in_use`, `previously_used`, and `revoked`: Auth starts signing with the new key,
while the previous public key remains verifiable only until the largest TTL of
an already-issued access JWT expires, plus the JWKS propagation margin. Emergency
revocation ignores this window and deliberately ends the affected JWTs.

## 10. Provisioning and migration

### 10.1 New and duplicated projects

The generator creates a unique gateway token, materializes the opaque Nginx, and
the Projects API persists two active slots:

- `default-publishable`;
- `default-secret`.

Both keys stay readable while they exist. Create, duplicate, rename, restore,
internal JWT rotation, and Nginx recreation preserve the gateway-token contract.
`.env` readers require a single canonical entry.

### 10.2 Existing projects

1. `prepare` ensures the gateway token and creates the two initial slots as
   `pending`, still rejected by the legacy gateway;
2. an admin claims, installs both credentials, and confirms both;
3. `cutover` revalidates everything before any downtime;
4. persists `opaque_gateway_cutover_started_at`;
5. host-agent stops the legacy Nginx and materializes the opaque template;
6. activates both keys in a transaction;
7. starts the opaque Nginx;
8. persists `opaque_gateway_ready_at`.

Any failure after step 4 exposes `gateway_recovery_required`. Repeating
`cutover` is idempotent with respect to the already-confirmed state. There is no
automatic return to the legacy protocol.

Before step 4, `DELETE .../migration` removes the prepared record in a
transaction. After that milestone, abort is rejected.

## 11. Phases

### Phase 0 — specification and contracts

- [x] map the existing coupling;
- [x] review all project documents and templates;
- [x] research current primary references;
- [x] define format, states, APIs, migration, and invariants;
- [x] create contract tests.

### Phase 1 — control-plane registration

- [x] schema, constraints, and indexes;
- [x] generator/parser/hash/checksum;
- [x] slot and version CRUD;
- [x] encrypted reveal for the version lifetime;
- [x] administrative authorization and auditing;
- [x] protocol unit tests.

### Phase 2 — authorizer and gateway

- [x] dedicated `key-authorizer` service;
- [x] unique token per gateway;
- [x] least-privilege PostgreSQL role;
- [x] fail-closed lookup by project, hash, time, role, and service;
- [x] translation for Auth, REST, GraphQL, Realtime, Storage, and Functions;
- [x] Realtime through query and `x-api-key`;
- [x] removal of public comparisons against internal JWTs;
- [x] static and unit tests for bypass/ambiguity;
- [ ] negative HTTP tests in a real Docker stack.

### Phase 3 — lifecycle and migration

- [x] create and duplicate produce opaque projects;
- [x] rename, restore, and internal rotation preserve the gateway token;
- [x] explicit preparation, confirmation, cutover, and abort;
- [x] recovery state without reactivating the legacy gateway;
- [x] block recreation/internal rotation until the gateway is ready;
- [ ] real probes for Auth, REST, GraphQL, Realtime, Storage, and Functions.

### Phase 4 — asymmetric signing

- [ ] P-256 and per-project JWKS;
- [ ] Auth signs ES256 with the canonical `kid`;
- [ ] PostgREST, Realtime, and Storage receive the public JWKS;
- [ ] internal ES256 tokens;
- [ ] `standby`, `in_use`, `previously_used`, and `revoked` states;
- [ ] retain the previous key only for the largest issued TTL plus the JWKS
  propagation margin;
- [ ] separate normal rotation from emergency revocation;
- [ ] session tests during the cryptoperiod.

This phase has no partial implementation in this branch. HS256 remains internal
and uses its own rotation until a fully coordinated migration.

### Phase 5 — automation, UI, and observability

- [x] scheduler per slot;
- [x] pending, claim, confirmation, and cutover without overlap;
- [x] automatic default `true` with project- and slot-level opt-out;
- [x] UI for slots, reveal, confirmation, rotation, cancellation, and revocation;
- [x] auditing, `last_used_at`, and secret-free alerts;
- [ ] aggregated metrics and an SLO dashboard.

### Phase 6 — operational validation

- [x] protocol and contract smoke tests;
- [x] Python compilation/import;
- [x] Dart static analysis;
- [x] Bash syntax validation;
- [x] operations and incident runbook;
- [ ] build and tests in a real Docker stack;
- [ ] end-to-end probes and database/authorizer outage testing;
- [ ] release changelog after real validation.

## 12. Acceptance criteria

| ID | Criterion | Status |
| --- | --- | --- |
| `OK-SEC-001` | Legacy JWT used as `apikey` receives 403 | covered statically; E2E pending |
| `OK-SEC-002` | A key from another project receives 403 | covered by checksum/project and SQL |
| `OK-SEC-003` | A service outside `allowed_services` receives 403 | covered by authorizer |
| `OK-SEC-004` | An ineffective, revoked, or expired pending key receives 403 | covered by temporal query |
| `OK-SEC-005` | Database/authorizer unavailability produces 5xx and never grants access | covered by design; E2E pending |
| `OK-SEC-006` | Divergent or duplicated key sources receive 403 | covered by parser |
| `OK-SEC-007` | Session JWT is preserved | covered by contract; E2E pending |
| `OK-SEC-008` | Secret does not appear in logs/listings/audit | covered by static review |
| `OK-SEC-009` | Claim is atomic and unique | covered by `DELETE ... RETURNING` |
| `OK-SEC-010` | There is at most one active and one pending version per slot | covered by partial indexes |
| `OK-SEC-011` | A gateway token from another project receives 403 | covered by project-bound hash |
| `OK-SEC-012` | Invalid checksum is rejected before lookup | covered by unit test |
| `OK-SEC-013` | A member can view/generate claims only for `publishable` | covered by server-side filter and widget test |
| `OK-SEC-014` | Plaintext `secret` requires admin and action/session-bound step-up | covered by Python/Lua/Flutter contract |
| `OK-SEC-015` | Step-up grant is short-lived, one-time, and does not replace `X-User-Token` | covered by HMAC domain, prefix, and PostgreSQL ledger |
| `OK-FUN-001` | Project maintains multiple independent slots | implemented |
| `OK-FUN-002` | Revoking one slot does not affect the others | implemented |
| `OK-FUN-003` | supabase-js works before/after login | E2E pending |
| `OK-FUN-004` | Realtime connects with an opaque key in the query | E2E pending |
| `OK-FUN-005` | Internal JWT rotation does not change external API keys | implemented through separation |
| `OK-FUN-006` | Lifecycle preserves gateway identity | covered by contracts; E2E pending |
| `OK-FUN-007` | New projects inherit enabled automation | implemented |
| `OK-FUN-008` | Opt-out prevents new preparations without changing the active key | implemented |
| `OK-FUN-009` | An active key with `expires_at = NULL` is accepted until explicit transition | implemented |
| `OK-FUN-010` | Scheduler ignores `never` lifetime and keeps timed slots | implemented |
| `OK-FUN-011` | Policy changes do not resurrect an expired or revoked version | implemented |

## 13. Deferred decisions

- extend step-up to restore, revocation, policy changes, and other destructive
  actions that do not reveal plaintext;
- decide whether a future elevated window will allow multiple actions instead of
  the current strictly bound, one-time grants;
- scope by table, schema, function, or row;
- IP restriction and secret-key blocking by User-Agent;
- distributed cache/Redis in the authorizer;
- automatic integration with Vault, KMS, or external secret managers;
- rate limit and individual quota per key ID;
- removal of HS256 and migration to ES256/JWKS;
- replacement of Nginx with Envoy.

These items receive neither partial implementation nor a secondary path in this
change.
