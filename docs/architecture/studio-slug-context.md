# Supabase Studio tab context

## Objective

Each tab keeps its project exclusively through the URL:

```text
/project/<project_ref>/...
```

Resolution uses this path and, for same-origin calls, the
`X-Studio-Project-Ref` header that the client sends with the same ref.

## Contract

1. The Flutter selector opens `/project/<ref>`.
2. Nginx accepts the page only when `<ref>` matches
   `[a-z_][a-z0-9_]{2,39}`.
3. Studio reads the ref from the current URL and includes
   `X-Studio-Project-Ref: <ref>` in every same-origin request made by its
   HTTP transport.
4. The gateway resolves the context once, using the original path
   (`request_uri`) and/or the explicit header.
5. When path and header coexist, they must be identical. A mismatch returns
   `409 project_ref_mismatch`.
6. The captured ref is stored in `ngx.ctx.studio_request_project_ref`.
   Rewrites and the access gate use this same value; there is no second
   resolution.
7. Before obtaining any service role, the gateway queries the control plane and
   validates the user and project membership.

```text
aba /project/alpha
        |
        +-- pagina: path alpha --------------------+
        |                                          |
        +-- APIs: X-Studio-Project-Ref: alpha -----+--> single capture
                                                       |
                                                       +--> membership
                                                       +--> contexto alpha
                                                       +--> proxy alpha
```

## Accepted sources

| Request | Required source |
| --- | --- |
| Page `/project/<ref>` | `<ref>` path segment |
| API with ref in path | Path ref; header, if sent, must match |
| API without ref in path, such as profile and self-hosted list | `X-Studio-Project-Ref` |
| AI | Explicit header and `projectRef` in the body, both equal |
| Local S3 credentials | Path `/api/projects/<ref>/storage/s3-keys` |

Missing context fails closed. There is no fallback.

## Front-end state

The Studio patch also includes the ref in cache keys whose payload depends on
the project:

- self-hosted profile;
- self-hosted project list;
- local S3 credentials.

Therefore, tab navigation or restoration does not reuse data from another ref.

## Reproducible build

Upstream code is not copied into this repository. The image in
`studio/studio-slug/Dockerfile` fetches the exact commit
`20290c71bdc48bef1720bfe7d292f3b9e6154f7d`, validates
`studio-project-context.patch` with `git apply --check`, and only then builds
Studio following the official Dockerfile steps.

Updating Studio deliberately requires:

1. change the SHA;
2. reapply and review the patch;
3. validate the build and per-project flows;
4. update the smoke contracts.

## Security invariants

- `X-Studio-Project-Ref` identifies the requested context but does not grant
  access;
- the control plane remains the membership authority;
- the service role is never returned to the browser;
- the external header is removed after capture and replaced internally with a
  validated `X-Project-Ref`;
- endpoints without an explicit ref cannot select a project through global
  state.
