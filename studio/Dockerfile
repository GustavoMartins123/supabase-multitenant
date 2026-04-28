FROM ghcr.io/cirruslabs/flutter:3.41.5 AS builder

WORKDIR /app

COPY seletor_de_projetos/pubspec.* ./

RUN flutter pub get

COPY seletor_de_projetos/ .

RUN flutter build web --release

FROM authelia/authelia:4.39 AS authelia-cli

FROM openresty/openresty:1.29.2.3-4-bookworm-fat


RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libssl-dev \
        libyaml-dev \
        argon2 \
        openssl \
        git \
        inotify-tools \
        luarocks \
    && rm -rf /var/lib/apt/lists/*

RUN luarocks install https://luarocks.org/manifests/hisham/luafilesystem-1.8.0-1.rockspec
COPY lyaml-6.2.8-1.src /tmp/lyaml-6.2.8-1.src
RUN cd /tmp/lyaml-6.2.8-1.src && \
    luarocks install lyaml-6.2.8-1.rockspec

RUN luarocks install https://luarocks.org/manifests/fffonion/lua-resty-openssl-1.7.1-1.rockspec \
&& opm get jkeys089/lua-resty-hmac \
 && opm get ledgetech/lua-resty-http

RUN luarocks install https://luarocks.org/manifests/rsander/lua-resty-string-0.09-0.rockspec \
    && luarocks install https://luarocks.org/manifests/erento/lua-erento-hmac-1.0-0.rockspec \
    && luarocks install https://luarocks.org/manifests/megalord/lua-resty-fernet-1.0-0.rockspec \
    && luarocks install https://luarocks.org/manifests/moorefu/lua-resty-crypto-master-0.rockspec \
    && luarocks install https://luarocks.org/manifests/daurnimator/luaossl-20250929-0.rockspec \
    && luarocks install https://luarocks.org/manifests/leafo/pgmoon-1.16.0-1.rockspec

COPY --from=authelia-cli /app/authelia /usr/local/bin/authelia

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/lua/ /usr/local/openresty/lualib/
COPY --from=builder /app/build/web /usr/share/nginx/html
COPY nginx/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN which argon2 && argon2 -h || echo "argon2 installation check failed"

EXPOSE 4000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
