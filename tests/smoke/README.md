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
export SMOKE_DELETE_PASSWORD=...
python -m unittest tests.smoke.test_tenant_lifecycle -v
```

TLS é verificado por padrão. Para CA privada, informe `SMOKE_CA_FILE`. Somente
em laboratório isolado é possível usar `SMOKE_VERIFY_TLS=false`.
