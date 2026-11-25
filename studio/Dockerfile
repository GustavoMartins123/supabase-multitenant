ARG AUTHELIA_IMAGE=authelia/authelia:4.39.20

FROM ghcr.io/cirruslabs/flutter:3.44.0 AS builder

WORKDIR /app

COPY projects_api_client/ ../projects_api_client/
COPY seletor_de_projetos/pubspec.* ./

RUN flutter pub get

COPY seletor_de_projetos/ .

RUN flutter build web --release

FROM ${AUTHELIA_IMAGE} AS authelia-cli

FROM openresty/openresty:1.31.9.1-noble


RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libssl-dev \
        libyaml-dev \
        libargon2-1 \
        libargon2-dev \
        argon2 \
        openssl \
        git \
        libvips-tools \
        luarocks \
    && rm -rf /var/lib/apt/lists/*

RUN luarocks install https://luarocks.org/manifests/hisham/luafilesystem-1.8.0-1.rockspec
COPY lyaml-6.2.8-1.src /tmp/lyaml-6.2.8-1.src
RUN cd /tmp/lyaml-6.2.8-1.src && \
    luarocks install lyaml-6.2.8-1.rockspec && \
    rm -rf /tmp/lyaml-6.2.8-1.src

RUN luarocks install https://luarocks.org/manifests/fffonion/lua-resty-openssl-1.7.1-1.rockspec \
    && (timeout 20 opm get ledgetech/lua-resty-http=0.17.1 \
        || (curl -fsSL https://github.com/ledgetech/lua-resty-http/archive/refs/tags/v0.17.1.tar.gz -o /tmp/lua-resty-http-0.17.1.tar.gz \
            && echo "f52a0538b20a2d45025f318c18a138b78f6f88f07713dd0ed502183cb3d16f17  /tmp/lua-resty-http-0.17.1.tar.gz" | sha256sum -c - \
            && tar -xzf /tmp/lua-resty-http-0.17.1.tar.gz -C /tmp \
            && mkdir -p /usr/local/openresty/site/lualib/resty \
            && cp /tmp/lua-resty-http-0.17.1/lib/resty/*.lua /usr/local/openresty/site/lualib/resty/ \
            && rm -rf /tmp/lua-resty-http-0.17.1 /tmp/lua-resty-http-0.17.1.tar.gz)) \
    && /usr/local/openresty/bin/resty -e 'local http = require("resty.http"); assert(type(http.new) == "function")'

COPY --from=authelia-cli /app/authelia /usr/local/bin/authelia

COPY nginx/nginx.conf /usr/local/openresty/nginx/conf/nginx.conf
COPY nginx/lua/ /usr/local/openresty/lualib/
COPY --from=builder /app/build/web /usr/share/nginx/html
COPY nginx/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN command -v argon2 >/dev/null
RUN ldconfig -p | grep -q libargon2

EXPOSE 443
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
