FROM python:3.12.13-slim
WORKDIR /app
COPY client-configuration/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY client-configuration/app.py ./app.py
USER 65532:65532
EXPOSE 18011
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18011", "--no-proxy-headers", "--no-server-header", "--no-access-log"]
