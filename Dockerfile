FROM node:22-alpine AS frontend

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tailwind.config.js ./
COPY watermark_app/templates ./watermark_app/templates
COPY watermark_app/static/js ./watermark_app/static/js
COPY watermark_app/static/css/tailwind.css ./watermark_app/static/css/tailwind.css
RUN npm run build:css

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /app/watermark_app/static/css/tailwind.generated.css \
    /app/watermark_app/static/css/tailwind.generated.css

EXPOSE 10000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
