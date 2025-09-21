# Aumentando numero de conexões do realtime


### 1. Parâmetros que importam

| Variável               | Pra que serve                                                                          |
| ---------------------- | -------------------------------------------------------------------------------------- |
| `NUM_ACCEPTORS`        | Limite global de conexões simultâneas aceitas pelo serviço Realtime (todos os tenants) |
| `MAX_CONCURRENT_USERS` | Limite de conexões simultâneas por tenant/projeto registrado no Realtime               |


### 2. Ajustando Limites para Novos Projetos

Ao criar um novo projeto, os limites padrões são definidos nas variáveis de ambiente do serviço Realtime.

* Arquivo de configuração -> **servidor/.env**

* Parâmetros chave:
    ```ini
    NUM_ACCEPTORS=2000          # Limite total de conexões aceitas pelo serviço Realtime
    MAX_CONCURRENT_USERS=1000   # Limite padrão por projeto/tenant
    ```
Como ajustar:
Altere os valores desses parâmetros no arquivo .env antes de subir ou reiniciar o serviço.


### 3. Atualizando Limites de Projetos Existentes

* **Para alterar o limite de um projeto que já foi criado, é necessário executar um comando UPDATE diretamente no banco de dados.**

* Acesse o psql dentro do contêiner do banco de dados:

    ```bash
    docker exec -it supabase-db psql -U supabase_admin
    ```

* **Para atualizar TODOS os tenants existentes para um novo limite:**

    ```sql
    -- Exemplo: Define o limite de todos para 2000 usuários
    UPDATE _realtime.tenants SET max_concurrent_users = 2000;
    ```
* **Para atualizar um tenant ESPECÍFICO pelo nome do projeto:**

    ```sql
    -- Exemplo: Define o limite do projeto 'meu_projeto_especial' para 5000
    UPDATE _realtime.tenants 
    SET max_concurrent_users = 5000 
    WHERE external_id = 'meu_projeto_especial';
    ```

Por fim reinicie o container do realtime.

```bash
docker restart realtime-dev.supabase-realtime
```