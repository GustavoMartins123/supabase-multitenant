FROM docker:29.3.1-cli AS docker_cli
FROM servidor-projects-api:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash jq openssl curl tar gzip util-linux coreutils ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=docker_cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker_cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY --from=docker_cli /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx
RUN pip install --no-cache-dir PyYAML==6.0.3
ENTRYPOINT ["sleep", "infinity"]
