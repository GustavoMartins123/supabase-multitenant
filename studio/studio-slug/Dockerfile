# Reproducible Studio build pinned to the exact upstream revision used by this
# deployment. The local patch is checked before being applied so an upstream
# change can never be accepted silently.
ARG SUPABASE_STUDIO_COMMIT=20290c71bdc48bef1720bfe7d292f3b9e6154f7d
ARG SUPABASE_STUDIO_REPOSITORY=https://github.com/supabase/supabase.git

FROM node:22-slim AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
      git \
      python3 \
      ca-certificates \
      build-essential && \
    rm -rf /var/lib/apt/lists/* && \
    update-ca-certificates

RUN npm install -g pnpm@10.24.0
WORKDIR /app

FROM base AS source
ARG SUPABASE_STUDIO_COMMIT
ARG SUPABASE_STUDIO_REPOSITORY

RUN git init /src && \
    git -C /src remote add origin "$SUPABASE_STUDIO_REPOSITORY" && \
    git -C /src fetch --depth=1 --filter=blob:none origin "$SUPABASE_STUDIO_COMMIT" && \
    git -C /src checkout --detach FETCH_HEAD && \
    test "$(git -C /src rev-parse HEAD)" = "$SUPABASE_STUDIO_COMMIT"

COPY studio-project-context.patch /tmp/studio-project-context.patch
RUN git -C /src apply --check /tmp/studio-project-context.patch && \
    git -C /src apply /tmp/studio-project-context.patch

FROM base AS turbo
COPY --from=source /src .
RUN pnpm dlx turbo@2.9.14 prune studio --docker

FROM base AS deps
COPY --from=turbo /app/out/json ./
COPY --from=turbo /app/out/pnpm-lock.yaml ./
COPY --from=source /src/patches ./patches
RUN pnpm install --frozen-lockfile

FROM deps AS builder
COPY --from=turbo /app/out/full ./
RUN pnpm --filter studio exec next build

FROM base AS production
ARG SUPABASE_STUDIO_COMMIT
ARG SUPABASE_STUDIO_REPOSITORY

# --- UNOFFICIAL derivative: Apache-2.0 compliance & provenance ---------------
# Supabase Studio is Apache-2.0. The Next standalone bundle does not carry the
# upstream LICENSE, so ship it explicitly (sec. 4a). The patch + its description
# travel with the image as the "prominent notice stating changes" (sec. 4b).
# Apache-2.0 grants no trademark rights: this image is not affiliated with,
# sponsored by, or endorsed by Supabase. Do not add the Supabase name/logo in a
# way that implies endorsement.
COPY LICENSE /usr/share/doc/multitenant-studio/LICENSE
COPY studio-project-context.patch README.md /usr/share/doc/multitenant-studio/

LABEL org.opencontainers.image.title="multitenant-studio" \
      org.opencontainers.image.description="UNOFFICIAL derivative of Supabase Studio with a per-tab project-context patch. Not affiliated with, sponsored by, or endorsed by Supabase." \
      org.opencontainers.image.source="https://github.com/GustavoMartins123/supabase-multitenant" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.revision="${SUPABASE_STUDIO_COMMIT}" \
      io.github.gustavomartins123.upstream.repository="${SUPABASE_STUDIO_REPOSITORY}" \
      io.github.gustavomartins123.upstream.commit="${SUPABASE_STUDIO_COMMIT}" \
      io.github.gustavomartins123.official="false"

COPY --from=builder /app/apps/studio/public ./apps/studio/public
COPY --from=builder /app/apps/studio/.next/standalone ./
COPY --from=builder /app/apps/studio/.next/static ./apps/studio/.next/static

EXPOSE 3000
ENTRYPOINT ["docker-entrypoint.sh"]
HEALTHCHECK --interval=5s --timeout=5s --retries=3 CMD node -e "fetch('http://localhost:3000/api/platform/profile').then((r) => {if (r.status !== 200) throw new Error(r.status)})"
CMD ["node", "apps/studio/server.js"]
