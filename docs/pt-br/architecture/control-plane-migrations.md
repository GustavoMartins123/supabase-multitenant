# Migrations do control plane

O schema do database `postgres` — usuários, projetos, jobs, intenções do host-agent, chaves opacas, colaboração e restore points — pertence a arquivos `.sql` versionados em `servidor/api-internal/app/migrations`.

Iniciar ou reiniciar a Projects API não altera schema. O processo que atende requisições apenas confere a versão aplicada e falha fechado quando o banco está atrás da imagem.

## Fronteiras

| Camada | Responsável | Quando roda |
| --- | --- | --- |
| Objetos de cluster: schemas internos, `_supabase_storage`, `_supabase_template`, `meta_trap`, `meta_guest`, pgvector | `servidor/volumes/db/create_template.sh` | uma única vez, no initdb do Postgres |
| Tabelas, índices, constraints, triggers e seeds do control plane | `app/migrations/NNNN_*.sql` | a cada deploy, pelo comando privilegiado |
| Identidade de banco `key_authorizer` | `app/control_plane_roles.py`, chamado pelo mesmo comando | a cada deploy |
| Verificação de compatibilidade | `verify_control_plane_schema()` no startup da API | a cada boot, sem escrever |

O bootstrap histórico não cria mais nenhuma tabela do control plane. Uma instalação limpa fica idêntica a uma instalação existente migrada.

## Ledger

`control_plane_schema_migrations` registra, por versão: nome, checksum SHA-256 do arquivo, timestamp, `current_user` e duração.

O checksum é a trava contra edição retroativa. Alterar um arquivo já aplicado faz `apply` e o boot recusarem explicitamente, porque o banco deixaria de corresponder ao que o repositório descreve.

## Comandos

O comando roda dentro da imagem da Projects API, com o DSN administrativo:

```bash
docker compose -f docker-compose-api.yml -f docker-compose.single-node.yml \
  --env-file .env run --rm control-plane-migrations
```

Os três modos:

```bash
python -m app.schema_migrations apply    # aplica pendências e provisiona identidades
python -m app.schema_migrations status   # lista o ledger contra os arquivos da imagem
python -m app.schema_migrations verify   # confere sem alterar nada; sai 3 se houver pendência
```

`apply` toma um advisory lock, de modo que dois migradores simultâneos não se atropelam, e usa `lock_timeout` de 30 segundos: se o processo anterior ainda segurar um lock de tabela, o deploy falha com diagnóstico em vez de travar indefinidamente.

Cada versão roda na sua própria transação, junto com o registro no ledger. Uma versão que falha é revertida inteira e nada é marcado como aplicado.

## Ordem no deploy

O serviço efêmero `control-plane-migrations` faz esse passo dentro do próprio Compose:

```text
supabase-db saudável
        │
        ▼
control-plane-migrations  (DSN administrativo, aplica NNNN pendentes, provisiona key_authorizer)
        │ service_completed_successfully
        ├────────────────► key-authorizer
        └────────────────► projects-api  (verifica a versão e serve tráfego)
```

`start.sh` espera o banco ficar saudável antes de subir esse Compose. `key-authorizer` e `projects-api` só iniciam depois que o migrador termina com sucesso; se ele falhar, nenhum dos dois sobe.

O host-agent continua esperando as tabelas existirem (`--check-schema`), agora publicadas pelo migrador e não mais pelo boot da API.

## Adicionar uma migration

1. crie `NNNN_nome_curto.sql` com o próximo número de quatro dígitos, sem buracos na sequência;
2. escreva DDL idempotente (`IF NOT EXISTS`, `DO $$` com checagem em `pg_constraint`/`pg_trigger`), porque a mesma versão precisa atravessar instalações em estados diferentes;
3. faça o backfill de dados **antes** de apertar `NOT NULL` ou adicionar `CHECK`, e lembre que `NULL IN (...)` devolve `NULL`;
4. conceda na própria migration os privilégios das tabelas que ela cria;
5. exercite os dois caminhos com `tests/integration/test_control_plane_migrations_postgres.py`.

Nunca edite um arquivo já aplicado em produção. Renomear ou reordenar versões também quebra o ledger.

## Rollback e forward-fix

Não existe `downgrade`. Reverter schema com dados vivos é o caminho que perde informação em silêncio, e o ledger não descreve o inverso de uma migration.

O procedimento é sempre avançar:

1. **Falha durante o `apply`**: a versão foi revertida pela transação e não entrou no ledger. Corrija o arquivo, que ainda não foi aplicado em lugar nenhum, e rode `apply` de novo.
2. **Versão aplicada que se revelou errada**: escreva uma nova versão que corrija o estado, com o mesmo cuidado de idempotência. O arquivo original permanece intacto no histórico.
3. **Imagem antiga contra banco novo** — um rollback de release: o boot registra `banco a frente desta imagem` e continua servindo, porque o schema é compatível para frente. Se a imagem antiga precisar de uma coluna que a versão nova removeu, o caminho é avançar a imagem, não reverter o banco.
4. **Imagem nova contra banco antigo**: o boot recusa com a lista de versões faltando. Rode `apply` antes de subir a API.

Restaurar backup do database `postgres` continua sendo a única forma de voltar o schema no tempo, e volta os dados junto.

## Instalações anteriores às migrations

A primeira execução do `apply` numa instalação existente aplica as três versões atuais sobre o schema que o boot já havia criado. As criações são no-op e restam apenas as convergências que faltavam, todas em `0001`:

- `jobs.action` e `jobs.updated_at` passam a `NOT NULL`. Jobs anteriores à coluna `action` não registraram a operação e recebem o marcador `unknown`, que não pertence a nenhuma ação executável nem à lista de ações idempotentes;
- `jobs` recebe os `CHECK` de `progress`, `total_steps` e `attempt`, que só existiam em instalações criadas do zero.

Antes disso, o cálculo de `is_idempotent` no boot quebrava numa instalação com jobs anteriores à coluna `action`, porque `NULL IN (...)` viola o `NOT NULL` da coluna. O backfill passou a vir antes do recálculo.
