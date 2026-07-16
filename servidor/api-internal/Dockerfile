FROM python:3.12.13-slim
WORKDIR /docker
COPY ./api-internal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./api-internal/app ./app
EXPOSE 18000
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "18000", "--proxy-headers"]
