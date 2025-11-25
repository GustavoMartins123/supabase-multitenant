FROM python:3.12-slim
RUN apt-get update && apt-get install -y \
    jq \
    curl \
    gnupg \
    lsb-release \
    rsync \
    attr \
    acl \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
  && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
  && apt-get update \
  && apt-get install -y docker-ce-cli
WORKDIR /docker
COPY ./api-internal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./api-internal/app ./app
COPY ./secrets/ /docker/secrets/
COPY /generateProject ./scripts/
RUN chmod +x ./scripts/extract_token.sh
RUN chmod +x ./scripts/generate_project.sh
RUN chmod +x ./scripts/delete_project.sh
RUN chmod +x ./scripts/duplicate_project.sh
EXPOSE 18000        
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18000", "--proxy-headers"]
