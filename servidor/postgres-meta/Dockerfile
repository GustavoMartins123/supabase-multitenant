ARG POSTGRES_META_IMAGE=supabase/postgres-meta:v0.96.1
FROM ${POSTGRES_META_IMAGE}

COPY internal-auth.mjs install-auth.mjs healthcheck.mjs /usr/src/app/security/
RUN node /usr/src/app/security/install-auth.mjs

HEALTHCHECK --interval=5s --timeout=5s --retries=3 CMD ["node", "/usr/src/app/security/healthcheck.mjs"]
