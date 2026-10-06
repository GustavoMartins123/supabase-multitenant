# Setup HTTPS

O Traefik possui um perfil TLS de produção, controlado por variáveis de ambiente. O renderizador da configuração dinâmica (`render_dynamic_config.py`) decide entre routers HTTP e routers `websecure` com redirecionamento automático HTTP→HTTPS, e falha fechado quando o protocolo declarado e o perfil TLS divergem ou quando os certificados estão ausentes. Edição manual de `traefik.yml` ou dos routers gerados não faz mais parte do procedimento.

## Variáveis do perfil (`servidor/.env`)

| Variável | Padrão | Significado |
| --- | --- | --- |
| `TRAEFIK_ENABLE_TLS` | `false` | Com `true`, todos os routers de serviço migram para `websecure` com fonte de certificado, e a porta 80 passa a responder só com redirecionamento permanente (além dos routers de proteção de borda). |
| `TRAEFIK_TLS_MODE` | `file` | `file` lê `tls.crt`/`tls.key` de `servidor/traefik/certs/traefik/`; `acme` usa Let's Encrypt pelo resolver `letsencrypt`. |
| `TRAEFIK_ACME_EMAIL` | placeholder | Obrigatório (sem placeholder) quando `TRAEFIK_TLS_MODE=acme`. |
| `TRAEFIK_HTTPS_PORT` | `443` | Porta do host publicada para `websecure`; também usada no destino do redirect. |
| `SERVER_PROTO` | preenchido pelo setup | Esquema declarado da plataforma. Se for `https` enquanto `TRAEFIK_ENABLE_TLS` não é `true`, o renderer levanta erro e nenhuma configuração nova é gravada. |

A porta `443` é sempre publicada no Compose do Traefik; sem `TRAEFIK_ENABLE_TLS=true` nada escuta com TLS nela e as conexões são fechadas sem rota.

## Comportamento fail-closed

O container watcher re-renderiza as rotas continuamente. Com `TRAEFIK_ENABLE_TLS=true`:

- `TRAEFIK_TLS_MODE=file` exige que `servidor/traefik/certs/traefik/tls.crt` e `tls.key` existam no momento do render; caso contrário o render falha, o healthcheck do watcher cai e o Traefik continua servindo a última configuração válida;
- `TRAEFIK_TLS_MODE=acme` exige um `TRAEFIK_ACME_EMAIL` real;
- `SERVER_PROTO=https` sem `TRAEFIK_ENABLE_TLS=true` aborta o render com erro explícito, em vez de servir HTTP puro silenciosamente.

## Modo 1 — `file` (self-signed ou CA interna, instalação por IP/LAN)

1. Gere o par em `servidor/traefik/certs/traefik/`, incluindo o IP do servidor em SAN:

    ```bash
    mkdir -p servidor/traefik/certs/traefik
    openssl req -x509 -newkey rsa:4096 -sha256 -days 825 -nodes \
      -keyout servidor/traefik/certs/traefik/tls.key \
      -out servidor/traefik/certs/traefik/tls.crt \
      -subj "/CN=supabase-local" \
      -addext "subjectAltName=IP:<SEU_IP>,DNS:seu.dominio.local"
    chmod 600 servidor/traefik/certs/traefik/tls.key
    ```

2. No `servidor/.env`: `TRAEFIK_ENABLE_TLS=true`, `TRAEFIK_TLS_MODE=file`.
3. Recrie o Traefik:

    ```bash
    docker compose -f servidor/traefik/docker-compose.yml up -d --force-recreate
    ```

4. Valide: `curl -k https://<SEU_IP>/<project_ref>/rest/v1/` deve responder via Nginx do projeto, e `curl http://<SEU_IP>/<project_ref>/rest/v1/` deve retornar redirecionamento permanente.

## Modo 2 — `acme` (Let's Encrypt, domínio público)

Pré-requisitos: domínio registrado apontando para o servidor, DNS propagado, portas 80 e 443 liberadas e `acme.json` gravável apenas pelo dono:

```bash
chmod 600 servidor/traefik/acme.json
```

No `servidor/.env`: `TRAEFIK_ENABLE_TLS=true`, `TRAEFIK_TLS_MODE=acme`, `TRAEFIK_ACME_EMAIL=você@example.com`, e recrie o Traefik como acima. Os certificados são obtidos pelo desafio HTTP-01 no entrypoint `web` e ficam em `/acme.json`.

## Apontar o Studio para HTTPS

Com TLS habilitado no data plane, atualize o `studio/.env` para que a interface administrativa use o mesmo esquema:

```text
SERVER_DOMAIN=https://<ip-ou-dominio-do-servidor>
BACKEND_PROTO=https
```

E recrie o Studio:

```bash
docker compose -f studio/docker-compose.yml up -d --force-recreate
```

## Hardening opcional de transporte

- **HSTS**: adicione `Strict-Transport-Security` ao `customResponseHeaders` do middleware `security-headers` em `servidor/traefik/middlewares.yml`. Comece sem `preload` e com `max-age` curto durante a validação; com `preload`, voltar atrás vira impossível por um ano.
- **Piso de TLS**: um bloco `tls.options.default` (versão mínima, cipher suites) pode ser adicionado ao diretório dinâmico; aplique somente após confirmar que nenhum cliente legado precisa dos padrões relaxados.

## Precedência do redirect

O router gerado `force-https` usa prioridade `150` no entrypoint `web`: acima do catch-all genérico (`100`) para que caminhos desconhecidos sejam redirecionados, abaixo dos routers de scanner/deny (`>= 1900`) para que tráfego hostil continue sendo classificado e banido em HTTP puro, em vez de receber redirect.
