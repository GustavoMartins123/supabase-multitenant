FROM nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim
ENV NGINX_ENVSUBST_OUTPUT_DIR=/tmp
ENV NGINX_ENVSUBST_FILTER=^FILE_SIZE_LIMIT$
COPY nginx/nginx_{{project_id}}.conf /etc/nginx/templates/nginx.conf.template
CMD ["nginx", "-g", "daemon off;", "-c", "/tmp/nginx.conf"]
