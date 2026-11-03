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
  logs         Show live logs (press Ctrl+C to stop watching)
  status       Show whether PHAEMA is running
  backup       Save a copy of the database to the backups folder
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
  logs)    compose logs -f ;;
  status)  compose ps ;;
  backup)
    mkdir -p backups
    file="backups/phaema-$(date +%Y%m%d-%H%M%S).sql.gz"
    compose exec -T db pg_dump -U phaema phaema | gzip > "$file"
    echo "Saved $file" ;;
  reset-data)
    read -r -p "This deletes ALL PHAEMA data. Type DELETE to confirm: " answer
    [ "$answer" = "DELETE" ] || { echo "Cancelled."; exit 1; }
    compose down -v && "$0" start ;;
  *) usage ;;
esac
