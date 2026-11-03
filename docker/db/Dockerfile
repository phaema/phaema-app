# SPDX-License-Identifier: AGPL-3.0-or-later
# PostgreSQL 17 with PostGIS, built on the official multi-architecture postgres image
# so it runs natively on Apple Silicon as well as on Intel/AMD servers.
FROM postgres:17-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*

COPY init-postgis.sql /docker-entrypoint-initdb.d/
