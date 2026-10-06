# Pooler connection limit

### 1. Relevant parameters

| Variable                   | Purpose                                                       |
| -------------------------- | ------------------------------------------------------------- |
| `POOLER_DEFAULT_POOL_SIZE` | Physical connections opened in Postgres **per tenant × user** |
| `POOLER_MAX_CLIENT_CONN`   | Client connections the pooler accepts before refusing them    |


### 2. Default values (new projects)

| Where to change            | Variable                   | Suggested value | Notes                                                                                               |
| ------------------------- | -------------------------- | -------------- | ---------------------------------------------------------------------------------------------------- |
| `servidor/.env`           | `POOLER_DEFAULT_POOL_SIZE` | `30`           | Physical connections per tenant × user (affects Postgres)                                           |
| **`generate_project.sh`** | `default_max_clients`      | `600`          | Client limit for **each** new tenant; not read from `.env`, change it directly in the script if needed |

```bash
# relevant excerpts (generate_project.sh)
--default_pool_size "$POOLER_DEFAULT_POOL_SIZE" \
--default_max_clients 600            # ← adjust here for another default
```

After editing, recreate Supavisor/the pooler normally so new projects use the new values:

```bash
docker compose -f servidor/docker-compose.yml \
  --env-file servidor/.env \
  up -d --force-recreate supabase-pooler
```

---

### 3. Changing existing projects

1. Connect to the database:

```bash
docker exec -it supabase-db psql -U supabase_admin
```

2. **All tenants**:

```sql
UPDATE _supavisor.tenants
SET    default_pool_size   = 40,
       default_max_clients = 2500;
```

3. **Specific tenant** (`meu_projeto`):

```sql
UPDATE _supavisor.tenants
SET    default_pool_size   = 50,
       default_max_clients = 3000
WHERE  external_id = 'meu_projeto';

-- (optional) adjust the pgbouncer user
UPDATE _supavisor.users
SET    pool_size = 50
WHERE  tenant_external_id = 'meu_projeto'
  AND  db_user            = 'pgbouncer';
```

4. Restart Supavisor:

```bash
docker restart supabase-pooler
```

---

### 4. Verification

```sql
-- Limits per tenant
SELECT external_id, default_pool_size, default_max_clients
FROM   _supavisor.tenants;

-- Postgres connections used by the pooler
SELECT datname, count(*)
FROM   pg_stat_activity
WHERE  application_name LIKE 'supavisor%'
GROUP  BY datname;
```

---

### 5. Common problems

| Symptom                                        | Cause                                    | Action                                       |
| ---------------------------------------------- | ---------------------------------------- | -------------------------------------------- |
| `max client connections reached`               | Low `POOLER_MAX_CLIENT_CONN`              | Raise the value or reduce idle clients       |
| `FATAL: sorry, too many clients already` in PG | Sum of `pool_size` > `max_connections`   | Reduce pools or increase `max_connections` |
| High pool latency                              | Small `pool_size`                          | Increase `pool_size`                       |
