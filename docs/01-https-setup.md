# HTTPS setup

By default, the platform is configured to run in a local development environment over HTTP. The steps below enable Traefik to operate over HTTPS and automatically generate SSL certificates with Let's Encrypt.

### ⚠️ Prerequisites

Before continuing, make sure that:

- **Valid domain**: You have a registered domain pointing to your server's IP
- **Configured DNS**: The domain has propagated and is reachable from the internet
- **Open ports**: Ports 80 and 443 are allowed by the firewall/cloud provider
> **Important**: Let's Encrypt works only with valid, publicly reachable domains. For local development, continue using HTTP or configure self-signed certificates.

---

### Step 1: Enable TLS in `traefik.yml`

For Traefik to generate and store Let's Encrypt SSL certificates, first adjust the permissions on the storage file and then edit the main configuration.

**1.1. Adjust `acme.json` permissions (critical step)**

Run the following command inside the `servidor/traefik/` folder to ensure Traefik can manage certificates securely.

```bash
# Set restrictive permissions (only the owner can read/write)
chmod 600 acme.json
```

Now open `servidor/traefik/traefik.yml` and make the following changes:

**1.2. Enable the HTTPS redirect**

This configuration instructs Traefik to redirect all traffic from port 80 (HTTP) to port 443 (HTTPS).

* **Find** the `entryPoints` section and **replace it** with the block below to enable the redirect and the `websecure` entrypoint:

    ```yaml
    entryPoints:
      web:
        address: ":80"
        http:
          redirections:
            entryPoint:
              to: websecure
              scheme: https
      websecure:
        address: ":443"
    ```

**1.3. Configure the certificate provider (Let's Encrypt)**

This tells Traefik how to obtain SSL certificates.

* **Add** the following block at the end of the file. **Remember to replace `your-email@example.com` with your email address.**

    ```yaml
    certificatesResolvers:
      letsencrypt:
        acme:
          email: your-email@example.com
          storage: /acme.json
          keyType: EC256
          httpChallenge:
            entryPoint: web
    ```

**1.4. Set TLS security defaults (optional but recommended)**

This block ensures that only modern, secure encryption ciphers are used.

* **Add** the following block at the end of the file:

    ```yaml
    tls:
      options:
        default:
          minVersion: "VersionTLS12"
          cipherSuites:
            - "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384"
            - "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
            - "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305"
            - "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305"
            - "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256"
            - "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
          curvePreferences:
            - "secp521r1"
            - "secp384r1"
    ```

> 💡 **Compatibility note**: Restricting the minimum version to `VersionTLS12` and limiting the ciphers provides excellent security and top scores in audits (such as SSL Labs), but may prevent very old clients or legacy devices (such as obsolete embedded systems) from connecting. If your business rules require support for those devices, you can remove or relax this configuration.

---

### Step 2: Adjust security headers in `middlewares.yml`

In production, sending the `Strict-Transport-Security` (HSTS) header is essential because it forces the browser to use HTTPS.

* Open `servidor/traefik/middlewares.yml`.
* **Find** the `security-headers` middleware and **replace it completely** with the version below:

    ```yaml
    # Replace the existing 'security-headers' middleware with this one:
    security-headers:
      headers:
        customRequestHeaders:
          X-Forwarded-Proto: "https"
        customResponseHeaders:
          X-Frame-Options: "DENY"
          X-Content-Type-Options: "nosniff"
          X-XSS-Protection: "1; mode=block"
          Strict-Transport-Security: "max-age=31536000; includeSubDomains; preload" 
          Content-Security-Policy: "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'"
          Referrer-Policy: "strict-origin-when-cross-origin"
    ```

> ⚠️ **Warning: Adjust this to your business rules!**
> The security headers above are strict and secure by default, but may be restrictive ("rigid") depending on your project:
>
> * **`Content-Security-Policy` (CSP)**:
>   * **What it does:** Prevents the browser from loading scripts, images, fonts, or making requests to or from domains other than the site itself (`'self'`).
>   * **When to adjust it:** If your application uses external APIs (e.g. Stripe, Google Maps), Google Fonts, or Supabase Storage to display images hosted in other buckets/domains, CSP will block the load. Add the allowed domains to the appropriate directives (e.g. `img-src 'self' data: https://*.supabase.co; connect-src 'self' https://api.yourservice.com`). During early development or testing, you can temporarily disable this header or use `Content-Security-Policy-Report-Only` to audit blocks without preventing the application from working.
> * **`Strict-Transport-Security` (HSTS)**:
>   * **What it does:** Forces the browser to always use HTTPS for the current domain and all its subdomains (`includeSubDomains; preload`) for one year (`max-age=31536000`).
>   * **Caution:** Once enabled and sent with `preload`, legacy subdomains or other services that still need to run without HTTPS will become completely inaccessible. Start with a shorter `max-age` and without `preload` or `includeSubDomains` during testing and staging (e.g. `"max-age=63072000"`).
> * **`X-Frame-Options`**:
>   * **What it does:** Prevents clickjacking attacks by stopping your site from being rendered inside an `<iframe>`.
>   * **When to adjust it:** If you plan to embed the dashboard or parts of your application in other platforms through an iframe, change `"DENY"` to `"SAMEORIGIN"`, or use the `frame-ancestors` directive in CSP.

---

### Step 3: Update the routers in middlewares.yml

* Open the file servidor/traefik/middlewares.yml.

* Adjust the entrypoints: For each router (malicious-paths, block-bad-useragents, and http-catchall), add `- websecure` to the `entryPoints` list and add the `tls: {}` key.

* Example for the malicious-paths router:

BEFORE:
```yml
    malicious-paths:
      rule: "..."
      entryPoints:
        - web
      priority: 2000
      middlewares:
        - malicious-paths-chain
      service: forbidden-service
```
AFTER:
```yml
    malicious-paths:
      rule: "..."
      entryPoints:
        - web
        - websecure
      tls: {}
      priority: 2000
      middlewares:
        - malicious-paths-chain
      service: forbidden-service
```
* Apply this step in the same way to the 'block-bad-useragents' and 'http-catchall' routers.

**3.1. Projects API router (projects-api)**

* Open the file servidor/traefik/render_dynamic_config.py.
* Find the block that builds the "projects-api" router.

BEFORE:
```python
        "      entryPoints:",
        "        - web",
        "      priority: 1000",
```
AFTER:
```python
        "      entryPoints:",
        "        - web",
        "        - websecure",
        "      tls: {}",
        "      priority: 1000",
```

## Step 4: Configure project routers for HTTPS

* This is the final step to expose your Supabase applications securely.

* In the same file, servidor/traefik/render_dynamic_config.py, find the block that builds the "project-{project_id}" router. Since this router is generated dynamically for all projects from the contents of projects/, this edit applies both to existing projects and to projects created later.

BEFORE:
```python
                "      entryPoints:",
                "        - web",
                "      priority: 500",
```
AFTER:
```python
                "      entryPoints:",
                "        - web",
                "        - websecure",
                "      tls: {}",
                "      priority: 500",
```

## Step 5: Apply the final configuration

After saving all changes to the *.yml files, restart the containers so the new rules are applied.

Run the following commands from your project root.

**5.1. Update the management server environment (Studio)**

The Studio Nginx needs to know that the backend now operates over HTTPS.

* Open the studio/.env file.

* Change the following variables to point to your domain and use the https protocol:

BEFORE:
```bash
SERVER_DOMAIN=http://<local_server_ip>
BACKEND_PROTO=http
```
AFTER:
```
SERVER_DOMAIN=https://your.domain.example
BACKEND_PROTO=https
```

**5.2. Restart all services**

The commands below force container recreation, ensuring they use the new .yml and .env files you modified.

Restart the edge gateway (Traefik), the dynamic configuration watcher, and the writer-permission watcher for the 'acme.json' file:

```bash
# Apply the new HTTPS configuration and certificate resolvers.
docker compose -f servidor/traefik/docker-compose.yml up -d --force-recreate
```

Restart the management interface (Studio):

```bash
# Apply the new backend environment variables.
docker compose -f studio/docker-compose.yml up -d --force-recreate
```
