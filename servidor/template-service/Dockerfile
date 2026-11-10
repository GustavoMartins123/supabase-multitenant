FROM golang:1.27.1-alpine AS engine
WORKDIR /src
COPY engine/ .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /template-engine .

FROM python:3.12.16-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=engine /template-engine /usr/local/bin/template-engine
COPY service.py policy.py legacy_migration.py .
USER 65532:65532
EXPOSE 18020
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "18020", "--no-access-log"]
