# Migração transitória para Storage compartilhado

Este procedimento existe somente para converter instalações criadas com
Storage API e imgproxy por projeto. Ele não é carregado pelo runtime e não cria
modo legacy, feature flag ou rota alternativa.

Depois de concluída, a instalação opera exclusivamente com
`supabase-storage-global` e `supabase-imgproxy-global`. O `start.sh` rejeita
explicitamente qualquer compose de projeto que ainda declare os containers
antigos.

## Pré-condições

Execute no host Linux da instalação, a partir do checkout que contém a nova
arquitetura. São necessários:

- branch e configuração revisadas;
- backup externo do host e do PostgreSQL;
- Docker/Compose, Bash, Python 3, `jq`, `openssl`, `tar`, `gzip`, `sed`, `grep`,
  `find` e `systemctl`;
- `supabase-db` em execução;
- Projects API e host-agent instalados no modelo atual;
- `STORAGE_IMAGE=supabase/storage-api:v1.61.12`, proxy
  `nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim` e backend file no layout
  canônico (`/var/lib/storage`, bucket interno `objects`); valores diferentes
  são recusados antes da conversão;
- nenhum job ou comando de lifecycle em `queued` ou `running`;
- espaço para uma segunda cópia temporária dos objetos e backups.

Não inicie create, duplicate, rename, delete, backup, restore, settings ou
rotação durante a janela.

## Execução

```bash
cd /caminho/supabase-multitenant
bash servidor/generateProject/migrate_shared_storage.sh
```

A ferramenta:

1. verifica que não há lifecycle ativo;
2. registra pelos labels do Compose se a Projects API usa `single-node` ou
   `split-node`, e então para Projects API e host-agent, impedindo novas intenções;
3. completa somente as chaves globais canônicas em `servidor/.env`;
4. cria `.storage.env` 0600 com chaves aleatórias se ainda não existir;
5. cria `_supabase_storage`, reconcilia as redes internas de DB/Supavisor e
   inicia Storage, imgproxy e o proxy global restrito à data plane;
6. descobre os diretórios em `servidor/projects/`;
7. confere `PROJECT_UUID` contra `projects.tenant_uuid`;
8. para a stack do projeto;
9. copia `storage/stub/stub` para
   `volumes/storage/objects/<PROJECT_UUID>` sem remover a origem;
10. reidentifica tabelas físicas pgvector de `stub` para o UUID;
11. registra o tenant, executa migrations e cria credencial SigV4 nova pela
    Admin API oficial;
12. renderiza compose/env/Nginx somente na arquitetura compartilhada;
13. inicia Auth, PostgREST, Nginx e Postgres-Meta;
14. valida health do tenant, database, JWT, S3, Vectors e o Nginx com tentativa
    de sobrescrever `X-Forwarded-Host`;
15. reconcilia wrappers Vector;
16. arquiva o diretório antigo no relatório interno e só então remove a cópia
    do diretório do projeto;
17. converte backups formato 1 para archives de namespace formato 2;
18. depois de todos os projetos e backups, reconstrói a Projects API com o
    mesmo override de topologia detectado antes da parada e religa o host-agent.

Cada projeto tem um arquivo de estado. A cópia de origem não é apagada antes de
o tenant novo passar por validação completa.

## Relatório e retomada

Cada execução cria:

```text
servidor/storage-migration-reports/<timestamp-pid>/
```

O diretório contém `summary.tsv`, estados por projeto, configurações anteriores,
archives do Storage antigo e backups substituídos. Ele é interno, ignorado pelo
Git e pode conter dados sensíveis; nunca deve ser publicado.

Se houver interrupção, use exatamente o diretório informado no erro:

```bash
bash servidor/generateProject/migrate_shared_storage.sh \
  --resume servidor/storage-migration-reports/<timestamp-pid>
```

O `--resume` detecta a etapa registrada. Um projeto incompleto é revertido para
seu estado anterior dentro da ferramenta antes de ser tentado novamente. Estado
ambíguo — por exemplo, dois namespaces físicos ou tenant existente sem estado —
é bloqueado para inspeção; nunca é escolhido um lado automaticamente.

O marcador `projects-api.compose-override` aceita somente os overrides
`docker-compose.single-node.yml` e `docker-compose.split-node.yml`. Marcador
ausente, adulterado ou topologia ambígua interrompe a retomada; a ferramenta não
escolhe um perfil padrão.

Se qualquer projeto ficar parcial, Projects API e host-agent permanecem parados.
Isso é intencional: código novo e stacks antigas não podem operar ao mesmo tempo.
Corrija a causa e retome o mesmo relatório.

## Rollback operacional da migração

Antes do marker global `COMPLETE`, o rollback suportado é por projeto e faz
parte da própria ferramenta: remove o tenant novo, devolve os hashes Vector para
`stub`, restaura compose/env e repõe o diretório antigo a partir do archive.

Se for necessário abandonar toda a mudança depois de projetos já concluídos,
mantenha o runtime parado e restaure o snapshot externo integral do host,
PostgreSQL e checkout anterior. Não tente iniciar a aplicação nova sobre esse
estado e não copie arquivos manualmente entre namespaces. Depois que o marker
`COMPLETE` existe, não há caminho de runtime para a arquitetura antiga; uma
reversão é exclusivamente recuperação operacional do snapshot completo.

## Verificações depois da conclusão

Confirme:

```bash
docker ps --format '{{.Names}}'
```

Para N projetos devem existir N containers Auth, PostgREST e Nginx, mas apenas:

```text
supabase-storage-global
supabase-imgproxy-global
```

Também execute os smoke tests ativos descritos em
[`tests/smoke/README.md`](../../../tests/smoke/README.md), confira `summary.tsv` e
preserve o relatório até o encerramento formal da janela de mudança.
