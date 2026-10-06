# Upgrades e rollback

Como levar uma instalação em produção de uma versão da plataforma para a
próxima. A versão canônica é o `VERSION` na raiz do repositório; contra o que
cada versão é construída está em
[`COMPATIBILITY_MATRIX.md`](../../../COMPATIBILITY_MATRIX.md).

O projeto é alpha e tem um mantenedor. O procedimento abaixo assume um operador
na frente do host, não um pipeline automatizado.

## O que um upgrade toca

Upgrades não são uniformes: três camadas se movem de forma independente e
falham de formas diferentes.

| Camada | O que é | Raio de alcance | Como é aplicada |
| --- | --- | --- | --- |
| Control plane | Projects API, host-agent, schema do control plane, gateway do Studio | todos os projetos de uma vez | `bash setup.sh` + `bash start.sh` no host |
| Data plane global | Postgres, Supavisor, Realtime, Storage, imgproxy, Edge Runtime, Postgres-Meta, Analytics, Traefik, Vector | todos os projetos de uma vez | `docker compose ... up -d` via `start.sh` |
| Data plane por projeto | Nginx, Auth e PostgREST daquele projeto | um projeto | `POST /api/projects/{nome}/recreate-services` |

Só a terceira camada pode ser encenada. **Qualquer coisa nas duas primeiras é
tudo-ou-nada num host único** — a estratégia de canário abaixo compra um
ensaio, não um raio de alcance parcial. Não descreva um upgrade de control
plane para os usuários como "canariado".

## Numeração de versão

- `VERSION` é `major.minor.patch[-prerelease]`, sem build metadata.
- Enquanto o projeto for `-alpha`, bumps de minor podem quebrar contratos.
  Diga isso no `CHANGELOG.md` em vez de fingir que as garantias de semver valem.
- O app Flutter em `studio/seletor_de_projetos` carrega `+N` de build metadata
  sobre a mesma versão core. Nada mais pode.
- Uma release candidate é `X.Y.Z-rc.N`, promovida a `X.Y.Z` só depois que o
  rollout abaixo termina numa instalação real.

Cada ponto derivado é travado por `tools/check-version-parity.py`, que roda no
CI. Para mudar a versão:

```bash
# 1. edite VERSION e servidor/api-internal/app/version.py a mão
python tools/export_openapi.py          # regenera docs/api/openapi.json
python tools/check-version-parity.py --fix
python tools/check-version-parity.py    # precisa sair 0
```

## Antes da tag: release candidate

Não crie a tag antes de tudo isto passar no commit da RC.

1. `python -m pytest tests/smoke -q` — verde.
2. CI verde nos dois workflows, incluindo `migrations-live` (Postgres real) e o
   job `flutter`.
3. `python tools/check-version-parity.py` — 0 erros.
4. `python tools/check-env-contract.py --compose` — 0 erros.
5. `COMPATIBILITY_MATRIX.md` atualizado se algum pin upstream mudou.
6. `CHANGELOG.md` com a seção da versão, quebras de contrato primeiro.
7. Uma **instalação limpa** a partir da RC funciona: host zerado, `bash
   setup.sh`, criar um projeto, entrar pelo Studio, escrever e ler uma linha
   pelo PostgREST. Instalação limpa quebrada é bloqueio de release mesmo que o
   upgrade funcione — usuário novo só vê esse caminho.
8. Um **upgrade** a partir da versão anterior funciona, usando o rollout abaixo
   numa instalação de staging.

## Rollout

### Etapa 0 — restore point e backup

Não é opcional. O schema do control plane é forward-fix apenas; não existe
caminho de `downgrade` (ver
[migrations do control plane](../architecture/control-plane-migrations.md)).
Migration ruim se recupera de backup, não se reverte.

- Tire um restore point de todo projeto que você vai tocar, ou no mínimo um
  `backup_project` completo do canário.
- Faça dump do banco do control plane à parte — restore points cobrem dados de
  projeto, não o control plane.
- Anote os digests das imagens atuais (`docker compose images`) e o
  `git rev-parse HEAD` atual. Esse é o alvo do rollback.

### Etapa 1 — canário (1 projeto)

Escolha o projeto menos crítico. De preferência um seu.

1. Faça o upgrade do control plane e do data plane global no host
   (`git checkout <tag>`, `bash setup.sh`, `bash start.sh`).
2. Recrie os serviços do canário:
   `POST /api/projects/{canario}/recreate-services` com os serviços que
   realmente mudaram — não todos.
3. Rode o portão de saúde abaixo.
4. Fique nele por pelo menos um ciclo completo de backup antes de continuar. A
   maioria das falhas nesse stack não é imediata: slot de replicação, renovação
   de certificado e envio de log falham horas depois.

### Etapa 2 — percentual (25%)

Recrie os serviços de um quarto dos projetos restantes, escolhidos para cobrir
os formatos que você de fato roda (um projeto com Storage Vectors, um com Edge
Functions, um com perfil de capacidade custom). Portão de saúde depois de cada
lote.

### Etapa 3 — todos

Projetos restantes. Portão de saúde depois do lote, e de novo no dia seguinte.

## Portão de saúde

Rode entre cada etapa. **Ainda não existe endpoint agregado de saúde por
projeto** — isso é a Fase 3 do plano. Até existir, o portão são as checagens
manuais abaixo; não pule nenhuma assumindo que container verde significa tenant
saudável.

| Checagem | Como | Condição de passagem |
| --- | --- | --- |
| Liveness da API | `GET /healthz` na Projects API | `{"ok": true}` |
| Estado dos containers | `project_container_state` do projeto, ou `GET /api/projects/{nome}` no Studio | todo container `running`, sem loop de restart |
| Migrations | ledger de migrations do control plane | versão aplicada bate com a release, sem linha parcial |
| Auth | entrar no Studio pelo Authelia | sessão emitida, sem `needs_admin=true` |
| PostgREST | leitura autenticada pela URL pública do projeto | 200, linhas esperadas |
| Storage | upload e signed-download de um objeto no bucket do projeto | ambos passam, objeto no tenant certo |
| Realtime | assinar um canal e escrever uma linha | evento entregue |
| Supavisor | conectar pela porta do pooler | conexão aceita |
| Chaves | `GET /api/projects/{nome}/keys` | slots presentes, nenhuma chave vencida |
| Logs | Logflare filtrado pelo projeto | eventos chegando depois do restart |

Qualquer checagem vermelha para o rollout naquela etapa. Não avance para o
próximo percentual para "ver se é só aquele projeto".

## Rollback

O rollback é diferente por camada. Decida qual camada quebrou antes de agir.

**Data plane por projeto** — o mais barato. Volte para a tag anterior e rode
`recreate-services` de novo para aquele projeto. Os dados nunca foram tocados.

**Data plane global** — volte para a tag anterior e rode `bash start.sh` de
novo. As imagens estão pinadas na matriz, então as versões anteriores ainda são
puxáveis. Cuidado com estado escrito no formato novo: tenants do Realtime e
linhas de tenant do Storage são compartilhados, e a versão nova pode tê-los
reescrito.

**Control plane** — o caro. Se a release incluiu migration:

1. Pare a Projects API e o host-agent para nada escrever.
2. Restaure o banco do control plane a partir do dump da Etapa 0.
3. Volte para a tag anterior e rode `bash setup.sh` + `bash start.sh`.
4. Restaure restore points só dos projetos cujos dados de fato divergiram —
   restaurar um projeto sem necessidade perde as escritas feitas desde então.

Se a release não incluiu migration, voltar a tag e reiniciar basta; pule a
restauração do banco.

**Segredo rotacionado não volta com nada disso.** Se o upgrade rotacionou
chaves ou segredos de conexão, os valores antigos se foram. Role para a frente
com uma nova rotação em vez de tentar restaurar os anteriores.

## Depois do rollout

1. Crie a tag da release e faça push dela.
2. Mova a seção do `CHANGELOG.md` de "Não lançado" para a versão.
3. Atualize o `COMPATIBILITY_MATRIX.md` se o rollout revelou um pin que teve de
   se mover.
4. Anote o que o portão de saúde pegou. O portão só vale pelas falhas que ele
   já viu.
