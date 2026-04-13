# Principais Erros e Soluções

Este documento lista os erros mais comuns que podem ocorrer no sistema e como resolvê-los.

---

## Índice

### Erros Críticos
- [1. Erro 502 Bad Gateway ao acessar projeto](#1-erro-502-bad-gateway-ao-acessar-projeto)
- [2. Porta já em uso ao criar projeto](#2-erro-ao-criar-projeto-porta-já-em-uso)
- [3. Usuário não consegue fazer login no Authelia](#3-usuário-não-consegue-fazer-login-no-authelia)
- [4. Projeto criado mas não aparece na lista](#4-projeto-criado-mas-não-aparece-na-lista)

### Erros Comuns
- [5. Problemas com storage após duplicação](#5-problemas-com-storage-após-duplicação-de-projeto)
- [6. Erro de permissões no storage](#6-erro-de-permissões-no-storage)
- [7. Replication slot travado](#7-replication-slot-travado)
- [8. "too many clients already" no PostgreSQL](#8-too-many-clients-already-no-postgresql)
- [9. Cookie de projeto inválido (erro 403)](#9-cookie-de-projeto-inválido-erro-403)
- [10. "network not found" ao iniciar containers](#10-erro-ao-iniciar-containers-network-not-found)
- [11. Projeto não responde após restart](#11-projeto-não-responde-após-restart)

### Referência Rápida
- [Comandos úteis para diagnóstico](#comandos-úteis-para-diagnóstico)
- [Reportando novos erros](#reportando-novos-erros)
- [Troubleshooting avançado](#troubleshooting-avançado)

---

## Erros Críticos

### 1. Erro 502 Bad Gateway ao Acessar Projeto

**Sintoma:**
- Ao tentar acessar um projeto pelo Studio, aparece erro 502
- Página em branco ou mensagem "Bad Gateway"

**Causa:**
O Nginx do Studio não consegue se comunicar com o Traefik, ou o Traefik não consegue encontrar o container do projeto.

**Como Diagnosticar:**

1. **Verifique os logs do Traefik:**
   ```bash
   docker logs traefik-traefik-1
   ```

2. **Procure por mensagens como:**
   - `"backend not found"`
   - `"no server available"`
   - Mensagens mostrando o UUID do container do projeto

3. **Verifique se o container do projeto está rodando:**
   ```bash
   docker ps | grep nome_do_projeto
   ```

**Soluções:**

**Solução 1: Container do projeto não está rodando**
```bash
docker ps -a | grep nome_do_projeto

cd servidor/projects/nome_do_projeto
docker compose -p nome_do_projeto \
  --env-file ../../.env \
  --env-file .env \
  up -d
```

**Solução 2: Traefik não está rodando**
```bash
docker ps | grep traefik

cd servidor/traefik
docker compose up -d
```

**Solução 3: Problema de rede Docker**
```bash
docker network ls | grep rede-supabase

docker network create rede-supabase \
  --driver bridge \
  --subnet 172.20.0.0/16 \
  --ip-range 172.20.0.0/18 \
  --gateway 172.20.0.1

docker restart traefik-traefik-1
docker restart nome_do_projeto-nginx-1
```

**Solução 4: Labels do Traefik incorretos**

Verifique se o `docker-compose.yml` do projeto tem os labels corretos:
```bash
cd servidor/projects/nome_do_projeto
cat docker-compose.yml | grep -A 5 "traefik.enable"
```

Deve ter algo como:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.supabase-nginx-nome_projeto.rule=PathPrefix(`/nome_projeto`)"
  - "traefik.http.services.supabase-nginx-nome_projeto.loadbalancer.server.port=PORTA"
```

**Como Prevenir:**
- Use a interface do Studio para gerenciar projetos (start/stop)
- Monitore os logs do Traefik regularmente
- Configure alertas para containers parados

---

### 2. Usuário Não Consegue Fazer Login no Authelia

**Sintoma:**
- Credenciais corretas, mas login falha
- Mensagem: "Invalid credentials" ou similar

**Causas Possíveis:**

**Causa 1: Usuário desativado**

Verifique o arquivo de usuários:
```bash
cat studio/authelia/users_database.yml | grep -A 20 "nome_usuario:"
```

Procure por:
```yaml
disabled: true
```

**Solução:**
```yaml
disabled: false
```

**Causa 2: Grupo "active" ausente**

Verifique se o usuário tem o grupo `active`:
```yaml
groups:
  - active
```

**Solução:**
Adicione o grupo `active` se estiver faltando.

**Causa 3: Hash de senha incorreto**

Gere um novo hash:
```bash
echo -n "senha_correta" | argon2 $(openssl rand -base64 32) -id -t 3 -m 16 -p 4 -l 32 -e
```

Substitua no arquivo `users_database.yml`.

**Causa 4: Certificado SSL inválido**

Se o certificado SSL do Authelia expirou (válido por 1 ano):

```bash
openssl x509 -in studio/authelia/ssl/ca.pem -noout -dates

sudo bash authelia.sh
```

**Como Diagnosticar:**
```bash
docker logs authelia

docker logs authelia | grep -i "authentication"
```

---

### 3. Projeto Criado Mas Não Aparece na Lista

**Sintoma:**
- Projeto foi criado (job status = "done")
- Mas não aparece na lista de projetos do usuário

**Causa:**
As chaves (anon_key, service_role) não foram armazenadas no banco.

**Como Diagnosticar:**
```bash
docker exec -it supabase-db psql -U supabase_admin -d postgres

SELECT name, anon_key, service_role FROM projects WHERE name = 'nome_projeto';
```

**Solução:**

1. **Extraia as chaves do projeto:**
   ```bash
   cd servidor/generateProject
   bash extract_token.sh nome_projeto
   ```

2. **Criptografe as chaves:**
   ```python
   from cryptography.fernet import Fernet
   
   fernet = Fernet(b'SEU_FERNET_SECRET_AQUI')
   
   anon_encrypted = fernet.encrypt(b'ANON_KEY_AQUI').decode()
   service_encrypted = fernet.encrypt(b'SERVICE_KEY_AQUI').decode()
   
   print(f"Anon: {anon_encrypted}")
   print(f"Service: {service_encrypted}")
   ```

3. **Atualize o banco:**
   ```sql
   UPDATE projects 
   SET anon_key = 'ANON_ENCRYPTED', 
       service_role = 'SERVICE_ENCRYPTED'
   WHERE name = 'nome_projeto';
   ```

**Como Prevenir:**
- Verifique os logs da API durante criação de projetos
- Monitore o status dos jobs

---

## Erros Comuns

### 4. Problemas com Storage Após Duplicação de Projeto

Este erro pode se manifestar de diferentes formas, mas todas relacionadas à cópia incorreta dos arquivos do storage.

**Sintomas Possíveis:**

**A) Arquivos não aparecem no projeto duplicado**
- Storage vazio mesmo após duplicação com dados
- Erro ao listar arquivos

**B) Arquivos listados mas não carregam (tela cinza)**
- Arquivo aparece na lista do Storage
- Ao clicar, apenas tela cinza com nome do arquivo
- Imagem não carrega

**C) Erro ao acessar arquivo**
- Logs mostram: `ENOENT: no such file or directory`

**Causas Raiz:**

1. **xattr perdidos:** O comando `tar` dentro do container não preserva extended attributes (xattr). O Storage usa xattr para armazenar metadados vitais (Content-Type, Cache-Control, etc.) diretamente no arquivo físico.

2. **Arquivo físico ausente:** Registro existe no banco (`storage.objects`) mas arquivo não existe no host. Acontece quando:
   - Duplicação copiou apenas o banco, não os arquivos
   - Arquivo deletado manualmente do host
   - Falha na cópia durante migração

**Como Diagnosticar:**

1. **Verifique se os arquivos existem no host:**
```bash
cd servidor/projects/projeto_duplicado/storage/stub/stub
ls -la bucket/
```

2. **Verifique se os xattr estão presentes:**
```bash
getfattr -d -m - bucket/path/arquivo.jpg
```

Deve mostrar atributos como:
```
user.content_type="image/jpeg"
user.cache_control="max-age=3600"
```

3. **Compare banco vs host:**
```bash
cd servidor/projects/nome_projeto

docker exec -it supabase-db psql -U supabase_admin -d nome_projeto -c \
  "SELECT name FROM storage.objects" > /tmp/db_files.txt

find storage/stub/stub -type f > /tmp/host_files.txt

diff /tmp/db_files.txt /tmp/host_files.txt
```

4. **Verifique logs do Storage:**
```bash
docker logs nome_projeto-storage-1 | grep ENOENT
```

**Solução Completa:**

**Passo 1: Limpe o storage corrompido**
```bash
cd servidor/projects

sudo rm -rf projeto_duplicado/storage/stub/stub/*
```

**Passo 2: Copie corretamente do projeto original**

**Opção A: Usar rsync (RECOMENDADO)**
```bash
sudo rsync -aAX projeto_original/storage/stub/stub/ \
  projeto_duplicado/storage/stub/stub/

sudo chown -R $(id -u):$(id -g) projeto_duplicado/storage/
```

**Opção B: Usar tar do host**
```bash
sudo tar -C projeto_original/storage/stub/stub -cpf - . | \
  sudo tar -C projeto_duplicado/storage/stub/stub -xpf -

sudo chown -R $(id -u):$(id -g) projeto_duplicado/storage/
```

**Passo 3: Verifique se funcionou**
```bash
cd servidor/projects/projeto_duplicado/storage/stub/stub

getfattr -d -m - bucket/path/arquivo.jpg

ls -la bucket/
```

**Passo 4: Teste no Studio**
- Acesse o projeto duplicado
- Vá em Storage
- Clique em um arquivo
- Deve carregar normalmente

**Solução Alternativa: Restaurar Apenas Arquivos Específicos**

Se apenas alguns arquivos estão com problema:

```bash
cd servidor/projects/nome_projeto/storage/stub/stub

sudo cp /caminho/backup/bucket/path/file.jpg bucket/path/

sudo chown $(id -u):$(id -g) bucket/path/file.jpg

setfattr -n user.content_type -v "image/jpeg" bucket/path/file.jpg
```

**Solução Drástica: Limpar Registros Órfãos**

Se não conseguir recuperar os arquivos:

```sql
DELETE FROM storage.objects 
WHERE name = 'bucket/path/file.jpg';
```

**Como Prevenir:**
- Sempre use `rsync -aAX` para copiar storage (preserva xattr automaticamente)
- Teste o acesso aos arquivos no Studio após duplicação
- Faça backup regular do storage
- Não delete arquivos manualmente do host

---

### 5. Erro de Permissões no Storage

**Sintoma:**
- Erro "Permission denied" ao acessar storage
- Duplicação falha por permissões

**Causa:**
Permissões incorretas nos arquivos do storage.

**Solução:**
```bash
cd servidor/projects/projeto
sudo chown -R $(id -u):$(id -g) storage/
sudo chmod -R 755 storage/
```

---

### 6. Replication Slot Travado

**Sintoma:**
- Erro ao deletar projeto
- Mensagem: "replication slot is active" ou "replication slot already exists"

**Causa:**
O Realtime ainda está usando o slot de replicação.

**Como Diagnosticar:**
```bash
docker exec -it supabase-db psql -U supabase_admin -d postgres

SELECT slot_name, active, active_pid 
FROM pg_replication_slots 
WHERE slot_name LIKE '%nome_projeto%';
```

**Solução:**

1. **Pause o Realtime temporariamente:**
   ```bash
   docker pause realtime-dev.supabase-realtime
   ```

2. **Termine o processo que está usando o slot:**
   ```sql
   -- No psql
   SELECT pg_terminate_backend(active_pid) 
   FROM pg_replication_slots 
   WHERE slot_name = 'supabase_realtime_replication_slot_nome_projeto';
   ```

3. **Aguarde alguns segundos e tente deletar o slot:**
   ```sql
   SELECT pg_drop_replication_slot('supabase_realtime_replication_slot_nome_projeto');
   ```

4. **Despause o Realtime:**
   ```bash
   docker unpause realtime-dev.supabase-realtime
   ```

**Como Prevenir:**
- Use a interface do Studio para deletar projetos (faz isso automaticamente)
- Não delete slots manualmente

---

### 7. "too many clients already" no PostgreSQL

**Sintoma:**
- Aplicações não conseguem conectar ao banco
- Erro: `FATAL: sorry, too many clients already`

**Causa:**
Número de conexões excedeu o `max_connections` configurado.

**Como Diagnosticar:**
```bash
docker exec -it supabase-db psql -U supabase_admin -d postgres

SELECT count(*) FROM pg_stat_activity;

SHOW max_connections;
```

**Solução Imediata:**
```sql
-- Termine conexões ociosas
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'idle' 
  AND state_change < now() - interval '10 minutes';
```

**Solução Permanente:**

Aumente o limite de conexões (veja `docs/02-Como-aumentar-o-limite-conexoes-postgres.md`):

```yaml
command:
  - postgres
  - -c
  - max_connections=1500
```

Reinicie o banco:
```bash
cd servidor
docker compose --env-file .env up -d --force-recreate db
```

---

### 8. Cookie de Projeto Inválido (Erro 403)

**Sintoma:**
- Ao acessar projeto, erro 403
- Logs do Nginx: "Assinatura de cookie inválida"

**Causa:**
O cookie `supabase_project` expirou (24h) ou foi corrompido.

**Solução:**

1. **Limpe os cookies do navegador** para o domínio do Studio

2. **Ou force a seleção de projeto novamente:**
   - Volte para a tela de seleção de projetos
   - Clique no projeto desejado

3. **Se o problema persistir, verifique o COOKIE_SIGN_SECRET:**
   ```bash
   # Verifique se está configurado
   cat studio/.env | grep COOKIE_SIGN_SECRET
   
   # Se estiver vazio, regenere:
   openssl rand -base64 32 | tr -d '\n'
   
   # Adicione ao studio/.env
   COOKIE_SIGN_SECRET=VALOR_GERADO
   
   # Reinicie o Nginx
   docker restart nginx
   ```

---

### 9. Erro ao Iniciar Containers: "network not found"

**Sintoma:**
- Containers não iniciam
- Erro: `network rede-supabase not found`

**Causa:**
A rede Docker foi removida ou não foi criada.

**Solução:**
```bash
docker network create rede-supabase \
  --driver bridge \
  --subnet 172.20.0.0/16 \
  --ip-range 172.20.0.0/18 \
  --gateway 172.20.0.1

bash start.sh
```

---

### 10. Projeto Não Responde Após Restart

**Sintoma:**
- Projeto foi reiniciado mas não responde
- Containers estão "running" mas não funcionam

**Causa:**
Ordem de inicialização incorreta ou serviços não prontos.

**Solução:**

1. **Verifique os healthchecks:**
   ```bash
   docker ps | grep nome_projeto
   # Procure por "(healthy)" ou "(unhealthy)"
   ```

2. **Verifique os logs de cada serviço:**
   ```bash
   docker logs nome_projeto-auth-1
   docker logs nome_projeto-rest-1
   docker logs nome_projeto-storage-1
   docker logs nome_projeto-meta-1
   ```

3. **Reinicie na ordem correta:**
   ```bash
   # Para todos
   docker stop $(docker ps -q --filter "name=nome_projeto")
   
   # Aguarde 5 segundos
   sleep 5
   
   # Inicie via interface do Studio (ordem correta automática)
   # Ou manualmente:
   docker start nome_projeto-meta-1
   sleep 2
   docker start nome_projeto-auth-1
   sleep 2
   docker start nome_projeto-rest-1
   sleep 2
   docker start nome_projeto-imgproxy-1
   sleep 2
   docker start nome_projeto-storage-1
   sleep 2
   docker start nome_projeto-nginx-1
   ```

---

## Comandos Úteis para Diagnóstico

### Verificar Status Geral
```bash
docker ps -a

docker ps | grep -E "traefik|authelia|nginx|supabase-db|realtime|pooler"

docker ps | grep nome_projeto
```

### Logs
```bash
docker logs traefik-traefik-1 --tail 100 -f

docker logs authelia --tail 100 -f

docker logs nginx --tail 100 -f

docker logs docker-projects-api-1 --tail 100 -f

docker logs supabase-db --tail 100 -f
```

### Verificar Conectividade
```bash
docker exec traefik-traefik-1 ping supabase-nginx-nome_projeto

docker exec nginx ping traefik-traefik-1

docker exec -it supabase-db psql -U supabase_admin -d postgres -c "SELECT 1;"
```

### Limpeza
```bash
docker container prune

docker image prune

docker volume prune

docker network prune
```

---

## Reportando Novos Erros

Se você encontrou um erro que não está listado aqui:

1. **Colete informações:**
   - Mensagem de erro completa
   - Logs relevantes
   - Passos para reproduzir

2. **Verifique os logs:**
   ```bash
   # Salve os logs em um arquivo
   docker logs CONTAINER > erro.log 2>&1
   ```

3. **Abra uma issue no GitHub** com:
   - Descrição do problema
   - Logs (remova informações sensíveis)
   - Ambiente (versões, sistema operacional)

---

## Troubleshooting Avançado

### Modo Debug do Nginx

Para ver mais detalhes nos logs do Nginx:

```bash
nano studio/nginx/nginx.conf

error_log /var/log/studio_error.log debug;

docker restart nginx

docker exec nginx tail -f /var/log/studio_error.log
```

### Cache de Service Keys

O Nginx mantém um cache em memória (`lua_shared_dict service_keys`, 10MB) 
com TTL de 10 minutos. Quando um projeto é acessado, a `service_role` é 
buscada uma vez na API e armazenada — as requisições seguintes usam o cache.

**Para limpar o cache manualmente:**
```bash
docker restart nginx
```

> ⚠️ Reiniciar o Nginx derruba todos os projetos por alguns segundos.

### Resetar Tudo (Último Recurso)

⚠️ **ATENÇÃO:** Isso vai parar todos os containers e limpar caches.

```bash
docker stop $(docker ps -q)

docker system prune -a --volumes

docker network create rede-supabase \
  --driver bridge \
  --subnet 172.20.0.0/16 \
  --ip-range 172.20.0.0/18 \
  --gateway 172.20.0.1

bash start.sh
```

---

**Última atualização:** Abril 2026

**Contribuições:** Se você resolveu um erro de forma diferente ou encontrou um novo, por favor contribua atualizando este documento!
