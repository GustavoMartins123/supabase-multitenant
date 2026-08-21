# Opaque API key operations runbook

This runbook covers creation, migration, rotation, optional expiration policy,
and incident response for project-managed `sb_publishable_*` and
`sb_secret_*` keys. The complete design and acceptance criteria are in the
[specification](specs/opaque-api-keys.md).

## Operational rules

- Use one slot per consuming application or service.
- Never reuse an `sb_secret_*` across different components.
- Do not put secret keys in frontends, mobile apps, repositories, URLs, or
  logs.
- A key stays readable while its version exists. Copy it directly into the
  consumer's secret manager instead of leaving it on screen.
- Any project member can reveal a `publishable`. Creating, changing, or
  rotating slots still requires a project admin or global admin.
- `secret` plaintext requires an admin and reauthentication with that account's
  own password. There is no global key password or server password in this
  flow.
- **Never expires** removes only the time-based expiration. It does not prevent
  rotation, revocation, disabling, service restrictions, or any other explicit
  cutover.
- Credential lifetime and JWT/session lifetime are independent policies.
- Confirm installation only after the correct value is in the consumer.
- Do not distribute `ANON_KEY_PROJETO`, `SERVICE_ROLE_KEY_PROJETO`, or
  `API_GATEWAY_TOKEN_PROJETO`; they are internal materials.
- Do not bypass an authorization failure. Fix the canonical state and repeat
  the indicated operation.

## Pre-check

Before creating or migrating keys:

1. confirm that `projects-api`, `host-agent`, PostgreSQL, and
   `key-authorizer` are healthy;
2. confirm that the host and PostgreSQL clocks are synchronized;
3. open the project in Studio with an owner/admin account;
4. prepare the secret manager and deployment for each consumer;
5. reserve a window for migrating legacy projects because there is no
   dual-acceptance period.

The authorizer's internal health check is `/healthz`. It must not be exposed to
the Internet.

## Schema update

The Projects API applies the
`20260812_opaque_api_key_optional_expiration.sql` migration when it detects
the previous schema. It makes `rotation_interval_days` and
`project_api_keys.expires_at` nullable, replaces the constraints, and adapts
the expiration index. It does not run an `UPDATE` on keys: all existing rows
preserve their `expires_at`.

After deployment, confirm that the migration finished before allowing policy
PATCH requests. A migration failure prevents canonical Projects API startup;
do not change constraints manually to bypass the error.

The deployment also applies `20260812_step_up_grants.sql`, which creates only
the reauthentication-grant consumption ledger. It records actor, hashed
session, action, target, and timestamps; it never stores a password, bearer
token, or API-key plaintext. A failure of this migration prevents Projects API
startup.

## New or duplicated project

New and duplicated projects are created in `active` mode with:

- `default-publishable`;
- `default-secret`.

Initial slots keep the 90-day timed default with automation enabled; this
avoids silently changing the policy of existing installations. The admin can
select **Never expires** after creation.

1. In Studio, open the project settings and the API keys section.
2. Claim each required key. `publishable` is available to all members;
   `secret` requests an admin's personal password.
3. Store the publishable key in the public client configuration.
4. Store the secret key only in the secret manager of a trusted backend.
5. Create additional slots for independent consumers.
6. Revoke an initial slot that will not be used.

Rotation deletes the plaintext of the version it replaces: after rotating, only
the new key can be read.

## Existing-project migration

### 1. Prepare

In Studio, choose **Prepare opaque migration**. The operation:

- creates the gateway's exclusive internal token;
- creates `default-publishable` and `default-secret` as `pending`;
- does not change the gateway currently serving the project.

The status changes from `legacy` to `prepared`. Prepared keys are still
rejected and cannot be used for parallel testing.

### 2. Reveal, install, and confirm

For each key:

1. claim it before the seven-day deadline; for `secret`, use an admin account
   and reauthenticate with that same account's password;
2. put the value in the consumer's secret manager/configuration;
3. prepare the deployment to use the new value at cutover;
4. confirm the installed key ID in Studio.

Cutover is released only when both keys have been revealed and confirmed.
Confirmation is an operational statement; it does not test the consumer.

### 3. Cut over

Trigger **Complete migration** within the reserved window. The Projects API:

1. revalidates both slots and confirmations;
2. marks the irreversible start of cutover;
3. stops the legacy Nginx;
4. materializes the opaque gateway;
5. activates both keys in the same transaction;
6. starts the gateway and marks `active`.

After cutover, old public JWTs receive 403 when used as an API key. Update the
consumers as part of the same operational event.

### Abort before cutover

While the status is `prepared`, **Abort preparation** removes the prepared
record and returns the project to `legacy`. Once `cutover_started_at` exists,
abort is rejected.

### Recovery during cutover

If the status is `gateway_recovery_required`, fix the cause indicated by the
job and run **Complete/recover migration** again. The operation resumes the
same state and does not reactivate the legacy protocol.

Minimum checks after success:

```bash
curl -i "https://HOST/PROJETO/auth/v1/settings" \
  -H "apikey: SB_PUBLISHABLE"

curl -i "https://HOST/PROJETO/rest/v1/" \
  -H "apikey: SB_SECRET"
```

Also verify login, an RLS-protected REST query, GraphQL, a Realtime connection,
a Storage operation, and a Function. A legacy JWT used as `apikey` must
receive 403.

## Create additional slots

Choose names tied to the consumer, for example:

- `web-production` — publishable;
- `android-production` — publishable;
- `billing-worker` — secret;
- `backup-nightly` — secret.

Restrict `allowed_services` to what is necessary. Creation activates the key
immediately and returns the value; the same value can be read again from the
API keys section.

Also choose the slot expiration:

- **Never expires**: `rotation_interval_days = NULL`,
  `automatic_rotation_enabled = false` and `expires_at = NULL`;
- **90/180/365 days or custom**: the key receives `expires_at`; automatic
  rotation can remain enabled or be disabled independently.

Disabling only automatic rotation does not remove an already defined
expiration. To switch to `never`, also send
`automatic_rotation_enabled: false` in the same operation. The API rejects
enabled automation without a time interval and does not silently replace this
value.

## Change the expiration policy

The change uses PostgreSQL's transactional clock, increments
`api_keyset_version`, and is audited. It applies only to the still-valid
`active` version; `revoked`/`expired` versions are never reactivated.

### Timed to never expires

1. confirm that no manual rotation is pending;
2. in Studio, select **Key expiration → Never expires**;
3. confirm the warning;
4. verify `rotation_interval_days = NULL`,
   `automatic_rotation_enabled = false`, and `expires_at = NULL` in the list;
5. validate the consumer and the audit record.

An automatic preparation that is not yet effective is canceled in the same
transaction. A manual pending state, an already-effective pending state, or an
already-expired active key causes the operation to fail explicitly. For an
expired key, perform a hard rotation.

### Never expires to timed

1. select 90, 180, 365 days, or an interval between 1 and 3650;
2. confirm the change; the new `expires_at` is calculated from the database's
   `now()`;
3. enable automatic rotation if you want lead-time preparation;
4. validate the displayed date, consumer, and audit record.

If there is a pending state, complete or cancel that lifecycle before changing
the policy. Changing the policy does not change the key material.

## Manual rotation

### Immediate cutover

Use this for a compromise or emergency change. The previous version is revoked
and the new one takes effect in the same transaction, without overlap.

1. run **Rotate now**;
2. capture the new value;
3. update the consumer;
4. validate the service.

There is unavailability between cutover and consumer update. This is the
intentional semantics of hard rotation.

For a slot with no expiration, the same procedure creates another key with
`expires_at = NULL`; the previous key is still revoked atomically. **Never
expires** never authorizes reuse of the compromised version.

### Scheduled cutover

Scheduling is done through the internal API
`POST /internal/projects/{project}/api-key-slots/{slot_id}/rotation`; Studio
exposes only immediate cutover at this stage.

1. send `activate_at` in ISO 8601 with a timezone;
2. capture the returned `pending` key;
3. install it in the consumer;
4. confirm the key ID;
5. wait for `activate_at` or activate it once it is due.

A confirmed pending key becomes accepted at the scheduled time and the old key
stops being accepted. The scheduler persists the transition afterward.

A preparation can be canceled before it takes effect. A confirmed pending key
that has reached `activate_at` cannot be canceled because that would bring the
previous key back. Canceling revokes only the pending key; it does not create
another key.

If an effective pending key expires during a prolonged scheduler outage, run
**Rotate now**. The emergency cutover revokes the pending and previous keys in
the same transaction and provides a new credential.

## Automatic rotation

Automation is enabled by default on the project and inherited by each slot.

1. at lead time, Studio receives a pending-key notification;
2. claim and install the key;
3. confirm before the active version expires;
4. cutover occurs exactly at the old expiration time.

Without confirmation, no new key is accepted and the old one expires at its
original time. The slot enters a blocked state with an explicit error.

Opt-out can be applied to the entire project or to a slot. Disabling it cancels
only pending automatic preparations and does not extend the active key.
Slots configured as **Never expires** are not scheduler candidates and do not
generate automatic pending keys. Explicitly scheduled manual cutovers continue
to be processed.

## Incidents

### Exposed secret key

1. identify the slot using `token_hint` and audit events;
2. as a project or global admin, perform an immediate rotation and
   reauthenticate with your personal password before receiving the new
   plaintext;
3. distribute the new key through the secret manager;
4. remove the exposed key from code, logs, and artifacts;
5. review `last_used_at`, audit records, and access to allowed services;
6. fix the cause of the leak before creating another credential.

Do not reveal or restore the old version.

For a key with no expiration, do not wait for a time event: perform a hard
rotation immediately. If the slot is no longer needed, use **Revoke slot**.
Both operations remain authoritative over `expires_at = NULL`.

If Authelia or grant validation is unavailable, do not try to obtain the secret
through another route. Preserve/revoke the slot as the incident allows and
restore the canonical authentication path first.

### Key expired without replacement

The authorizer rejects the key even if the persisted status still appears as
`active`. `currently_accepted=false` is the effective information.

- If there is no pending key: perform an immediate rotation.
- If there is a valid pending key: claim, install, confirm, and activate it.
- If the pending key expired: cancel it and perform an immediate rotation.

### Authorizer or database unavailable

Protected Auth, REST, GraphQL, Realtime, and Functions fail with 5xx; Storage
continues through the subrequest even when it did not receive an API key.
Restore `key-authorizer` or its database connection. Do not remove
`auth_request`, inject a public JWT, or enable a bypass route.

### Interrupted migration

- `prepared`: complete distribution or abort before cutover.
- `gateway_recovery_required`: fix host-agent/Docker/template and repeat the
  cutover.
- `active`: do not run migration again; manage slots normally.

## Audit and safe diagnostic data

The following are safe for tickets and internal dashboards:

- project ref/UUID;
- slot ID and name;
- key ID;
- `token_hint`;
- `api_keyset_version`;
- status, timestamps, and error code.

Never copy the following to tickets or logs:

- complete opaque key;
- key hash;
- JWT interno anon/service role;
- JWT secret;
- gateway-exclusive token;
- reveal ciphertext.

## Scope of this delivery

Opaque API keys do not change user-session expiration. Signing remains HS256
internally in this phase. P-256/ES256/JWKS migration is a separate phase and
requires coordinated cutover across Auth, PostgREST, Realtime, and Storage.
User access JWTs remain short-lived and are renewed by refresh token while the
session is valid; no API key extends the session.
