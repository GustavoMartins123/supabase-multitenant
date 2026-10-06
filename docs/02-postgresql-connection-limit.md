# PostgreSQL connection limit


### 1. Relevant parameters

| Parameter              | Purpose                                               |
| ---------------------- | ---------------------------------------------------- |
| `max_connections`      | Maximum number of simultaneous sessions               |
| `shared_buffers`       | Database page cache (allocated at startup)             |
| `work_mem`             | Memory per operation (ORDER BY, JOIN, etc.)            |
| `effective_cache_size` | Hint to the optimizer about available RAM              |

---

### 2. Where to change it

File **`servidor/docker-compose.yml`** → **`db`** service → **`command`** block.

```yaml
services:
  db:
    # …
    command:
      - postgres
      - -c
      - max_connections=1000   # ← change here
      - -c
      - shared_buffers=2GB
      # …
```

---

### 3. Applying the change

1. Edit the `max_connections` value.
2. Save the file.
3. Recreate the container so the parameter is loaded:

```bash
# from the project root
docker compose -f servidor/docker-compose.yml \
  --env-file servidor/.env \
  up -d --force-recreate db
```

> **Important:** `restart` alone is not enough; use `--force-recreate`.

---

### 4. Memory impact

```
Total usage ≈ shared_buffers (fixed) + max_connections × work_mem (variable)
```

*In the example* (`shared_buffers=2 GB`, `work_mem=8 MB`, `max_connections=1000`):

```
2 GB + 1000 × 8 MB ≈ 10 GB
```

In practice, few connections use `work_mem` at the same time, and Supavisor provides pooling.

---

### 5. Useful queries

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity;

-- Configured limit
SHOW max_connections;

-- Current memory values
SELECT name, setting, unit
FROM pg_settings
WHERE name IN ('max_connections','shared_buffers','work_mem','effective_cache_size');
```

---

### 6. Common problems

| Error / Symptom                          | Likely cause                               | Action                                        |
| ---------------------------------------- | ----------------------------------------- | --------------------------------------------- |
| `FATAL: sorry, too many clients already` | Connections > `max_connections`           | Increase the limit or optimize pooling        |
| High RAM usage                            | Excessive `work_mem` or `shared_buffers` | Lower the values or add RAM                  |
| General slowness                          | Undersized cache or WAL                     | Adjust `effective_cache_size`, review indexes |

---

### 7. Quick check

```bash
# container running?
docker ps | grep db

# logs
docker logs supabase-db

# confirm the new limit
docker exec -it supabase-db psql -U supabase_admin -c "SHOW max_connections;"
```
