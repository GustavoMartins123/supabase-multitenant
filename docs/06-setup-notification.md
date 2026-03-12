## Setup de Notificações Push (Firebase FCM)

Por padrão, a plataforma utiliza uma arquitetura descentralizada para o envio de notificações push via Firebase Cloud Messaging (FCM). O roteamento e a assinatura de segurança (OAuth2) acontecem na borda (Gateway Nginx), enquanto um *Worker* assíncrono em Python gerencia as filas usando um padrão híbrido de escuta ativa (LISTEN/NOTIFY) no PostgreSQL.

> [!NOTE]
> A infraestrutura do **Gateway (Nginx + Lua)** já vem **100% configurada**. O endpoint `/api/internal/push` e a lógica de autenticação JWT com o Google já estão prontos para uso, bastando apenas o arquivo de credenciais.

Os passos a seguir configuram as credenciais do Google e preparam o banco de dados dos projetos para se integrarem a esse fluxo.

### ⚠️ Pré-requisitos

Antes de prosseguir, certifique-se de que:

- **Projeto Firebase**: Você possui um projeto criado no [Firebase Console](https://console.firebase.google.com/).
- **Service Account**: Você gerou e baixou a chave privada (arquivo JSON) da Conta de Serviço do Firebase (Configurações do Projeto > Contas de Serviço > Gerar nova chave privada).
- **Worker em execução**: O serviço `push-worker` está configurado e rodando no seu ambiente Docker.

---

### Passo 1: Fornecer a Chave do Firebase ao Gateway

Como o script Lua (`send_push.lua`) já está configurado no Nginx para assinar o JWT e disparar o push, você só precisa fornecer a chave de serviço. O Nginx possui um volume mapeado para a pasta `./authelia` no host, correspondendo ao diretório `/config` internamente.

**1.1. Renomear e Posicionar o Arquivo**

Pegue o arquivo JSON baixado do Firebase Console, renomeie-o para `firebase.json` e mova-o para dentro da pasta `authelia` do seu servidor Gateway. A rota `/api/internal/push` utilizará este arquivo automaticamente.

Execute o comando a partir da raiz do seu servidor de borda:

```bash
# Move o arquivo para a pasta que o Nginx lê como /config
mv /caminho/do/seu/download/arquivo-do-google.json ./authelia/firebase.json
```

Importante: Certifique-se de que o arquivo seja um arquivo real e não um diretório. Se o Docker criou uma pasta fantasma chamada `firebase.json/` anteriormente, exclua a pasta antes de mover o arquivo. O Nginx refletirá a mudança na mesma hora, sem necessidade de reiniciar.

### Passo 2: Estruturar o Banco de Dados dos Projetos

Para cada projeto (tenant) que utilizará notificações, precisamos criar as tabelas do padrão Outbox, a função de alerta e as políticas de segurança (RLS).

Abra o painel SQL do Supabase do seu projeto e execute os blocos a seguir.

**2.1. Criar Tabela de Tokens e RLS**

Esta tabela armazena os tokens FCM dos dispositivos dos usuários.

```sql
CREATE TABLE public.push_tokens (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NULL,
  token text NOT NULL,
  platform text NULL,
  created_at timestamp with time zone NULL DEFAULT now(),
  CONSTRAINT push_tokens_pkey PRIMARY KEY (id),
  CONSTRAINT push_tokens_token_key UNIQUE (token),
  CONSTRAINT push_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE,
  CONSTRAINT push_tokens_platform_check CHECK (
    (platform = ANY (ARRAY['ios'::text, 'android'::text]))
  )
) TABLESPACE pg_default;


ALTER TABLE public.push_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Usuários gerenciam seus próprios tokens" 
ON public.push_tokens 
FOR ALL 
USING (auth.uid() = user_id);

ALTER TABLE public.push_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Usuários gerenciam seus próprios tokens" 
ON public.push_tokens 
FOR ALL 
USING (auth.uid() = user_id);
```

**2.2. Criar Função de Alerta (O Grito do Banco)**

Esta função é a peça central do sistema híbrido. Ela acorda o Worker em Python instantaneamente via canal Pub/Sub do Postgres, economizando processamento de CPU (evitando polling constante).

```sql
CREATE OR REPLACE FUNCTION notify_new_push()
RETURNS trigger AS $$
BEGIN
  -- Emite um sinal no canal 'new_push' para acordar o Worker
  PERFORM pg_notify('new_push', ''); 
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**2.3. Criar Tabela de Notificações e Trigger**

Esta é a "caixa de saída". Insira mensagens nesta tabela (com status pendente) para que o Worker as processe e envie.

```sql
CREATE TABLE public.notifications (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NULL,
  body text NOT NULL,
  created_at timestamp with time zone NULL DEFAULT now(),
  status text NULL DEFAULT 'pendente'::text,
  CONSTRAINT notifications_pkey PRIMARY KEY (id),
  CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
) TABLESPACE pg_default;

CREATE TRIGGER trigger_new_push
AFTER INSERT ON public.notifications 
FOR EACH STATEMENT 
EXECUTE FUNCTION notify_new_push();

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Usuários leem apenas suas notificações" 
ON public.notifications 
FOR SELECT 
USING (auth.uid() = user_id);
```

### Passo 3: Ativar o Worker no Docker Compose

Por padrão, para economizar recursos caso o módulo de notificações não seja utilizado, o serviço do `push-worker` vem comentado no arquivo de orquestração da API.

Você deve editar o arquivo `docker-compose-api.yml` e descomentar o bloco correspondente.

**3.1. Editar o arquivo**
Abra o `docker-compose-api.yml` e remova os `#` da frente do serviço `push-worker`. Ele deve ficar alinhado com o `projects-api`, assim:

```yaml
  push-worker:
    build:
      context: .
      dockerfile: ./api-internal/Dockerfile
    restart: unless-stopped
    networks: [rede-supabase]
    environment:
      PYTHONUNBUFFERED: 1
      DB_DSN: postgres://supabase_admin:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/postgres
    command: ["python", "app/push_worker.py"]
```

**3.2. Aplicar a alteração**
Após salvar o arquivo, suba o contêiner executando o comando abaixo na pasta raiz:

```bash
docker compose -f docker-compose-api.yml --env-file secrets/.env --env-file .env u
```

### Passo 4: Como Enviar uma Notificação

A partir deste momento, o fluxo está completamente automatizado. O Nginx está com a chave, o Python está monitorando dinamicamente e o banco possui o gatilho.

Para disparar uma notificação, basta que o seu aplicativo, uma função Edge, ou uma Trigger de outra tabela insira um registro na tabela notifications:

```sql
-- Exemplo de envio via SQL
INSERT INTO public.notifications (user_id, body) 
VALUES ('uuid-do-usuario-aqui', 'Sua nova notificação chegou!');
```

O status mudará automaticamente de pendente para enviado, sem_token ou erro.

### Passo 5: Troubleshooting e Logs

Se as notificações não estiverem chegando ou o status no banco de dados ficar como `erro`, a investigação deve seguir uma ordem específica para identificar onde a falha ocorreu:

**5.1. Verificando o Worker (Servidor de Projetos)**

O primeiro lugar para olhar é o contêiner do Python, pois ele é responsável por ler a fila do banco e iniciar o disparo. Execute o comando no servidor onde a API dos projetos está rodando:

```bash
docker logs -f docker-push-worker-1
```

**5.2. Verificando o Gateway Nginx (Servidor Studio)**

Se o log do Worker não mostrar nenhum erro de conexão, mas a notificação ainda não chegou, o bloqueio ocorreu na camada do Lua/Nginx (validação do JWT, leitura do firebase.json ou comunicação com o Google).

Acesse o contêiner do Nginx no servidor do Studio e leia o arquivo de log de erros:

```bash
docker exec -it nginx bash
cat /var/log/studio_error.log
```