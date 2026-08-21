# Realtime connection limit


### 1. Relevant parameters

| Variable               | Purpose                                                                                |
| ---------------------- | -------------------------------------------------------------------------------------- |
| `NUM_ACCEPTORS`        | Global limit of simultaneous connections accepted by the Realtime service (all tenants) |
| `MAX_CONCURRENT_USERS` | Simultaneous connection limit per tenant/project registered in Realtime                  |


### 2. Adjusting limits for new projects

When creating a new project, default limits are defined in the Realtime service environment variables.

* Configuration file -> **servidor/.env**

* Key parameters:
    ```ini
    NUM_ACCEPTORS=2000          # Total limit of connections accepted by the Realtime service
    MAX_CONCURRENT_USERS=1000   # Default limit per project/tenant
    ```
How to adjust:
Change these parameter values in the .env file before starting or restarting the service.


### 3. Updating limits for existing projects

* **To change the limit for an existing project, run an UPDATE command directly against the database.**

* Access psql inside the database container:

    ```bash
    docker exec -it supabase-db psql -U supabase_admin
    ```

* **To update ALL existing tenants to a new limit:**

    ```sql
    -- Example: Set everyone's limit to 2,000 users
    UPDATE _realtime.tenants SET max_concurrent_users = 2000;
    ```
* **To update a SPECIFIC tenant by project name:**

    ```sql
    -- Example: Set the 'meu_projeto_especial' project limit to 5,000
    UPDATE _realtime.tenants 
    SET max_concurrent_users = 5000 
    WHERE external_id = 'meu_projeto_especial';
    ```

Finally, restart the Realtime container.

```bash
docker restart realtime-dev.supabase-realtime
```
