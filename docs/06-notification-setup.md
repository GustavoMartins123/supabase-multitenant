# Push notification setup (Firebase FCM)

By default, the platform uses a decentralized architecture to send push notifications through Firebase Cloud Messaging (FCM). Routing and the security signature (OAuth2) happen at the edge (Nginx Gateway), while an asynchronous Python *Worker* manages queues using a hybrid active-listening pattern (LISTEN/NOTIFY) in PostgreSQL.

> [!NOTE]
> The base **Gateway (Nginx + Lua)** push infrastructure is already available, but the current flow does not rely only on `firebase.json`.
> The `/api/internal/push` route is protected by a backend-to-backend HMAC signature and is intended exclusively for `push-worker`.
> If the worker runs on another machine, it must call the Studio Nginx at `https://<STUDIO_IP>:9091/api/internal/push`.
> Port `9091` is the Studio's single public origin; Authelia is available from the same origin at `/auth`.

The following steps configure Google credentials and prepare the project databases to integrate with this flow.

### ⚠️ Prerequisites

Before continuing, make sure that:

- **Firebase project**: You have a project created in the [Firebase Console](https://console.firebase.google.com/).
- **Service account**: You generated and downloaded the private key (JSON file) for the Firebase Service Account (Project Settings > Service Accounts > Generate new private key).
- **Worker enabled**: by default, the `push-worker` service is commented out in `servidor/docker-compose-api.yml`. Uncomment it and start the container before validating the end-to-end flow.
- **Internal shared secret**: `INTERNAL_HMAC_SECRET` must have the same value in `studio/.env` and `servidor/.env`. `setup.sh` generates this value automatically.
- **Correct gateway URL**: `PUSH_API_URL` must point to `https://<STUDIO_IP>:9091/api/internal/push`.
- **Trusted TLS between machines**: if `PUSH_VERIFY_TLS=true`, the Studio certificate must be trusted by the Python server. `setup.sh` copies `studio/authelia/ssl/ca.pem` to `servidor/certs/ca.pem`, which is mounted in the container as `/docker/push-certs/ca.pem`.

---

### Step 1: Provide the Firebase key to the Gateway

Because the Lua script (`send_push.lua`) is already configured in Nginx to sign the JWT and trigger the push, you only need to provide the service key. Nginx has a volume mapped to the `./authelia` folder on the host, corresponding to the `/config` directory internally.

**1.1. Rename and place the file**

Take the JSON file downloaded from Firebase Console, rename it to `firebase.json`, and move it into the `authelia` folder on your Gateway server. The `/api/internal/push` route will use this file automatically.

Run the command from the root of your edge server:

```bash
# Move the file to the folder that Nginx reads as /config
mv /path/to/your/download/google-service-account.json ./authelia/firebase.json
```

Important: Make sure the file is an actual file and not a directory. If Docker previously created a ghost folder named `firebase.json/`, remove the folder before moving the file. Nginx will reflect the change immediately without a restart.

### Step 1.2: Confirm integration variables between Studio and Worker

The current push flow depends on the variables below:

```env
# studio/.env
INTERNAL_HMAC_SECRET=...
INTERNAL_HMAC_MAX_SKEW_SECONDS=60

# servidor/.env
INTERNAL_HMAC_SECRET=...
PUSH_API_URL=https://<STUDIO_IP>:9091/api/internal/push
PUSH_VERIFY_TLS=true
PUSH_CA_FILE=/docker/push-certs/ca.pem
```

Important notes:

- `INTERNAL_HMAC_SECRET` must be the same on both machines. The worker uses this secret to sign each call, and Lua validates the signature.
- `INTERNAL_HMAC_MAX_SKEW_SECONDS` defines the maximum window, in seconds, accepted by Nginx between the signed timestamp and the local clock. The default is `60`.
- `PUSH_API_URL` must point to the IP or domain used in the Studio certificate.
- If the Studio certificate is self-signed, it must contain a SAN compatible with the host used in `PUSH_API_URL`.

The worker call to `/api/internal/push` uses these internal headers:

```text
X-Internal-Service: push-worker
X-Internal-Timestamp: <unix_timestamp>
X-Internal-Nonce: <random_nonce>
X-Internal-Signature: <hmac_sha256_hex>
```

The HMAC signs the method, path, timestamp, nonce, and `sha256` of the request body. Nginx validates the time window and temporarily stores the nonce to reduce replay.

### Step 2: Structure the project databases

For each project (tenant) that will use notifications, create the Outbox tables, the notification function, and the security policies (RLS).

Open your project's Supabase SQL panel and run the following blocks.

**2.1. Create the token table and RLS**

This table stores users' device FCM tokens.

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

CREATE POLICY "Users manage their own tokens"
ON public.push_tokens 
FOR ALL 
USING (auth.uid() = user_id);
```

**2.2. Create the notification function (the database callout)**

This function is the centerpiece of the hybrid system. It immediately wakes the Python Worker through the Postgres Pub/Sub channel, saving CPU (by avoiding constant polling).

```sql
CREATE OR REPLACE FUNCTION notify_new_push()
RETURNS trigger AS $$
BEGIN
  -- Emit a signal on the 'new_push' channel to wake the Worker
  PERFORM pg_notify('new_push', ''); 
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**2.3. Create the notification table and trigger**

This is the "outbox". Insert messages into this table (with a pending status) for the Worker to process and send.

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

CREATE POLICY "Users read only their notifications"
ON public.notifications 
FOR SELECT 
USING (auth.uid() = user_id);
```

### Step 3: Enable the Worker in Docker Compose

By default, to save resources when the notification module is not used, the `push-worker` service is commented out in the API orchestration file.

Edit `docker-compose-api.yml` and uncomment the corresponding block.

**3.1. Edit the file**
Open `docker-compose-api.yml` and remove the `#` characters in front of the `push-worker` service. It should be aligned with `projects-api`, as follows:

```yaml
  push-worker:
    container_name: push-worker
    build:
      context: .
      dockerfile: ./api-internal/Dockerfile
    restart: unless-stopped
    networks: [rede-supabase]
    environment:
      PYTHONUNBUFFERED: 1
      DB_DSN: postgres://supabase_admin:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/postgres
      PUSH_API_URL: ${PUSH_API_URL}
      INTERNAL_HMAC_SECRET: ${INTERNAL_HMAC_SECRET}
      PUSH_VERIFY_TLS: ${PUSH_VERIFY_TLS}
      PUSH_CA_FILE: ${PUSH_CA_FILE}
    volumes:
      - ./certs:/docker/push-certs:ro
    command: ["python", "app/push_worker.py"]
```

**3.2. Apply the change**
After saving the file, start the container by running the following command inside the `servidor/` folder:

```bash
docker compose -f docker-compose-api.yml --env-file .env up --build -d push-worker
```

### Step 4: How to send a notification

At this point, the flow is fully automated. Nginx has the key, Python is monitoring dynamically, and the database has the trigger.

To trigger a notification, your application, an Edge Function, or a trigger on another table only needs to insert a record into the notifications table:

```sql
-- Example sent through SQL
INSERT INTO public.notifications (user_id, body) 
VALUES ('user-uuid-here', 'Your new notification arrived!');
```

The status automatically changes from pending to sent, no_token, or error.

### Step 5: Troubleshooting and logs

If notifications are not arriving or the database status becomes `erro`, investigate in a specific order to identify where the failure occurred:

**5.1. Check the Worker (Project Server)**

The first place to look is the Python container, which reads the database queue and starts delivery. Run the command on the server where the Projects API is running:

```bash
docker logs -f push-worker
```

If a TLS error such as `certificate verify failed` or `IP address mismatch` appears, check in this order:

1. `PUSH_API_URL` uses the correct host and port `9091`
2. the Studio certificate contains a SAN for that IP or domain
3. `servidor/certs/ca.pem` was updated with the correct certificate
4. the `push-worker` container was recreated after the certificate change

**5.2. Check the Nginx Gateway (Studio Server)**

If the Worker log shows no connection error but the notification still has not arrived, the block occurred in the Lua/Nginx layer (internal HMAC validation, reading firebase.json, Google OAuth2 signing, or communication with Firebase).

Access the Nginx container on the Studio server and read the error log:

```bash
docker exec -it nginx bash
cat /var/log/studio_error.log
```

If the log shows `401` or `403` for `/api/internal/push`, check:

- whether the worker's `INTERNAL_HMAC_SECRET` is the same as the one in `studio/.env`
- whether the worker is making a `POST`
- whether the clocks on both machines are synchronized, since the signature uses a short timestamp window
- whether the Studio Nginx was recreated after the `.env` update
