FROM nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim
COPY --chown=101:101 --chmod=0400 \
  nginx/nginx_{{project_id}}.conf /etc/nginx/nginx.conf.template
USER 101
ENTRYPOINT ["/bin/sh", "-c"]
CMD ["envsubst '$FILE_SIZE_LIMIT' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf && exec nginx -g 'daemon off;' -c /tmp/nginx.conf"]
