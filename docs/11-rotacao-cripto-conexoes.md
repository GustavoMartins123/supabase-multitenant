# Rotação de segredos de projeto e conexões do Postgres-Meta

## Objetivo e separação de chaves

Há três domínios de chave independentes:

| Variável | Uso | Onde fica |
| --- | --- | --- |
| `PROJECT_SECRETS_MASTER_KEY` | Envelopa os DEKs por projeto | apenas `projects-api` |
| `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` | Transporte cifrado da `service_role` entre API e Nginx Studio | `projects-api` e Nginx Studio |
| `PG_META_CRYPTO_KEY` | Header `x-connection-encrypted` para `postgres-meta-global` | `projects-api` e Postgres-Meta |

Cada projeto recebe um DEK aleatório, registrado em `project_key_envelopes`.
`anon_key`, `service_role` e `config_token` usam AES-256-GCM com o DEK do
projeto e AAD contendo o id do projeto e o nome da coluna. Mover um ciphertext
entre tenants ou entre finalidades falha na autenticação.

O `postgres-meta` atual aceita uma única `CRYPTO_KEY`; portanto o header de
conexão precisa continuar com uma chave de trânsito global separada. Não há
headers de conexão persistidos para recriptografar: a API gera um novo header a
cada requisição. A imagem oficial também expõe essa separação como
`PG_META_CRYPTO_KEY`.

## Rotação automática de anon e service role

As API keys legadas de cada projeto são JWTs emitidos com o
`JWT_SECRET_PROJETO` daquele tenant e validade de 90 dias. A rotação automática
é habilitada por padrão, gera um par novo sete dias antes do `exp` e não altera
o JWT secret. Por isso ela não encerra sessões de usuários do GoTrue.

O estado operacional fica em `projects`:

| Coluna | Significado |
| --- | --- |
| `automatic_key_rotation_enabled` | opt-out por projeto; padrão `true` |
| `key_expires_at` | vencimento comum validado de anon/service role |
| `last_key_rotation_at` | última troca persistida |
| `automatic_key_rotation_blocked_at` | automação suspensa após falha |
| `automatic_key_rotation_last_error` | erro explícito que exige intervenção |

O agendador cria jobs duráveis com `trigger=automatic`. O host-agent revalida a
assinatura, o UUID e a opção do projeto antes de executar `rotate_key.sh`. O
script exige `PROJECT_UUID`, usa `jti` aleatório em cada token, atualiza arquivos
com rollback transacional e não escreve as chaves em stdout/stderr.

Depois do script, a API valida os dois `exp`, cifra os valores com o DEK do
tenant, incrementa `project_key_version`, grava auditoria e invalida o cache do
Studio. Qualquer falha encerra o job e bloqueia novas tentativas automáticas. Um
admin precisa corrigir a causa e reabilitar a opção, ou executar uma rotação
manual bem-sucedida.

Consulta operacional:

```sql
SELECT name, automatic_key_rotation_enabled, key_expires_at,
       last_key_rotation_at, automatic_key_rotation_blocked_at,
       automatic_key_rotation_last_error
FROM projects
ORDER BY key_expires_at NULLS FIRST;
```

Desabilitar a automação é uma decisão por projeto, disponível no Studio ou na
rota `PUT /api/projects/{project_ref}/automatic-key-rotation`. Não altere os
campos de bloqueio manualmente, pois a retomada pela API é auditada e executa a
reconciliação imediatamente.

### Critérios e referências

O desenho segue estes princípios publicados:

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): automação, auditoria e metadata de criação/rotação/expiração;
- [NIST SP 800-57 Part 1 Rev. 5](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): cryptoperiod definido conforme risco e uso da chave;
- [AWS Secrets Manager — four-step rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html): etapas explícitas de criação, aplicação, teste e conclusão;
- [AWS Secrets Manager — schedules](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html): janela de rotação antes do vencimento;
- [Google Cloud Secret Manager — rotation recommendations](https://docs.cloud.google.com/secret-manager/docs/rotation-recommendations): rotação programada e consumidor preparado para a nova versão;
- [HashiCorp Vault — automated credential rotation](https://developer.hashicorp.com/vault/docs/enterprise/automated-credential-rotation/overview): execução por líder, estado persistido e interrupção explícita após falha;
- [Supabase self-hosted Auth keys](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-keys) e [signing keys](https://supabase.com/docs/guides/auth/signing-keys): distinção entre API keys e signing keys e caminho atual para chaves assimétricas.

## Pré-requisitos

1. Faça backup consistente da base `postgres`.
2. Gere duas chaves Fernet distintas para `PROJECT_SECRETS_MASTER_KEY` e
   `STUDIO_SERVICE_KEY_ENCRYPTION_KEY`:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Gere uma terceira chave independente com pelo menos 32 caracteres para
   `PG_META_CRYPTO_KEY`.
4. Confirme que as três chaves são distintas entre si.

## Migração inicial

1. Defina no `.env` do servidor:

   ```dotenv
   PROJECT_SECRETS_MASTER_KEY=<nova-chave-fernet>
   PROJECT_SECRETS_MASTER_KEY_ID=project-secrets-master-2026-07
   PROJECT_SECRETS_PREVIOUS_MASTER_KEYS=
   PG_META_CRYPTO_KEY=<chave-de-transito-distinta>
   STUDIO_SERVICE_KEY_ENCRYPTION_KEY=<nova-chave-fernet>
   ```

2. Defina `STUDIO_SERVICE_KEY_ENCRYPTION_KEY` também no `.env` do Studio.
3. Recrie no mesmo período de manutenção o Nginx Studio, `projects-api` e
   `postgres-meta-global`. API e Postgres-Meta devem receber a mesma
   `PG_META_CRYPTO_KEY`; Nginx e API devem receber a mesma chave de transporte.
4. Em uma instalação nova, não há dados legados a migrar. Em uma instalação
   existente, informe a chave antiga somente ao executar o utilitário manual:

   ```bash
   LEGACY_FERNET_SECRET=<chave-antiga> \
     python -m app.migrate_project_secrets --dry-run
   LEGACY_FERNET_SECRET=<chave-antiga> \
     python -m app.migrate_project_secrets --apply
   ```

5. Verifique que não há valores legados restantes:

   ```sql
   SELECT count(*) AS legacy_values
   FROM projects
   WHERE (anon_key IS NOT NULL AND anon_key NOT LIKE 'v2.%')
      OR (service_role IS NOT NULL AND service_role NOT LIKE 'v2.%')
      OR (config_token IS NOT NULL AND config_token NOT LIKE 'v2.%');
   ```

6. Faça smoke test de listagem de projetos, acesso ao config token, metadata do
   PG e login no Studio. O runtime não aceita mais valores legados após a
   migração.

O processo manual é retomável e não imprime segredos.

## Rotação da chave mestra

1. Gere uma nova chave Fernet e atualize:

   ```dotenv
   PROJECT_SECRETS_MASTER_KEY=<nova-chave>
   PROJECT_SECRETS_MASTER_KEY_ID=project-secrets-master-2026-10
   PROJECT_SECRETS_PREVIOUS_MASTER_KEYS=<chave-mestra-anterior>
   ```

2. Reinicie `projects-api` e execute:

   ```bash
   python -m app.migrate_project_secrets --apply
   ```

   Isso somente reenvelopa os DEKs; os valores de projeto não precisam ser
   recifrados. Após conferir os logs e o backup, remova a chave anterior de
   `PROJECT_SECRETS_PREVIOUS_MASTER_KEYS`.

## Rotação de DEKs por tenant

Para recifrar efetivamente todos os valores de cada projeto, use uma janela de
manutenção e execute primeiro com `--dry-run`, depois com `--apply`:

```bash
python -m app.migrate_project_secrets --rotate-deks --dry-run
python -m app.migrate_project_secrets --rotate-deks --apply
```

É possível limitar a um tenant para canário:

```bash
python -m app.migrate_project_secrets --project meu_tenant --rotate-deks --apply
```

## Rotação da chave de conexão do Postgres-Meta

Como os headers de conexão são efêmeros, não existe backlog criptográfico a
migrar. Faça uma troca coordenada de `PG_META_CRYPTO_KEY` no `projects-api` e
em `postgres-meta-global`, recrie ambos e valide uma chamada de metadata. A
troca precisa ser coordenada porque a imagem atual suporta uma única
`CRYPTO_KEY`; durante a diferença de chaves as chamadas de metadata falham de
forma fechada e caem no `meta_trap`.

## Rollback

Não descarte nenhuma chave antiga antes de um backup e de todos os smoke tests.
Se houver falha durante a rotação da chave mestra, restaure a chave anterior em
`PROJECT_SECRETS_PREVIOUS_MASTER_KEYS` e reinicie apenas a API. Para falha na
troca do Postgres-Meta, restaure a mesma `PG_META_CRYPTO_KEY` nos dois serviços
e recrie-os juntos.
