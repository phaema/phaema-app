#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Simple control script for running PHAEMA with Docker Compose.
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  cat <<'EOF'
Usage: ./phaema.sh <command>

  start        Build (if needed) and start PHAEMA at http://localhost:8000
  stop         Stop PHAEMA (your data is kept)
  update       Download the latest code from GitHub, rebuild and restart
  admin        Create a user who can sign in and manage data
  demo-data    Load the fictional Exampleton demonstration estate
  import-inspire FILE  Import HM Land Registry INSPIRE parcels from a zip file
  reminders    Send any lease event reminders that are due now
  logs         Show live logs (press Ctrl+C to stop watching)
  status       Show whether PHAEMA is running
  backup       Save a copy of the database and uploaded files to the backups folder
  restore FILE Replace ALL data with a database backup (and its matching files backup, if any)
  prune-backups N  Keep only the newest N backups
  reset-data   DELETE all data and start with an empty database
EOF
}

compose() { docker compose "$@"; }

case "${1:-}" in
  start)
    compose up -d --build
    echo "Waiting for PHAEMA to start..."
    for _ in $(seq 1 60); do
      if curl -fs http://localhost:8000/health/ >/dev/null 2>&1; then
        echo "PHAEMA is running: open http://localhost:8000"
        exit 0
      fi
      sleep 2
    done
    echo "PHAEMA has not started yet. Check './phaema.sh logs'." ; exit 1 ;;
  stop)    compose down ;;
  update)  git pull --ff-only && "$0" start ;;
  admin)   compose exec web python manage.py createsuperuser ;;
  demo-data) compose exec web python manage.py load_demo_data "${@:2}" ;;
  import-inspire)
    [ -f "${2:-}" ] || { echo "Usage: ./phaema.sh import-inspire path/to/inspire.zip"; exit 1; }
    compose cp "$2" web:/tmp/inspire-upload
    compose exec web python manage.py import_inspire /tmp/inspire-upload ;;
  reminders) compose exec web python manage.py send_reminders "${@:2}" ;;
  logs)    compose logs -f ;;
  status)  compose ps ;;
  backup)
    mkdir -p backups
    stamp="$(date +%Y%m%d-%H%M%S)"
    file="backups/phaema-$stamp.sql.gz"
    compose exec -T db pg_dump -U phaema phaema | gzip > "$file"
    compose exec -T web tar -czf - -C /app media > "backups/media-$stamp.tar.gz"
    echo "Saved $file and backups/media-$stamp.tar.gz" ;;
  restore)
    [ -f "${2:-}" ] || { echo "Usage: ./phaema.sh restore backups/phaema-YYYYMMDD-HHMMSS.sql.gz"; exit 1; }
    read -r -p "This REPLACES ALL PHAEMA data with $2. Type RESTORE to confirm: " answer
    [ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }
    compose stop web scheduler
    compose exec -T db psql -U phaema -d postgres -q -c "DROP DATABASE IF EXISTS phaema WITH (FORCE);" -c "CREATE DATABASE phaema OWNER phaema;"
    gunzip -c "$2" | compose exec -T db psql -U phaema -d phaema -q -v ON_ERROR_STOP=1 >/dev/null
    compose start web scheduler
    media="${2/phaema-/media-}"; media="${media%.sql.gz}.tar.gz"
    if [ -f "$media" ]; then
      compose exec -T -u root web sh -c 'rm -rf /app/media/* && tar -xzf - -C /app && chown -R phaema /app/media' < "$media"
      echo "Restored $2 and $media"
    else
      echo "Restored $2 (no matching files backup found)"
    fi ;;
  prune-backups)
    keep="${2:-14}"
    ls -1t backups/phaema-*.sql.gz 2>/dev/null | tail -n +"$((keep + 1))" | xargs -r rm -f
    ls -1t backups/media-*.tar.gz 2>/dev/null | tail -n +"$((keep + 1))" | xargs -r rm -f ;;
  reset-data)
    read -r -p "This deletes ALL PHAEMA data. Type DELETE to confirm: " answer
    [ "$answer" = "DELETE" ] || { echo "Cancelled."; exit 1; }
    compose down -v && "$0" start ;;
  *) usage ;;
esac
