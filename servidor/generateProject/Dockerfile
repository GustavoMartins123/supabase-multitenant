FROM nginx:1.29.6
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx
ENV NGINX_ENVSUBST_FILTER=^FILE_SIZE_LIMIT$
COPY nginx/nginx_{{project_id}}.conf /etc/nginx/templates/nginx.conf.template
