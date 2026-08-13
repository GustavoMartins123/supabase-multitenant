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
`supabase-storage-global` por poucos segundos para comprovar fail-closed:

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
