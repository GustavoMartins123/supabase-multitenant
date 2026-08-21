# Storage compartilhado, S3 e Storage Vectors

## Contrato upstream adotado

A implementacao usa sem patches o modo multi-tenant oficial do
`supabase/storage-api:v1.61.12`. A referencia foi conferida na tag
`v1.61.12` do repositorio upstream, nao apenas no HEAD.

O servico global usa:

- `MULTI_TENANT=true`;
- `DATABASE_MULTITENANT_URL` para o registry dedicado `_supabase_storage`;
- `SERVER_ADMIN_API_KEYS` e a Admin API na porta interna 5001;
- `AUTH_ENCRYPTION_KEY` para cifrar os campos sensiveis do registry;
- `REQUEST_X_FORWARDED_HOST_REGEXP` para extrair um UUID de tenant;
- `STORAGE_BACKEND=file` e `TenantLocation`;
- `VECTOR_BUCKET_PROVIDER=pgvector`;
- um unico `IMGPROXY_URL` interno.

O lifecycle é deliberadamente acoplado a esse contrato verificado na tag
`v1.61.12`: exige a imagem canônica, `STORAGE_BACKEND=file`,
`STORAGE_FILE_BACKEND_PATH=/var/lib/storage` e bucket interno `objects`. Ele
falha antes de mutar dados se configuração ou imagem efetivamente executada
divergirem; não tenta interpretar outro backend como layout file.

A Admin API nao e publicada no host nem conectada a `rede-supabase`. O
container Storage usa redes internas de controle e data plane; um Nginx global
sem credenciais, com alias `supabase-storage-global` na rede interna exclusiva
`supabase-storage-gateways`, encaminha exclusivamente para `storage:5000`.
Somente o Nginx confiavel de cada projeto entra nessa rede; Auth, PostgREST e os
demais containers de projeto permanecem fora dela. O lifecycle chama a Admin API por
`docker exec`, le a chave apenas dentro do container e nunca a inclui em argv,
arquivos de projeto, respostas publicas ou logs.

## Identidade e localizacao fisica

O Storage tenant ID e o `tenant_uuid` imutavel, persistido em `projects.id` e
materializado como `PROJECT_UUID`. O `project_ref` nao e usado como identidade
de objetos porque muda em rename.

Na versao adotada, `TenantLocation` forma a chave fisica como:

```text
<tenant_uuid>/<bucket_id>/<object_name>
```

Com `STORAGE_FILE_BACKEND_PATH=/var/lib/storage` e
`STORAGE_S3_BUCKET=objects`, o host guarda:

```text
servidor/volumes/storage/objects/<tenant_uuid>/<bucket_id>/<object_name>
```

Os helpers de lifecycle aceitam apenas UUID canonico em minusculas, resolvem a
raiz real, rejeitam symlinks e validam archives antes de extrair. Nao existe
tenant padrao e uma identidade ausente ou desconhecida falha.

O container do Storage roda com `cap_drop: ALL`, portanto sem
`CAP_DAC_OVERRIDE`: ele so grava no namespace se for dono dos diretorios.
`STORAGE_RUN_AS_USER` (formato `UID:GID`) declara essa identidade no compose e
precisa casar com o dono de `servidor/volumes/storage` no host. Toda
materializacao de namespace — criacao vazia, clone e restore — passa por
`storage_enforce_namespace_ownership`, que ajusta o dono ou falha antes de
entregar um tenant onde o Storage nao consegue escrever.

Para operações de projeto existente, o par `project_ref`/`tenant_uuid` também é
comparado com `projects.tenant_uuid` no control plane. Um `.env` divergente não
consegue selecionar o namespace de outro projeto.

## Resolucao HTTP do tenant

Cada Nginx de projeto conhece o UUID renderizado no seu proprio arquivo e
sempre sobrescreve o valor recebido do cliente:

```nginx
proxy_set_header X-Forwarded-Host "<tenant_uuid>.storage.internal";
```

O Storage aceita somente hosts que casam integralmente com o regexp de UUID.
O proxy do data plane tambem rejeita com HTTP 421 qualquer request de dados sem
esse host canonico ou com valor invalido; apenas `/status`, usado pelo
healthcheck de infraestrutura, nao exige tenant. Assim, `X-Forwarded-Host`,
`Host` ou qualquer suposto header de tenant enviado pelo cliente nao permite
selecionar outro projeto.

O fluxo de chave opaca permanece:

```text
sb_publishable / sb_secret
  -> Nginx do projeto
  -> key-authorizer vinculado ao project_ref
  -> JWT anon/service_role interno daquele projeto
  -> Storage global com X-Forwarded-Host sobrescrito
```

O JWT secret, anon key e service key ficam cifrados no registry de cada tenant.
Nao ha JWT global usado como substituto. Uma chave opaca de A nao e resolvida
pelo gateway de B e um JWT de A nao valida contra o segredo de B.

## Database e migrations por tenant

O registro do tenant contem duas URLs:

- direta: `supabase_storage_admin` em `_supabase_<project_ref>` pelo hostname
  `db` da rede de controle;
- pool: `supabase_storage_admin.<project_ref>` pelo hostname `supavisor` da
  mesma rede.

Create, duplicate, rename e restore concedem acesso a
`supabase_storage_admin`, fixam `search_path=storage,public` e validam pgvector.
O lifecycle registra ou atualiza essas URLs pela Admin API. Rename altera apenas
as URLs; o tenant UUID e o namespace de objetos permanecem iguais.

As migrations sao executadas pelo endpoint oficial
`POST /tenants/<uuid>/migrations`. O lifecycle espera
`migrationsStatus=COMPLETED` e `isLatest=true`. O Storage upstream serializa a
migration por tenant; projetos diferentes nao precisam de um lock global.

## Credenciais S3/SigV4

Cada tenant recebe pela Admin API oficial uma credencial propria:

```text
POST /s3/<tenant_uuid>/credentials
```

O access key e o secret retornados sao gravados apenas no `.env` 0600 do
projeto e nos Vault secrets dos wrappers. No registry, o secret e cifrado com
`AUTH_ENCRYPTION_KEY`.

Na verificacao de uma assinatura, o upstream chama
`getS3CredentialsByAccessKey(tenantId, accessKey)`. Portanto o mesmo access key
so e pesquisado dentro do tenant ja resolvido pelo host. Credencial A com host
de B falha; nao existe busca global nem credencial substituta.

Para `/storage/v1/s3`, o cliente assina o host e path publicos. O Nginx:

- preserva `Host`, que faz parte da assinatura canonica;
- reescreve a rota interna para `/s3`;
- informa o prefixo publico confiavel em `X-Forwarded-Prefix`;
- sobrescreve `X-Forwarded-Host` exclusivamente para resolver o tenant.

## Storage Vectors

Storage Vectors usa o mesmo par SigV4 do S3 Protocol, mas o service da
assinatura e `s3vectors`. O provider `pgvector` grava metadata e tabelas no
database do proprio projeto.

O FDW de cada projeto aponta para seu Nginx:

```text
http://supabase-nginx-<project_ref>:8080/vector
```

O wrapper assina o `Host` desse endpoint. O Nginx preserva esse host canonico e
injeta o UUID imutavel em `X-Forwarded-Host`. Desse modo o endpoint pode mudar
no rename sem alterar a identidade do tenant. O lifecycle reconcilia os
`endpoint_url` depois de duplicate, rename e restore.

O nome fisico de uma tabela pgvector inclui um hash calculado pelo upstream a
partir de bucket, tenant e index. Um clone `with-data` renomeia essas tabelas em
transacao para hashes do novo UUID. O clone tambem remove FDWs e Vault secrets
copiados, cria credenciais novas e recria wrappers somente para seus proprios
Vector Buckets. `schema-only` cria namespace e metadata vazios.

## Create e validacao

Create executa, na ordem relevante:

1. cria e valida o database;
2. registra Realtime e Supavisor;
3. cria o namespace fisico exclusivo;
4. registra o tenant pela Admin API;
5. cria a credencial SigV4;
6. renderiza apenas Auth, PostgREST, Nginx e Postgres-Meta do projeto;
7. sobe esses containers;
8. valida migrations, health do tenant, consulta JWT ao database, S3 SigV4,
   `ListVectorBuckets` e o caminho real pelo Nginx com um header hostil.

Qualquer falha encerra o job e aciona rollback compensatorio. O Storage global
nao e reiniciado e nenhum container local e iniciado.

## Settings

`FILE_SIZE_LIMIT`, transformacao de imagem, S3 Protocol, Vector Buckets e os
limites de Vector sao campos do tenant. `apply_storage_settings.sh` envia um
`PATCH /tenants/<uuid>` e valida o tenant real. Apenas o Nginx do projeto e
recriado quando seu limite de body precisa mudar; Storage e imgproxy globais nao
sao reiniciados por settings de projeto.

## Backup, restore e delete

Backup coloca somente o tenant Storage solicitado em manutenção fail-closed,
confirma pelo data plane que ele não aceita novas operações, para os containers
do projeto e arquiva somente o conteúdo do seu namespace. A manutenção usa uma
`databasePoolUrl` deliberadamente inalcançável; não usa `null`, porque o Storage
oficial passaria a consultar `databaseUrl`. O manifest formato 2 vincula
`project_uuid`, `storage_tenant_id` e `storage_layout=tenant-namespace`.

Restore rejeita manifests de outro UUID e archives com path absoluto,
`..`, symlink ou tipo especial. O namespace atual e movido para staging
transacional, somente o namespace solicitado e extraido, migrations sao
reexecutadas e wrappers sao reconciliados. Outros tenants permanecem intactos.

Delete revoga todas as credenciais pela Admin API, remove o tenant do registry
e somente depois remove o diretorio validado daquele UUID. O database do projeto
so e removido depois dessa etapa concluir.

## Observabilidade

Os logs JSON do Storage global preservam `tenantId`, request ID, metodo, path e
tipo de operacao quando fornecidos pelo upstream. O proxy do data plane registra
somente o path sem query string, o metodo, o status, o request ID e o host de
tenant ja sobrescrito pelo Nginx confiavel. O Vector extrai desse host apenas o
UUID canonico e envia ambos os fluxos ao sink de Storage, sem registrar chaves,
tokens, senhas ou credenciais SigV4.

## Testes

- `test_shared_storage_architecture_contract.py` protege topologia, roteamento,
  lifecycle, migration e ausencia de caminhos antigos sem precisar de Docker;
- `test_shared_storage_tenant_integration.py` e opt-in e executa a matriz ativa
  de dois tenants: objetos privados, mesmos nomes de bucket, opaque keys,
  SigV4 cruzado, Vectors, limites, imagens, clones, rename, backup/restore,
  delete, tenant ausente, header hostil e indisponibilidade global.

Nao ha bootstrap alternativo, tenant default ou fallback para Storage local.
