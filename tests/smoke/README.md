# Smoke tests

Os testes locais de contrato não acessam rede nem Docker:

```bash
python -m unittest discover -s tests/smoke -p "test_*.py" -v
```

Os testes ativos são opt-in e nunca usam valores padrão para secrets. Para
validar HMAC contra uma instalação em execução, configure:

```bash
export RUN_HMAC_SMOKE=1
export SMOKE_API_URL=https://servidor-interno
export SMOKE_SHARED_TOKEN=...
export SMOKE_USER_ID=...
export SMOKE_NGINX_HMAC_SECRET=...
export SMOKE_PUSH_URL=https://studio:9091/api/internal/push
export SMOKE_INTERNAL_HMAC_SECRET=...
python -m unittest tests.smoke.test_live_hmac -v
```

Para o ciclo completo do tenant, use um usuário admin global descartável:

```bash
export RUN_TENANT_LIFECYCLE_SMOKE=1
export SMOKE_API_URL=https://servidor-interno
export SMOKE_SHARED_TOKEN=...
export SMOKE_USER_TOKEN=...
export SMOKE_NGINX_HMAC_SECRET=...
python -m unittest tests.smoke.test_tenant_lifecycle -v
```

Para a matriz completa de Storage compartilhado, use exclusivamente uma
instalacao descartavel e dedicada. O teste cria cinco projetos, exercita
Storage/S3/Vectors/backup/restore/rename/duplicate/delete e interrompe o
`supabase-storage-global` por poucos segundos para comprovar fail-closed. Ele
também confirma que um Nginx de projeto não alcança a porta administrativa 5001:

```bash
export RUN_SHARED_STORAGE_SMOKE=1
export SMOKE_API_URL=https://servidor-interno
export SMOKE_PUBLIC_BASE_URL=https://supabase.example.com
export SMOKE_SERVER_ROOT=/opt/supabase-multitenant/servidor
export SMOKE_SHARED_TOKEN=...
export SMOKE_USER_TOKEN=...
export SMOKE_NGINX_HMAC_SECRET=...
python -m unittest tests.smoke.test_shared_storage_tenant_integration -v
```

O runner precisa executar no host do servidor, com `docker`, `bash`, acesso de
leitura aos diretorios de projeto/backup e permissao para reiniciar somente o
container global de Storage. Nao execute essa matriz em ambiente compartilhado
com trafego real.

`SMOKE_USER_TOKEN` precisa conter o claim `login_session` emitido pelo gateway.
O teste direto assina um grant de step-up específico para o projeto; ele não
possui nem aceita uma senha global de exclusão.

TLS é verificado por padrão. Para CA privada, informe `SMOKE_CA_FILE`. Somente
em laboratório isolado é possível usar `SMOKE_VERIFY_TLS=false`.

## Migrations do control plane contra Postgres real

`tests/integration/test_control_plane_migrations_postgres.py` cria dois
databases temporarios a partir do DSN administrativo, aplica as migrations e
remove tudo no final. Ele cobre instalacao limpa, upgrade de instalacao
existente, convergencia entre os dois caminhos e recusa de migration editada.
Nenhum objeto do control plane em uso e tocado, mas o DSN precisa poder criar e
remover databases:

```bash
export RUN_MIGRATIONS_INTEGRATION=1
export MIGRATIONS_ADMIN_DSN=postgres://supabase_admin:...@127.0.0.1:5432/postgres
python -m unittest tests.integration.test_control_plane_migrations_postgres -v
```

O teste precisa de `asyncpg`. Sem instalar nada no host, rode dentro da imagem
da Projects API:

```bash
docker run --rm --network rede-supabase \
  -v "$PWD:/repo:ro" -w /repo \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e RUN_MIGRATIONS_INTEGRATION=1 \
  -e MIGRATIONS_ADMIN_DSN=postgres://supabase_admin:...@172.50.200.10:6755/postgres \
  servidor-projects-api:latest \
  python -m unittest tests.integration.test_control_plane_migrations_postgres -v
```
