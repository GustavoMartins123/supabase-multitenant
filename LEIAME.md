# Documentação do supabase-multitenant

[Read this setup in English 🇺🇸](./README.md)

## Visão geral

A stack oficial de auto-hospedagem do Supabase foi projetada para um único projeto. Este repositório estende essa arquitetura para gerenciar múltiplos projetos isolados na mesma infraestrutura.

Cada projeto recebe seu próprio database PostgreSQL, JWT secret, tenant do Realtime, tenant do Storage, tenant do Supavisor e serviços dedicados de Nginx/Auth/PostgREST. Serviços que já suportam ou foram adaptados para multi-tenancy — incluindo Storage, ImgProxy, Realtime, Supavisor, Edge Functions e Postgres Meta — são compartilhados. Um control plane em FastAPI gerencia o ciclo de vida dos projetos, enquanto um gateway dinâmico OpenResty/Lua permite que **uma única instância do Supabase Studio** administre todos eles.

Cada projeto possui múltiplos slots de API keys opacas `publishable`/`secret`. A expiração é opcional por chave; slots com expiração podem rotacionar automaticamente antes do vencimento, enquanto os JWTs internos anon/service role permanecem somente no servidor. Um administrador pode desativar a automação no projeto ou no slot, e falhas ficam bloqueadas e visíveis até uma retomada explícita.

> Este é um projeto não oficial e ainda está em desenvolvimento ativo.

---

## Sumário

- [Visão geral](#visão-geral)
- [Propósito](#propósito)
- [Arquitetura](#arquitetura)
- [Pré-requisitos](#pré-requisitos)
- [Como utilizar](#como-utilizar)
  - [1. Clonar o repositório](#1-clonar-o-repositório)
  - [2. Executar o setup](#2-executar-o-setup)
  - [3. Iniciar a plataforma](#3-iniciar-a-plataforma)
  - [4. Verificação](#4-verificação)
- [Documentação](#documentação)
- [Manutenção](#manutenção)

## Propósito

Simplificar a criação e a gestão de múltiplos projetos Supabase isolados em uma infraestrutura controlada por você.

---

## Arquitetura

```mermaid
flowchart LR
    User[Usuário] --> StudioGateway[Studio Gateway\nNginx/OpenResty :9091]
    StudioGateway --> Authelia[Authelia]
    StudioGateway --> Flutter[Seletor Flutter]
    StudioGateway --> Studio[Supabase Studio]

    StudioGateway --> Traefik[Traefik]
    Traefik --> ProjectsAPI[Projects API\nFastAPI]
    Traefik --> TenantGateway[Nginx do projeto]

    ProjectsAPI --> PostgreSQL[(PostgreSQL)]
    ProjectsAPI -->|intenções assinadas de lifecycle| PostgreSQL
    HostAgent[host-agent\nsystemd no host] -->|lease/resultado| PostgreSQL
    HostAgent --> Docker[Docker daemon]

    TenantGateway --> KeyAuthorizer[key-authorizer]
    KeyAuthorizer --> PostgreSQL
    TenantGateway --> Auth[GoTrue]
    TenantGateway --> Rest[PostgREST]
    TenantGateway --> StorageDataPlane[Data plane compartilhado do Storage]
    StorageDataPlane --> Storage[Storage global multi-tenant]
    Storage --> ImgProxy[ImgProxy global]
    TenantGateway --> Functions[Edge Functions global]
    TenantGateway --> Realtime[Realtime global]

    Auth --> Supavisor[Supavisor global]
    Rest --> Supavisor
    Storage --> Supavisor
    Supavisor --> PostgreSQL

    ProjectsAPI --> PostgresMeta[Postgres Meta global]
    PostgresMeta --> PostgreSQL
```

A Projects API **não acessa o Docker socket**. As operações físicas de lifecycle são gravadas no PostgreSQL como intenções assinadas por HMAC. Um serviço systemd no host, o `host-agent`, faz o lease, revalida essas intenções e executa apenas um conjunto fechado de comandos Docker/lifecycle.

A plataforma suporta duas topologias:

- **Uma máquina:** Studio, Traefik, API, PostgreSQL, host-agent e serviços dos projetos rodam no mesmo host. O host-agent continua fora dos containers.
- **Duas máquinas:** Studio, Authelia e OpenResty rodam em uma máquina administrativa local, enquanto Traefik, API, host-agent e serviços dos projetos rodam no servidor principal.

As aplicações acessam as rotas dos projetos pelo Traefik. O gateway do Studio é uma interface administrativa e não precisa fazer parte do caminho público dos dados.

### Serviços compartilhados

- PostgreSQL;
- Supavisor;
- Realtime modificado;
- Storage API no modo multi-tenant oficial;
- ImgProxy;
- proxy restrito do data plane do Storage;
- Edge Functions;
- Postgres Meta;
- key-authorizer;
- Projects API;
- Traefik;
- Supabase Analytics/Logflare e Vector.

O `host-agent` também é um componente global da plataforma, mas roda como serviço systemd no servidor principal em vez de container.

### Serviços criados por projeto

- Nginx;
- GoTrue;
- PostgREST;
- database `_supabase_<project_ref>`;
- diretório de configuração do projeto.

Storage e ImgProxy não são mais criados por projeto. Os objetos do Storage são namespaced pelo UUID imutável do tenant, e o Nginx de cada projeto injeta a identidade confiável do tenant antes de o tráfego chegar ao data plane compartilhado do Storage.

Para os detalhes de implementação, consulte a [documentação da arquitetura](docs/pt-br/00-arquitetura.md).

---

## Pré-requisitos

| Item | Descrição |
| --- | --- |
| Linux | Sistema usado pelos scripts de setup. |
| Docker e Docker Compose | Instalados e em execução. |
| Python | Python 3.10 ou mais recente, incluindo o módulo `venv`. Ele é necessário para o `setup.sh`, configuração do Studio/Authelia, scripts de lifecycle dos projetos e host-agent. |
| Usuário | Permissão para executar comandos Docker. |
| Utilitários | `openssl`, `curl`, `jq`, `sed` e ferramentas padrão de shell. |

No Ubuntu ou Debian, instale o Python necessário no host com:

```bash
sudo apt update
sudo apt install -y python3 python3-venv
```

Confirme a versão mínima antes de executar o setup:

```bash
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 ou mais recente é obrigatório"'
python3 -m venv --help >/dev/null
```

Na topologia com duas máquinas, o Python precisa estar instalado tanto no servidor principal quanto na máquina administrativa do Studio. O servidor usa Python para o host-agent e o lifecycle dos projetos; a máquina do Studio usa Python para renderizar a configuração runtime e os certificados do Authelia.

---

## Como utilizar

### 1. Clonar o repositório

```bash
git clone git@github.com:GustavoMartins123/supabase-multitenant.git
cd supabase-multitenant
```

### 2. Executar o setup

```bash
bash setup.sh single-node
```

Para instalar tudo em uma única máquina, `single-node` usa o IP local detectado para o servidor principal e o Studio, sem perguntar a topologia.

Para duas máquinas, use `bash setup.sh split-node <ip-ou-dominio-do-servidor>`. Executar `bash setup.sh` sem perfil mantém o fluxo interativo anterior.

O IP ou domínio solicitado pelo script representa o **servidor principal**, onde rodam Traefik, Projects API e os serviços dos projetos.

Depois do setup, instale o **host-agent** no servidor principal. Ele é o serviço systemd que executa o lifecycle físico dos projetos (Docker e scripts) — a Projects API apenas grava intenções assinadas no banco e não toca mais no Docker:

```bash
sudo bash servidor/host-agent/install.sh
```

O script também detecta o IP da máquina atual, usado pelo Studio local, Authelia, certificado autoassinado e integrações internas.

No modo interativo:

- Informe o IP da máquina local para preparar uma instalação em uma máquina.
- Informe outro IP ou domínio para preparar a topologia com duas máquinas.

O setup gera os arquivos de ambiente do servidor e do Studio, incluindo as credenciais separadas do Analytics em `servidor/.analytics.env` e `studio/.analytics.env`. Os segredos de infraestrutura do Storage ficam separados em `servidor/.storage.env`.

### 3. Iniciar a plataforma

#### Início automatizado — recomendado

```bash
bash start.sh single-node
```

`single-node` é o perfil explícito padrão. Para duas máquinas, execute `bash start.sh split-node-server` no servidor principal e `bash start.sh split-node-studio` na máquina administrativa do Studio.

O script inicia os serviços compartilhados e a Projects API, espera PostgreSQL e Supavisor, inicia Traefik e os projetos existentes e, por último, inicia o Studio.

> Não execute o `start.sh` com `sudo`. Rodar a stack inteira como root altera variáveis de ambiente, contexto do Docker, ownership dos arquivos e permissões dos volumes. Se o Docker exigir privilégio, adicione seu usuário ao grupo `docker` e entre novamente na sessão:
>
> ```bash
> sudo usermod -aG docker "$USER"
> ```

#### Início manual — controle ou depuração

Inicie os serviços compartilhados e a Projects API:

```bash
cd servidor

docker compose -f docker-compose.yml --env-file .env up --build -d
docker compose -f docker-compose-api.yml -f docker-compose.single-node.yml --env-file .env up --build -d
```

O segundo comando executa antes o serviço efêmero `control-plane-migrations`, que aplica as migrations versionadas do schema e provisiona as identidades restritas de banco; `key-authorizer` e `projects-api` só sobem depois que ele termina com sucesso. Veja [Migrations do control plane](docs/architecture/control-plane-migrations.md).

Inicie o Traefik:

```bash
docker compose -f traefik/docker-compose.yml --env-file .env up -d
```

Inicie os projetos existentes:

```bash
for project_dir in projects/*/; do
  project_name=$(basename "$project_dir")

  [ -f "$project_dir/docker-compose.yml" ] || continue

  docker compose -p "$project_name" \
    -f "$project_dir/docker-compose.yml" \
    --env-file .env \
    --env-file "$project_dir/.env" \
    up --build -d
done
```

Inicie o Studio:

```bash
cd ../studio
docker compose up --build -d
```

### 4. Verificação

Confira se os containers estão rodando:

```bash
docker ps
```

Com vários projetos, deve existir um conjunto Nginx/Auth/PostgREST por projeto, mas apenas um `supabase-storage-global` e um `supabase-imgproxy-global`.

Acesse o Studio:

```text
https://<seu_ip_local>:9091
```

No primeiro acesso, crie o administrador inicial pelo navegador. Depois do bootstrap, usuários não autenticados são redirecionados para o Authelia.

Detalhes importantes do Studio:

- cada aba do navegador mantém seu projeto pela URL (`/project/<ref>`);
- `9091` é o único endpoint público do Studio e do Authelia;
- requisições HTTP simples em `:9091` são redirecionadas para HTTPS na mesma porta;
- integrações entre servidores que acessam o gateway do Studio também devem usar a porta `9091`.

---

## Documentação

O README é focado em entender e iniciar a plataforma rapidamente. A documentação detalhada está em [`docs/README.md`](docs/README.md). Quando detalhes de implementação evoluírem, os documentos de arquitetura são a fonte canônica.

Referências principais:

- [Visão geral da arquitetura](docs/pt-br/00-arquitetura.md)
- [Control plane](docs/architecture/control-plane.md)
- [Host-agent](docs/architecture/host-agent.md)
- [Lifecycle dos projetos](docs/architecture/project-lifecycle.md)
- [Storage compartilhado, S3 e Storage Vectors](docs/architecture/storage-vectors-lifecycle.md)
- [Chaves de API opacas](docs/pt-br/12-chaves-api-opacas.md)
- [OpenResty/Lua](docs/architecture/openresty-lua.md)
- [Supabase Analytics](docs/architecture/supabase-analytics.md)
- [Realtime multi-tenant](docs/pt-br/09-autenticacao-multi-tenant-realtime.md)
- [Hardening do Postgres Meta](docs/pt-br/10-hardening-postgres-meta.md)
- [Criptografia e rotação de segredos](docs/pt-br/11-rotacao-cripto-conexoes.md)
- [Principais erros](docs/pt-br/05-principais-erros.md)

---

## Manutenção

### Rotação do certificado SSL

O setup gera um certificado autoassinado para o Authelia e para o gateway do Studio.

Por padrão, o certificado é válido por **825 dias**, conforme `tools/configure_studio_runtime.py`. Gere um novo certificado antes do vencimento para evitar perder o acesso à interface administrativa.

## Licença

Apache License 2.0. Consulte [`LICENSE`](LICENSE).
