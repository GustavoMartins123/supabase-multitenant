# Scoped API resource configuration

Projects API no longer mounts the server's complete `.env`. Resource limits
come solely from `/docker/resource-profiles.env`, a read-only projection of
twelve `PROJECT_RES_*` settings. The parser rejects missing/extra/duplicate keys
and unavailable files; it does not read the server env as a secondary path.

`start.sh` generates `servidor/.resource-profiles.env` before Docker startup in
both server topologies. For direct Compose deployment, first run:

```sh
python3 tools/configure_api_resource_profiles.py \
  --source servidor/.env --output servidor/.resource-profiles.env
```

The derived file is Git-ignored and contains no passwords or service keys.
Docker refuses a missing bind source instead of creating a directory. Regenerate
it after changing root resource settings; changes are read per operation.

The isolated Docker image test `test_api_resource_mount.py` checks absence of
`/docker/.env` and root PostgreSQL password, the exact profile set, legitimate
resolution and read-only behavior. This closes the full-file mount exposure,
not every privilege of the API: its declared lifecycle/admin credentials remain
explicit dependencies. The shared Functions runtime's global credentials and
all-tenants directory exposure require a separate correction.
