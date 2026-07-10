ARG ELIXIR_VERSION=1.18
ARG OTP_VERSION=27.3
ARG DEBIAN_VERSION=bookworm-20250929-slim
ARG BUILDER_IMAGE="hexpm/elixir:${ELIXIR_VERSION}-erlang-${OTP_VERSION}-debian-${DEBIAN_VERSION}"
ARG RUNNER_IMAGE="debian:${DEBIAN_VERSION}"
# @supabase/pg-delta@1.0.0-alpha.30
ARG PG_DELTA_COMMIT=d706336a6772318e92db419eda5a5ea51123510e
ARG REALTIME_VER=v2.112.3


FROM debian:${DEBIAN_VERSION} AS pgdelta-builder
ARG PG_DELTA_COMMIT
ARG BUN_VERSION=1.3.14

RUN set -eux; \
    apt-get update -y; \
    apt-get install -y --no-install-recommends curl ca-certificates unzip xz-utils; \
    curl -fsSL https://bun.sh/install | bash -s "bun-v${BUN_VERSION}"; \
    export PATH="/root/.bun/bin:${PATH}"; \
    mkdir -p /build && cd /build; \
    curl -fsSL "https://github.com/supabase/pg-toolbelt/archive/${PG_DELTA_COMMIT}.tar.gz" \
      | tar xz --strip-components=1; \
    bun install --frozen-lockfile --ignore-scripts; \
    cd /build/packages/pg-delta; \
    bun build --compile src/cli/bin/cli.ts --outfile /tmp/pgdelta; \
    /tmp/pgdelta --help > /dev/null; \
    xz -9 -e -T0 -c /tmp/pgdelta > /tmp/pgdelta.xz; \
    cd / && find build -path '*/@libpg-query/parser/wasm/libpg-query.wasm' \
      | tar -czf /tmp/libpg-query.tar.gz -T -; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -e' \
      'BIN=/app/.pgdelta-cache/pgdelta' \
      'if [ ! -x "$BIN" ]; then' \
      '  mkdir -p "$(dirname "$BIN")"' \
      '  xz -dcT0 /usr/local/share/pgdelta/pgdelta.xz > "$BIN"' \
      '  chmod +x "$BIN"' \
      'fi' \
      'exec "$BIN" "$@"' \
      > /tmp/pgdelta-wrapper; \
    chmod +x /tmp/pgdelta-wrapper; \
    rm -rf /tmp/pgdelta /build /root/.bun /var/lib/apt/lists/*


FROM ${BUILDER_IMAGE} AS builder
ENV MIX_ENV="prod"

RUN apt-get update -y \
    && apt-get install curl -y \
    && apt-get install -y build-essential git ca-certificates gnupg \
    && apt-get clean

RUN set -uex; \
    apt-get update; \
    apt-get install -y ca-certificates curl gnupg; \
    mkdir -p /etc/apt/keyrings; \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg; \
    NODE_MAJOR=24; \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list; \
    apt-get -qy update; \
    apt-get -qy install nodejs;

WORKDIR /app
ARG REALTIME_VER=v2.112.3
RUN git clone --depth 1 --branch ${REALTIME_VER} \
      https://github.com/supabase/realtime.git .

RUN mix local.hex --force && \
    mix local.rebar --force

RUN mix deps.get --only $MIX_ENV \
 && mix deps.compile

# Compile assets with esbuild and npm
RUN cd assets \
    && npm install \
    && cd .. \
    && mix assets.deploy

# Apply multitenant customizations before final compile so module overrides take effect
COPY volumes/realtime/replication_connection.ex \
     lib/realtime/tenants/replication_connection.ex
COPY volumes/realtime/metrics_controller.ex \
     lib/realtime_web/controllers/metrics_controller.ex
COPY volumes/realtime/router.ex \
     lib/realtime_web/router.ex
COPY volumes/realtime/tenant_controller_test.exs \
     test/realtime_web/controllers/tenant_controller_test.exs

RUN mix compile

RUN mix release


FROM ${RUNNER_IMAGE}
ARG SLOT_NAME_SUFFIX

ENV SLOT_NAME_SUFFIX="${SLOT_NAME_SUFFIX}" \
    LANG="en_US.UTF-8" \
    LANGUAGE="en_US:en" \
    LC_ALL="en_US.UTF-8" \
    MIX_ENV="prod" \
    ECTO_IPV6="true" \
    ERL_AFLAGS="-proto_dist inet6_tcp"

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
      libstdc++6 openssl libncurses5 locales iptables sudo tini curl awscli jq xz-utils && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=pgdelta-builder /tmp/pgdelta.xz /usr/local/share/pgdelta/pgdelta.xz
COPY --from=pgdelta-builder /tmp/pgdelta-wrapper /usr/local/bin/pgdelta
COPY --from=pgdelta-builder /tmp/libpg-query.tar.gz /tmp/libpg-query.tar.gz
RUN tar -C / -xzf /tmp/libpg-query.tar.gz && rm /tmp/libpg-query.tar.gz

# Set the locale
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen

WORKDIR "/app"

RUN chown nobody /app && mkdir -p /app/.pgdelta-cache && chown nobody /app/.pgdelta-cache

COPY --from=builder --chown=nobody:root /app/_build/${MIX_ENV}/rel/realtime ./
COPY --from=builder --chown=nobody:root /app/run.sh /app/run.sh
RUN ls -la /app
ENTRYPOINT ["/usr/bin/tini", "-s", "-g", "--", "/app/run.sh"]
CMD ["/app/bin/server"]