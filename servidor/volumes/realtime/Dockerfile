ARG ELIXIR_VERSION=1.18
ARG OTP_VERSION=27.3
ARG DEBIAN_VERSION=bookworm-20250929-slim
ARG RUST_VERSION=1.94.0
ARG BUILDER_IMAGE="hexpm/elixir:${ELIXIR_VERSION}-erlang-${OTP_VERSION}-debian-${DEBIAN_VERSION}"


FROM rust:${RUST_VERSION}-slim-bookworm AS rust-builder

RUN apt-get update -y \
    && apt-get install -y build-essential git \
    && apt-get clean

ARG REALTIME_VER=v2.78.15
RUN git clone --depth 1 --branch ${REALTIME_VER} \
      https://github.com/supabase/realtime.git /app

WORKDIR /app/native/prometheus_remote_write
RUN cargo build --release


FROM ${BUILDER_IMAGE} AS builder
ENV MIX_ENV="prod"

RUN apt-get update -y \
    && apt-get install curl -y \
    && apt-get install -y build-essential git \
    && apt-get clean

COPY --from=rust-builder /usr/local/cargo /usr/local/cargo
COPY --from=rust-builder /usr/local/rustup /usr/local/rustup
ENV PATH="/usr/local/cargo/bin:${PATH}"
ENV RUSTUP_TOOLCHAIN=stable

WORKDIR /app
ARG REALTIME_VER=v2.78.15
RUN git clone --depth 1 --branch ${REALTIME_VER} \
      https://github.com/supabase/realtime.git .

COPY --from=rust-builder \
     /app/native/prometheus_remote_write/target \
     native/prometheus_remote_write/target

COPY volumes/realtime/replication_connection.ex \
     lib/realtime/tenants/replication_connection.ex

RUN mix local.hex --force && \
    mix local.rebar --force

RUN mix deps.get --only prod \
 && mix deps.compile \
 && mix compile \
 && mix release

FROM debian:${DEBIAN_VERSION}
ENV LANG=C.UTF-8 MIX_ENV=prod

RUN apt-get update -y && apt-get install -y libstdc++6 openssl libncurses5 locales iptables sudo curl tini postgresql-client \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/_build/prod/rel/realtime ./
COPY --from=builder /app/run.sh /app/run.sh
RUN chmod +x /app/run.sh

ENTRYPOINT ["/usr/bin/tini", "-s", "-g", "--", "/app/run.sh"]
CMD ["./bin/server"]