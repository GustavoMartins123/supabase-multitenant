ARG ELIXIR_VERSION=1.17.3
ARG OTP_VERSION=27.1.2
ARG DEBIAN_VERSION=bookworm-20241111-slim
ARG BUILDER_IMAGE="hexpm/elixir:${ELIXIR_VERSION}-erlang-${OTP_VERSION}-debian-${DEBIAN_VERSION}"

FROM ${BUILDER_IMAGE} AS builder
ENV MIX_ENV="prod"

RUN apt-get update -y \
    && apt-get install curl -y \
    && apt-get install -y build-essential git \
    && apt-get clean

WORKDIR /app
ARG REALTIME_VER=v2.34.46
RUN git clone --depth 1 --branch ${REALTIME_VER} \
      https://github.com/supabase/realtime.git .

COPY volumes/realtime/replication_connection.ex \
     lib/realtime/tenants/replication_connection.ex

RUN mix local.hex --force && \
    mix local.rebar --force

RUN mix deps.get --only prod \
 && mix deps.compile \
 && mix compile \
 && mix release

FROM debian:bookworm-20241111-slim
ENV LANG=C.UTF-8 MIX_ENV=prod

RUN apt-get update -y && apt-get install -y libstdc++6 openssl libncurses5 locales iptables sudo curl tini postgresql-client \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/_build/prod/rel/realtime ./
COPY --from=builder /app/run.sh /app/run.sh
RUN chmod +x /app/run.sh

ENTRYPOINT ["/usr/bin/tini", "-s", "-g", "--", "/app/run.sh"]
CMD ["./bin/server"]