FROM postgres:16.13-alpine3.23


COPY init.sql /docker-entrypoint-initdb.d/
COPY entrypoint.sh /docker-entrypoint-initdb.d/


RUN chmod +x /docker-entrypoint-initdb.d/entrypoint.sh