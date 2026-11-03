# SPDX-License-Identifier: AGPL-3.0-or-later
# PHAEMA application image. Builds natively on Apple Silicon (arm64) and on Intel/AMD servers.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home phaema && mkdir -p /app/media /app/staticfiles && chown -R phaema /app
USER phaema

RUN SECRET_KEY=build python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn phaema.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 300"]
