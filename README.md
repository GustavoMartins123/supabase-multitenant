# Documentação supabase-multitenant

## Visão geral

A stack oficial de auto-hospedagem do Supabase é projetada para um único projeto. Este repositório resolve essa limitação, oferecendo uma arquitetura multi-tenant.

A solução provisiona um banco de dados isolado para cada novo inquilino e utiliza uma API(fast-api) de orquestração para gerenciar o ciclo de vida dos projetos. O principal diferencial é um gateway OpenResty/Lua que permite o uso de uma **única instância do Supabase Studio** para administrar todos os inquilinos de forma centralizada e segura, contornando uma limitação fundamental da ferramenta.

---

## Sumário

- [Visão geral](#visão-geral)  
- [Propósito](#propósito)  
- [Pré-requisitos](#pré-requisitos)  

### Como Usar  
- [1. Clonar o repositório](#1-clonar-o-repositório)  
- [2. Rodar o script de configuração](#2-rodar-o-script-de-configuração)  
- [3. Ordem de execução](#3-ordem-de-execução)  
- [4. Verificação](#4-verificação)  

## Propósito

Simplificar a criação e gerenciamento de novos projetos usando a arquitetura do supabase como base

---

## Pré-requisitos

| Item | Descrição |
|------|-----------|
| Docker & Docker Compose | Instalados e funcionando. |
| Usuario    |   Com permissão para rodar comandos docker. |
| jq    |   Instalado na maquina. |

---

## Como Usar

### 1. Clonar o repositório

```bash
git clone git@github.com:GustavoMartins123/supabase-multitenant.git
cd supabase-multitenant
```
### 2. Rodar o script de configuração
 
```bash
bash setup.sh
#O IP do servidor ou Dominio que o script pedir é aonde o banco ficara hospedado com o traefik
```

### 3. Ordem de execução

1.  **Subir os Serviços Base (Banco):**
    ```bash
    # Inicia o PostgreSQL, a API de gerenciamento, etc.
    cd servidor/
    docker compose --env-file secrets/.env --env-file .env up -d
    cd .. 
    ```
2.  **Subir o Gateway de Borda (Traefik):**
    ```bash
    # Inicia o proxy reverso que gerencia todo o tráfego externo.
    cd traefik/
    docker compose up -d
    cd ..
    ```

3.  **Subir a Interface de Gerenciamento (Studio):**
    ```bash
    # Inicia o Nginx/Lua e a interface Flutter.
    cd studio/
    docker compose up -d
    cd ..
    # Um adendo, o studio foi arquitetado para ser utilizado em uma maquina diferente do servidor, mas a principio funciona em uma só.
    ```
### 4. Verificação

Após alguns instantes, verifique se todos os contêineres estão rodando:
```bash
docker ps
```
Se tudo estiver com o status `Up`, acesse a interface no IP que você configurou no `setup.sh` (ex: `https://<seu_ip_local>:9091`). Você deverá ser redirecionado para a tela de login do Authelia.
Use o usuario 'teste' com a senha 'teste' para logar
