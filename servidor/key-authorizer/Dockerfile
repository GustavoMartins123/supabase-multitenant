FROM python:3.12.13-slim

WORKDIR /app
COPY ./key-authorizer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ./api-internal/app/opaque_keys.py ./opaque_keys.py
COPY ./key-authorizer/app.py ./app.py

USER 65532:65532
EXPOSE 18010
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18010", "--proxy-headers", "--no-server-header"]
