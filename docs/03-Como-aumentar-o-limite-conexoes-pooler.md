# Como aumentar o limite conexoes pooler

### 1. Parâmetros que importam

| Variável                   | Pra que serve                                                 |
| -------------------------- | ------------------------------------------------------------- |
| `POOLER_DEFAULT_POOL_SIZE` | Conexões físicas abertas no Postgres **por tenant × usuário** |
| `POOLER_MAX_CLIENT_CONN`   | Conexões de clientes que o pooler aceita antes de recusar     |


### 2. Valores padrões (novos projetos)

| Onde ajustar              | Variável                   | Valor sugestão | Observação                                                                                           |
| ------------------------- | -------------------------- | -------------- | ---------------------------------------------------------------------------------------------------- |
| `servidor/.env`           | `POOLER_DEFAULT_POOL_SIZE` | `30`           | Conexões físicas por tenant × usuário (afeta Postgres)                                               |
| **`generate_project.sh`** | `default_max_clients`      | `600`          | Limite de clientes para **cada** novo tenant; não vem do `.env`, altere direto no script se precisar |

```bash
# trechos relevantes (generate_project.sh)
--default_pool_size "$POOLER_DEFAULT_POOL_SIZE" \
--default_max_clients 600            # ← ajuste aqui se quiser outro padrão
```

Depois de editar, recrie o Supavisor/pooler normalmente para que os novos projetos usem os novos valores:

```bash
docker compose -f servidor/docker-compose.yml \
  --env-file servidor/secrets/.env \
  --env-file servidor/.env \
  up -d --force-recreate supabase-pooler
```

---

### 3. Alterando projetos já criados

1. Entre no banco:

```bash
docker exec -it supabase-db psql -U supabase_admin
```

2. **Todos os tenants**:

```sql
UPDATE _supavisor.tenants
SET    default_pool_size   = 40,
       default_max_clients = 2500;
```

3. **Tenant específico** (`meu_projeto`):

```sql
UPDATE _supavisor.tenants
SET    default_pool_size   = 50,
       default_max_clients = 3000
WHERE  external_id = 'meu_projeto';

-- (opcional) ajustar o usuário pgbouncer
UPDATE _supavisor.users
SET    pool_size = 50
WHERE  tenant_external_id = 'meu_projeto'
  AND  db_user            = 'pgbouncer';
```

4. Reinicie o supavisor:

```bash
docker restart supabase-pooler
```

---

### 4. Verificação

```sql
-- Limites por tenant
SELECT external_id, default_pool_size, default_max_clients
FROM   _supavisor.tenants;

-- Conexões Postgres usadas pelo pooler
SELECT datname, count(*)
FROM   pg_stat_activity
WHERE  application_name LIKE 'supavisor%'
GROUP  BY datname;
```

---

### 5. Problemas comuns

| Sintoma                                        | Causa                                    | Ação                                         |
| ---------------------------------------------- | ---------------------------------------- | -------------------------------------------- |
| `max client connections reached`               | `POOLER_MAX_CLIENT_CONN` baixo           | Elevar valor ou reduzir ociosos              |
| `FATAL: sorry, too many clients already` no PG | Soma dos `pool_size` > `max_connections` | Diminuir pools ou aumentar `max_connections` |
| Latência alta no pool                          | `pool_size` pequeno                      | Aumentar `pool_size`                         |