FROM ghcr.io/cirruslabs/flutter:3.35.1 AS builder

WORKDIR /app

COPY seletor_de_projetos/pubspec.* ./

RUN flutter pub get

COPY seletor_de_projetos/ .

RUN flutter build web --release

FROM openresty/openresty:1.27.1.2-1-alpine-fat


RUN apk add --no-cache build-base curl openssl-dev yaml-dev argon2 openssl git

RUN luarocks install https://luarocks.org/manifests/hisham/luafilesystem-1.8.0-1.rockspec
COPY lyaml-6.2.8-1.src /tmp/lyaml-6.2.8-1.src
RUN cd /tmp/lyaml-6.2.8-1.src && \
    luarocks install lyaml-6.2.8-1.rockspec

RUN opm get xiaocang/lua-resty-openssl \
&& opm get jkeys089/lua-resty-hmac \
 && opm get ledgetech/lua-resty-http

RUN luarocks install https://luarocks.org/manifests/rsander/lua-resty-string-0.09-0.rockspec \
    && luarocks install https://luarocks.org/manifests/erento/lua-erento-hmac-1.0-0.rockspec \
    && luarocks install https://luarocks.org/manifests/megalord/lua-resty-fernet-1.0-0.rockspec \
    && luarocks install https://luarocks.org/manifests/moorefu/lua-resty-crypto-master-0.rockspec


COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/lua/get_service_key.lua /usr/local/openresty/lualib/ 
COPY --from=builder /app/build/web /usr/share/nginx/html
COPY nginx/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN which argon2 && argon2 -h || echo "argon2 installation check failed"

EXPOSE 4000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
    
