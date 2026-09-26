# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build-time collectstatic needs Django settings; do not rely on production secrets here.
ENV SECRET_KEY=build-only-not-for-runtime \
    DEBUG=False \
    ALLOWED_HOSTS=localhost
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["bash", "-c", "python manage.py migrate --noinput && python manage.py seed_platform && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
