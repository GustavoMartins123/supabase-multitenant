FROM python:3.12.13-slim
COPY --from=supabase/edge-runtime:v1.77.9 /usr/local/bin/edge-runtime /usr/local/bin/edge-runtime
WORKDIR /app
COPY policy.py server.py ./
USER 65532:65532
EXPOSE 18030
CMD ["python3", "-u", "/app/server.py"]
