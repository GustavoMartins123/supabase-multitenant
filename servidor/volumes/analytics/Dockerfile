ARG ELIXIR_VERSION=1.19.5
ARG OTP_VERSION=27.3.4.6
ARG DEBIAN_VERSION=trixie-20260112-slim
ARG RUST_VERSION=1.94.1
ARG BUILDER_IMAGE="hexpm/elixir:${ELIXIR_VERSION}-erlang-${OTP_VERSION}-debian-${DEBIAN_VERSION}"
ARG RUNNER_IMAGE="debian:${DEBIAN_VERSION}"
ARG LOGFLARE_VER=v1.47.1


FROM ${BUILDER_IMAGE} AS builder

ARG RUST_VERSION
ARG LOGFLARE_VER
ENV MIX_ENV prod

WORKDIR /app

RUN apt-get update -y && apt-get install -y curl bash build-essential git gcc make ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    curl https://sh.rustup.rs -sSf | bash -s -- -y --default-toolchain ${RUST_VERSION} && \
    apt-get clean && rm -f /var/lib/apt/lists/*_*

RUN git clone --depth 1 --branch ${LOGFLARE_VER} \
      https://github.com/Logflare/logflare.git .

RUN mix do local.rebar --force + local.hex --force + deps.get + deps.compile

RUN npm --prefix assets ci

# Apply multitenant customizations before final compile so module overrides take effect
COPY volumes/analytics/dialect_translation.ex \
     lib/logflare/sql/dialect_translation.ex
COPY volumes/analytics/sql.ex \
     lib/logflare/sql.ex
COPY volumes/analytics/translation_smoke.exs \
     /tmp/analytics_translation_smoke.exs

# rust bin path and release optimizations
ENV PATH="/root/.cargo/bin:${PATH}"
ENV CARGO_PROFILE_RELEASE_LTO="thin"
ENV CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1

RUN cargo version

RUN mix run --no-start /tmp/analytics_translation_smoke.exs

RUN mix release && \
    npm run --prefix assets deploy && \
    mix phx.digest


FROM ${RUNNER_IMAGE}

RUN apt-get update -y && apt-get install -y curl libstdc++6 openssl locales \
    && apt-get clean && rm -f /var/lib/apt/lists/*_*

RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen

ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

ARG LOGFLARE_VER
ENV LOGFLARE_COMMIT_SHA=${LOGFLARE_VER}

COPY --from=builder app/_build/prod /opt/app
COPY --from=builder app/VERSION /opt/app/VERSION
COPY --from=builder app/priv/static /opt/app/rel/logflare/bin/priv/static

RUN cp -r /opt/app/rel/logflare/bin/priv/static /opt/app/rel/logflare/lib/logflare-$(cat /opt/app/VERSION)/priv/static
RUN rm -r /opt/app/rel/logflare/bin/priv

WORKDIR /opt/app/rel/logflare/bin
COPY --from=builder app/run.sh ./run.sh
CMD ["sh", "run.sh"]
