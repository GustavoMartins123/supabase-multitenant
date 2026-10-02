# Canonical Studio administrative transport

```
browser --Authelia cookie--> Studio Lua
Lua --service HMAC + signed human identity--> Traefik / Projects API
Lua --tenant administrative sb_secret--> Traefik / tenant gateway
tenant gateway --service-role JWT--> REST / GraphQL / Storage
```

The credential is **one private, stable, random key per project**, stored in
`project_studio_keys`, not in external API-key slots. At rest it uses the project's
AES-GCM envelope and the separate `studio-administrative-key` purpose. The API sends
only Fernet transport ciphertext to Lua after checking current project-admin access.
There is no universal cross-tenant key, browser reveal endpoint, or JWT compatibility
mode. The external authorizer still requires canonical checksummed opaque credentials.

The gateway accepts this key only for REST, GraphQL, and Storage, translating it to
the project's current service role. Lua does not cache authorization across requests.
The same HTTP(S) path passes through server Traefik on one or two machines; no Studio
access to the server's Docker network is required. Existing HMAC-authenticated Auth
and SQL administration retain their server-side human authorization gates.

Administrative matrix:

| Actor | Studio REST/GraphQL/Storage (including objects and vectors) |
| --- | --- |
| member / former member / disabled user | denied |
| project admin / owner with admin membership | allowed |
| active global administrator | allowed |

Members may view permitted platform metadata but do not receive a service credential
or gain object access through Studio. External application-user Storage access continues
using its own opaque key/user JWT and RLS, independently of Studio administration.

The key is provisioned atomically on first authorized use. JWT rotation does not change
it. Incident revocation sets `is_active=false, revoked_at=now()` under the project row
lock. It is never silently recreated: an installer/privileged maintenance transaction
must explicitly delete/reprovision the revoked record to rotate it. Old keys immediately
fail in the authorizer. A browser cannot request these internal API paths directly.
