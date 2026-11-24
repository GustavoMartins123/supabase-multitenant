FROM python:3.12.13-slim
COPY --from=ghcr.io/gustavomartins123/supabase-edge-runtime-custom:v1.79.5-wsfix /usr/local/bin/edge-runtime /usr/local/bin/edge-runtime
WORKDIR /app
COPY policy.py server.py ./
USER 65532:65532
EXPOSE 18030
CMD ["python3", "-u", "/app/server.py"]
