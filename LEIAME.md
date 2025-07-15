# Documentação do supabase-multitenant

## Visão Geral

A stack oficial de auto-hospedagem do Supabase foi projetada para um único projeto. Este repositório resolve essa limitação oferecendo uma arquitetura multi-tenant.

A solução provisiona um banco de dados isolado para cada novo tenant e utiliza uma API de orquestração (FastAPI) para gerenciar o ciclo de vida do projeto. O diferencial chave é um gateway dinâmico OpenResty/Lua que permite que **uma única instância do Supabase Studio** gerencie todos os tenants de forma segura e centralizada, contornando uma limitação fundamental da ferramenta.

---

## Sumário

* [Visão Geral](#visão-geral)
* [Propósito](#propósito)
* [Arquitetura](#arquitetura)
* [Pré-requisitos](#pré-requisitos)

### Como utilizar

* [1. Clonar o repositório](#1-clonar-o-repositório)
* [2. Executar o script de configuração](#2-executar-o-script-de-configuração)
* [3. Ordem de execução](#3-ordem-de-execução)
* [4. Verificação](#4-verificação)

### Manutenção e Notas Importantes

* [Rotação do Certificado SSL](#rotação-do-certificado-ssl)

## Propósito

Simplificar a criação e a gestão de novos projetos utilizando a arquitetura do Supabase como base.

---

## Arquitetura

```mermaid
flowchart TB
 subgraph subGraph0["Estúdio Local - :4000"]
        Authelia["🔐 Authelia :9091\nAutenticação"]
        Lan["🛜 Internet/Usuários/LAN"]
        Nginx["🌐 Nginx/OpenResty :443\nGerenciador Local"]
        Flutter["📱 Flutter Web\nSeletor de Projetos"]
        Studio["📊 Supabase Studio\nInterface Final"]
  end
 subgraph subGraph1["Servidor Local - Serviços Compartilhados"]
        DB["🗄️ PostgreSQL\nsupabase-db\nBanco Principal"]
        Realtime["⚡ Realtime :4000\nGlobal"]
        Pooler["🏊 Supavisor\nPool de Conexões\nGlobal"]
        Functions["⚙️ Edge Functions\n/functions/main\nGlobal"]
  end
 subgraph subGraph2["Projeto A (project_id_a)"]
        NginxA["🌐 Nginx A :port_a\n/project_id_a"]
        AuthA["🔑 GoTrue A :9999"]
        RestA["📡 PostgREST A :3000"]
        StorageA["📦 Storage A :5000"]
        MetaA["🔧 Meta A :meta_port_a"]
        ImgA["🖼️ ImgProxy A :5001"]
  end
 subgraph subGraph3["Projeto B (project_id_b)"]
        NginxB["🌐 Nginx B :port_b\n/project_id_b"]
        AuthB["🔑 GoTrue B :9999"]
        RestB["📡 PostgREST B :3000"]
        StorageB["📦 Storage B :5000"]
        MetaB["🔧 Meta B :meta_port_b"]
        ImgB["🖼️ ImgProxy B :5001"]
  end
 subgraph subGraph4["Projetos Dinâmicos"]
    direction TB
        subGraph2
        subGraph3
  end
 subgraph subGraph5["Rede Docker"]
        Network["🔗 rede-supabase\n172.20.0.0/16"]
  end
    World["🌐 Internet/Usuários"] -- World --> Traefik["🚦 Traefik :80/:443\nGateway Principal"]
    Lan -- :9091 --> Authelia
    Authelia -- :4000 --> Nginx
    Nginx --> Flutter
    Flutter --> Studio
    Nginx -. "LAN - Requisições por projeto via '/project_id'" .-> Traefik
    Traefik -. LAN .-> API["🐍 API de Projetos :18000\nPython\nGerencia Projetos"]
    Pooler --> DB
    NginxA --> AuthA & RestA & StorageA & Functions
    NginxA -. via roleKey .-> MetaA
    StorageA --> ImgA
    NginxB --> AuthB & RestB & StorageB & Functions
    NginxB -. via roleKey .-> MetaB
    StorageB --> ImgB
    Traefik --> NginxA
    Traefik --> NginxB
    AuthA -. via Pooler .-> Pooler
    RestA -. via Pooler .-> Pooler
    StorageA -. via Pooler .-> Pooler
    MetaA -. Conexão Direta .-> DB
    AuthB -. via Pooler .-> Pooler
    RestB -. via Pooler .-> Pooler
    StorageB -. via Pooler .-> Pooler
    MetaB -. Conexão Direta .-> DB
    NginxA -. WebSocket .-> Realtime
    NginxB -. WebSocket .-> Realtime
    API -. Cria/Gerencia .-> NginxA & NginxB
    API -. Docker Socket .-> DockerSock["🐳 Docker Socket\nCriação de Containers"]
    Flutter -. "/set-project?ref=" .-> Nginx
     Authelia:::studio
     Nginx:::studio
     Flutter:::studio
     Studio:::studio
     DB:::shared
     Realtime:::shared
     Pooler:::shared
     Functions:::shared
     NginxA:::project
     AuthA:::project
     RestA:::project
     StorageA:::project
     MetaA:::project
     ImgA:::project
     NginxB:::project
     AuthB:::project
     RestB:::project
     StorageB:::project
     MetaB:::project
     ImgB:::project
     World:::external
     Traefik:::gateway
     API:::api
    classDef external fill:#e1f5fe
    classDef gateway fill:#f3e5f5
    classDef shared fill:#e8f5e8
    classDef project fill:#fff3e0
    classDef studio fill:#fce4ec
    classDef api fill:#f1f8e9
```

---

## Pré-requisitos

| Item                    | Descrição                                    |
| ----------------------- | -------------------------------------------- |
| Docker & Docker Compose | Instalado e em execução.                     |
| Usuário                 | Com permissão para executar comandos Docker. |

---

## Como utilizar

### 1. Clonar o repositório

```bash
git clone git@github.com:GustavoMartins123/supabase-multitenant.git
cd supabase-multitenant
```

### 2. Executar o script de configuração

```bash
bash setup.sh
# O IP ou domínio do servidor solicitado pelo script é onde o banco de dados e o Traefik serão hospedados.
```

### 3. Iniciando os Contêineres

Você tem duas opções para rodar a plataforma. Escolha a que melhor se adapta às suas necessidades.

**Opção 1: Início Automatizado (Recomendado)**

Para a maioria dos casos de uso, especialmente para um primeiro teste, o script `start.sh` fornecido cuida de iniciar todos os serviços na ordem correta.

```bash
# Este comando irá iniciar os serviços principais, o gateway e a interface de gerenciamento
bash start.sh
```
---
**Opção 2: Início Manual (Para Controle ou Depuração)**

Se você prefere iniciar cada parte da plataforma individualmente para ter mais controle ou para depurar um serviço específico, execute os seguintes comandos **em vez de** usar o `start.sh`.

1.  **Inicie os Serviços Base (Banco de Dados):**

    ```bash
    # Inicia o PostgreSQL, a API de gerenciamento, etc.
    cd servidor/
    docker compose --env-file secrets/.env --env-file .env up -d
    cd .. 
    ```

2.  **Inicie o Gateway de Borda (Traefik):**

    ```bash
    # Inicia o proxy reverso que gerencia todo o tráfego externo.
    cd traefik/
    docker compose up -d
    cd ..
    ```

3.  **Inicie a Interface de Gerenciamento (Studio):**

    ```bash
    # Inicia o Nginx/Lua e a interface Flutter.
    cd studio/
    sudo docker compose up -d
    cd ..
    # Nota: na arquitetura base o studio serve para ser usado em uma máquina diferente do servidor,
    # mas deve funcionar também em uma única máquina, vai da sua escolha.
    ```

### 4. Verificação

Após alguns instantes, verifique se todos os containers estão em execução:

```bash
docker ps
```

Se tudo estiver com status `Up`, acesse a interface no IP que você configurou no `setup.sh` (por exemplo: `https://<seu_ip_local>:9091`).
Você deverá ser redirecionado para a tela de login do Authelia.
Use o usuário 'teste' com a senha 'teste' para fazer login.

---

## Manutenção e Notas Importantes

### Rotação do Certificado SSL

* O script `setup.sh` gera automaticamente um certificado SSL autoassinado para o Authelia e o Nginx do Studio, garantindo comunicação HTTPS em sua rede local.
* **Atenção:** Por padrão, esse certificado é válido por **1 ano**. Após esse período, ele deixará de funcionar.
