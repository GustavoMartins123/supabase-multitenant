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
COPY --from=builder /app/apps/studio/public ./apps/studio/public
COPY --from=builder /app/apps/studio/.next/standalone ./
COPY --from=builder /app/apps/studio/.next/static ./apps/studio/.next/static

EXPOSE 3000
ENTRYPOINT ["docker-entrypoint.sh"]
HEALTHCHECK --interval=5s --timeout=5s --retries=3 CMD node -e "fetch('http://localhost:3000/api/platform/profile').then((r) => {if (r.status !== 200) throw new Error(r.status)})"
CMD ["node", "apps/studio/server.js"]
