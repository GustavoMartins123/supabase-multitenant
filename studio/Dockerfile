FROM debian:latest AS builder

    # Instala dependências do Flutter
RUN apt-get update && apt-get install -y \
        curl git wget unzip libgconf-2-4 gdb libstdc++6 libglu1-mesa fonts-droid-fallback python3 \
        && apt-get clean
    
    # Baixa Flutter SDK via git
RUN git clone https://github.com/flutter/flutter.git /usr/local/flutter
    
    # Ajusta PATH
ENV PATH="${PATH}:/usr/local/flutter/bin:/usr/local/flutter/bin/cache/dart-sdk/bin"
    
    # Verifica o Flutter e configura canal
RUN flutter doctor && \
    flutter channel stable && \
    flutter upgrade && \
    flutter config --enable-web

WORKDIR /app
COPY ["seletor_de_projetos", "."]
RUN flutter pub get
RUN flutter build web --release

# -------- stage 2: runtime OpenResty (nginx + lua)
# FROM openresty/openresty:1.21.4.1-0-alpine
FROM openresty/openresty:1.27.1.2-1-alpine-fat AS runtime


RUN apk add --no-cache build-base curl openssl-dev yaml-dev argon2 openssl
RUN opm get xiaocang/lua-resty-openssl \
 && opm get jkeys089/lua-resty-hmac \
 && opm get ledgetech/lua-resty-http \
 && luarocks install lua-resty-fernet \
 && luarocks install luafilesystem \
 && luarocks install lyaml


FROM runtime


# copia config + build pronto
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/lua/get_service_key.lua /usr/local/openresty/lualib/ 
COPY --from=builder /app/build/web /usr/share/nginx/html
# CMD ["openresty", "-g", "daemon off;"]
COPY nginx/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN which argon2 && argon2 -h || echo "argon2 installation check failed"

EXPOSE 4000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
    
