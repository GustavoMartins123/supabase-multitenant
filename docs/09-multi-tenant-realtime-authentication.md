# Multi-tenant Realtime authentication

Realtime is shared by all projects, but each project has its own JWT secret.

The implementation was changed to identify the tenant before validating the JWT for Realtime administrative routes.

## Tenant identity

The Realtime tenant uses the project's canonical UUID:

```text
external_id = <project_uuid>
```

The project ref continues to be used in the database name and the main CDC slot. The temporary broadcast slot uses a hash derived from the UUID:

```text
database: _supabase_<project_ref>
slot principal: supabase_realtime_replication_slot_<project_ref>
messages slot: supabase_realtime_messages_replication_slot_<project_uuid_hash>
```

This separation allows the project to be renamed without changing its canonical identity.

## Tenant registration

During creation, `generate_project.sh` receives:

```text
<project_ref> <project_uuid>
```

It generates a project-specific JWT secret and tokens whose issuer is the UUID:

```json
{
  "role": "anon",
  "iss": "<project_uuid>",
  "iat": 123,
  "exp": 456
}
```

The tenant is registered with an equivalent structure:

```json
{
  "tenant": {
    "name": "<project_uuid>",
    "external_id": "<project_uuid>",
    "jwt_secret": "<jwt_secret_do_projeto>",
    "extensions": [
      {
        "type": "postgres_cdc_rls",
        "settings": {
          "db_name": "_supabase_<project_ref>",
          "slot_name": "supabase_realtime_replication_slot_<project_ref>"
        }
      }
    ]
  }
}
```

## Tenant resolution in WebSocket

The project Nginx forwards the WebSocket to global Realtime and injects:

```text
Host: <project_uuid>.localhost
```

Realtime uses this host to resolve the correct tenant. The project ref must not be used as the tenant identity in this flow.

## Authentication for administrative routes

The main patch is in:

```text
servidor/volumes/realtime/router.ex
```

The current flow is:

```text
Bearer token
  -> extracts tenant_id from path, body, or query
  -> looks up the tenant or payload context
  -> obtains the specific JWT secret
  -> validates the signature
  -> validates the issuer
  -> authorizes or returns 403
```

### Existing-tenant context

For operations on an already registered tenant:

1. extract `tenant_id`;
2. query `Api.get_tenant_by_external_id`;
3. decrypt the `jwt_secret` stored by Realtime;
4. validate the token;
5. accept `iss` equal to the tenant UUID;
6. preserve compatibility with old tokens without `iss` only in this context.

### Creation context

For `POST /api/tenants`, the tenant does not exist yet.

The router uses the `jwt_secret` present in the payload and requires:

```text
claims.iss == tenant.external_id
```

## Fail-closed behavior

When a request identifies a tenant, authentication does not fall back to the global secret if the tenant JWT fails.

The code distinguishes three situations:

```text
without tenant_id
  -> may validate with the global API secret

resolved tenant
  -> validates only with the tenant secret

tenant_id provided, but context missing
  -> denies the request
```

This prevents a global token from silently replacing the specific authentication of an already identified tenant.

The global secret still exists for routes or operations that genuinely have no tenant context, but it cannot bypass tenant authentication.

## Replication slots

Each project has at least two types of slots.

### Main slot

Registered in the tenant's CDC extension:

```text
supabase_realtime_replication_slot_<project_ref>
```

### `realtime.messages` slot

Created by Realtime according to the broadcast connection:

```text
supabase_realtime_messages_replication_slot_<project_uuid_hash>
```

The modified function receives the tenant UUID, calculates SHA-256, and uses the first 16 hexadecimal characters in the slot name. Since the UUID does not change, the temporary slot remains stable during a rename.

## Rename

During a rename:

- the tenant UUID remains unchanged;
- the Realtime `external_id` remains unchanged;
- the database changes from `_supabase_<old_ref>` to `_supabase_<new_ref>`;
- the CDC extension must point to the new database;
- the main slot must follow the new project ref;
- the temporary broadcast slot remains derived from the same UUID;
- Nginx continues to inject the same UUID into Host.

The complete flow is in [Project lifecycle](architecture/project-lifecycle.md).

## Internal JWT rotation

Rotation of the internal anon and service-role JWTs reuses the project's JWT
secret. Applications use opaque keys, so this operation does not require
redistributing an API key.

It:

- generates new tokens;
- keeps the same UUID issuer;
- updates Nginx and the control plane;
- does not replace the Realtime tenant.

Changing the JWT secret is a different operation because it invalidates existing tokens and sessions and requires coordinated synchronization.

## Security

Invariants:

- each project has its own JWT secret;
- the issuer of new tokens is the project UUID;
- a token from one project does not validate in another;
- an identified tenant does not accept the global fallback;
- Nginx delegates the opaque key to `key-authorizer` before the WebSocket proxy and
  injects the internal JWT into `x-api-key`;
- Realtime validates the JWT again with the tenant secret;
- the database and main slot remain isolated by project ref;
- the temporary broadcast slot remains isolated by the UUID hash.

## Related files

- `servidor/volumes/realtime/router.ex`
- `servidor/volumes/realtime/replication_connection.ex`
- `servidor/volumes/realtime/tenant_controller_test.exs`
- `servidor/generateProject/generate_project.sh`
- `servidor/generateProject/duplicate_project.sh`
- `servidor/generateProject/rename_project.sh`
- `servidor/generateProject/nginxtemplate`
