# Como aumentar o limite conexoes postgres


### 1. Parâmetros que importam

| Parâmetro              | Pra que serve                                        |
| ---------------------- | ---------------------------------------------------- |
| `max_connections`      | Número máximo de sessões simultâneas                 |
| `shared_buffers`       | Cache de páginas do banco (alocado na inicialização) |
| `work_mem`             | Memória por operação (ORDER BY, JOIN, etc.)          |
| `effective_cache_size` | Dica para o otimizador sobre RAM disponível          |

---

### 2. Onde alterar

Arquivo **`servidor/docker-compose.yml`** → serviço **`db`** → bloco **`command`**.

```yaml
services:
  db:
    # …
    command:
      - postgres
      - -c
      - max_connections=1000   # ← troque aqui
      - -c
      - shared_buffers=2GB
      # …
```

---

### 3. Aplicando a mudança

1. Edite o valor de `max_connections`.
2. Salve o arquivo.
3. Recrie o contêiner para que o parâmetro seja carregado:

```bash
# na raiz do projeto
docker compose -f servidor/docker-compose.yml \
  --env-file servidor/secrets/.env \
  --env-file servidor/.env \
  up -d --force-recreate db
```

> **Importante:** `restart` sozinho não basta; use `--force-recreate`.

---

### 4. Impacto em memória

```
Uso total ≈ shared_buffers (fixo) + max_connections × work_mem (variável)
```

*No exemplo* (`shared_buffers=2 GB`, `work_mem=8 MB`, `max_connections=1000`):

```
2 GB + 1000 × 8 MB ≈ 10 GB
```

Na prática, poucas conexões usam `work_mem` ao mesmo tempo e o Supavisor faz pooling.

---

### 5. Consultas úteis

```sql
-- Conexões ativas
SELECT count(*) FROM pg_stat_activity;

-- Limite configurado
SHOW max_connections;

-- Valores atuais de memória
SELECT name, setting, unit
FROM pg_settings
WHERE name IN ('max_connections','shared_buffers','work_mem','effective_cache_size');
```

---

### 6. Problemas comuns

| Erro / Sintoma                           | Causa provável                            | Ação                                          |
| ---------------------------------------- | ----------------------------------------- | --------------------------------------------- |
| `FATAL: sorry, too many clients already` | Conexões > `max_connections`              | Aumente o limite ou otimize pool              |
| RAM alta                                 | `work_mem` ou `shared_buffers` exagerados | Reduza valores ou adicione RAM                |
| Lentidão geral                           | Cache ou WAL subdimensionados             | Ajuste `effective_cache_size`, revise índices |

---

### 7. Checagem rápida

```bash
# container em execução?
docker ps | grep db

# logs
docker logs supabase-db

# confirmar novo limite
docker exec -it supabase-db psql -U supabase_admin -c "SHOW max_connections;"
```
