# Project secret and Postgres-Meta connection rotation

## Objective and key separation

There are three independent key domains:

| Variable | Use | Location |
| --- | --- | --- |
| `PROJECT_SECRETS_MASTER_KEY` | Wraps per-project DEKs | only `projects-api` |
| `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` | Encrypted transport of `service_role` between the API and Studio Nginx | `projects-api` and Studio Nginx |
| `PG_META_CRYPTO_KEY` | `x-connection-encrypted` header for `postgres-meta-global` | `projects-api` and Postgres-Meta |

Each project receives a random DEK, recorded in `project_key_envelopes`.
`anon_key`, `service_role`, and `config_token` use AES-256-GCM with the
project DEK and AAD containing the project ID and column name. Moving a
ciphertext between tenants or purposes fails authentication.

The current `postgres-meta` accepts a single `CRYPTO_KEY`; therefore the
connection header must continue to use a separate global transit key. No
connection headers are persisted for re-encryption: the API generates a new
header for each request. The official image also exposes this separation as
`PG_META_CRYPTO_KEY`.

## Automatic rotation of internal anon and service-role JWTs

Each project still has `anon` and `service_role` JWTs issued with its
`JWT_SECRET_PROJETO` and a 90-day validity. In the opaque gateway they are
internal operational tokens, never API keys distributed to clients. Automatic
rotation is enabled by default, generates a new pair seven days before `exp`,
and does not change the JWT secret. Therefore it does not end GoTrue user
sessions or change any external opaque key.

The public per-slot lifecycle, including claim, confirmation, cutover, and
opt-out, is documented in
[Opaque API key operations](12-opaque-api-key-operations.md).

Operational state is stored in `projects`:

| Column | Meaning |
| --- | --- |
| `automatic_key_rotation_enabled` | per-project opt-out; default `true` |
| `key_expires_at` | validated common expiration for anon/service role |
| `last_key_rotation_at` | last persisted change |
| `automatic_key_rotation_blocked_at` | automation suspended after failure |
| `automatic_key_rotation_last_error` | explicit error requiring intervention |

The scheduler creates durable jobs with `trigger=automatic`. The host-agent
revalidates the signature, UUID, and project option before executing
`rotate_key.sh`. The script requires `PROJECT_UUID`, uses a random `jti` for
each token, updates files with transactional rollback, and does not write keys
to stdout/stderr.

After the script, the API validates both `exp` values, encrypts the values with
the tenant DEK, increments `project_key_version`, records an audit event, and
invalidates the Studio cache. Any failure ends the job and blocks new automatic
attempts. An admin must fix the cause and re-enable the option, or perform a
successful manual rotation.

Operational query:

```sql
SELECT name, automatic_key_rotation_enabled, key_expires_at,
       last_key_rotation_at, automatic_key_rotation_blocked_at,
       automatic_key_rotation_last_error
FROM projects
ORDER BY key_expires_at NULLS FIRST;
```

Disabling automation is a per-project decision, available in Studio or through
`PUT /api/projects/{project_ref}/automatic-key-rotation`. Do not change the
blocking fields manually because resumption through the API is audited and
immediately performs reconciliation.

### Criteria and references

The design follows these published principles:

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): automation, auditing, and creation/rotation/expiration metadata;
- [NIST SP 800-57 Part 1 Rev. 5](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): a cryptoperiod defined according to key risk and use;
- [AWS Secrets Manager — four-step rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html): explicit creation, application, testing, and completion steps;
- [AWS Secrets Manager — schedules](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html): a rotation window before expiration;
- [Google Cloud Secret Manager — rotation recommendations](https://docs.cloud.google.com/secret-manager/docs/rotation-recommendations): scheduled rotation and a consumer prepared for the new version;
- [HashiCorp Vault — automated credential rotation](https://developer.hashicorp.com/vault/docs/enterprise/automated-credential-rotation/overview): leader execution, persisted state, and explicit interruption after failure;
- [Supabase self-hosted Auth keys](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-keys) and [signing keys](https://supabase.com/docs/guides/auth/signing-keys): distinction between API keys and signing keys and the current path to asymmetric keys.

## Prerequisites

1. Make a consistent backup of the `postgres` database.
2. Generate two distinct Fernet keys for `PROJECT_SECRETS_MASTER_KEY` and
   `STUDIO_SERVICE_KEY_ENCRYPTION_KEY`:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Generate a third independent key with at least 32 characters for
`PG_META_CRYPTO_KEY`.
4. Confirm that all three keys are distinct.

## Initial migration

1. Set the following in the server `.env`:

   ```dotenv
   PROJECT_SECRETS_MASTER_KEY=<new-fernet-key>
   PROJECT_SECRETS_MASTER_KEY_ID=project-secrets-master-2026-07
   PROJECT_SECRETS_PREVIOUS_MASTER_KEYS=
   PG_META_CRYPTO_KEY=<distinct-transit-key>
   STUDIO_SERVICE_KEY_ENCRYPTION_KEY=<new-fernet-key>
   ```

2. Also set `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` in the Studio `.env`.
3. Recreate Studio Nginx, `projects-api`, and `postgres-meta-global` during
the same maintenance window. The API and Postgres-Meta must receive the same
`PG_META_CRYPTO_KEY`; Nginx and the API must receive the same transport key.
4. A new installation has no legacy data to migrate. In an existing
installation, provide the old key only when running the manual utility:

   ```bash
   LEGACY_FERNET_SECRET=<old-key> \
     python -m app.migrate_project_secrets --dry-run
   LEGACY_FERNET_SECRET=<old-key> \
     python -m app.migrate_project_secrets --apply
   ```

5. Verify that no legacy values remain:

   ```sql
   SELECT count(*) AS legacy_values
   FROM projects
   WHERE (anon_key IS NOT NULL AND anon_key NOT LIKE 'v2.%')
      OR (service_role IS NOT NULL AND service_role NOT LIKE 'v2.%')
      OR (config_token IS NOT NULL AND config_token NOT LIKE 'v2.%');
   ```

6. Run smoke tests for project listing, config-token access, PG metadata, and
Studio login. The runtime no longer accepts legacy values after migration.

The manual process is resumable and does not print secrets.

## Master-key rotation

1. Generate a new Fernet key and update:

   ```dotenv
   PROJECT_SECRETS_MASTER_KEY=<new-key>
   PROJECT_SECRETS_MASTER_KEY_ID=project-secrets-master-2026-10
   PROJECT_SECRETS_PREVIOUS_MASTER_KEYS=<previous-master-key>
   ```

2. Restart `projects-api` and run:

   ```bash
   python -m app.migrate_project_secrets --apply
   ```

   This only re-wraps the DEKs; project values do not need to be re-encrypted.
   After checking the logs and backup, remove the previous key from
   `PROJECT_SECRETS_PREVIOUS_MASTER_KEYS`.

## Per-tenant DEK rotation

To actually re-encrypt every value for each project, use a maintenance window
and run `--dry-run` first, followed by `--apply`:

```bash
python -m app.migrate_project_secrets --rotate-deks --dry-run
python -m app.migrate_project_secrets --rotate-deks --apply
```

You can limit the operation to one tenant as a canary:

```bash
python -m app.migrate_project_secrets --project my_tenant --rotate-deks --apply
```

## Postgres-Meta connection-key rotation

Because connection headers are ephemeral, there is no cryptographic backlog to
migrate. Coordinate a `PG_META_CRYPTO_KEY` change in `projects-api` and
`postgres-meta-global`, recreate both, and validate a metadata call. The
change must be coordinated because the current image supports a single
`CRYPTO_KEY`; while the keys differ, metadata calls fail closed and fall back
to `meta_trap`.

## Rollback

Do not discard any old key before a backup and all smoke tests. If the master
key rotation fails, restore the previous key in
`PROJECT_SECRETS_PREVIOUS_MASTER_KEYS` and restart only the API. If the
Postgres-Meta change fails, restore the same `PG_META_CRYPTO_KEY` in both
services and recreate them together.
