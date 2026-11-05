#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Installs PHAEMA on a fresh Ubuntu 24.04 server (for example an IONOS, OVHcloud or Hetzner VPS) with
# automatic HTTPS, a firewall, automatic security updates and daily backups.
#
# Run as root on the server, once its domain name already points at it:
#   curl -fsSL https://raw.githubusercontent.com/phaema/phaema-app/main/deploy/install-server.sh -o install-server.sh
#   bash install-server.sh demo.phaema.co.uk --demo
#
# Add --demo to load the fictional demonstration data (for a test site only, never with real data).
# Running it again is safe: it updates the code and keeps the data and settings.
set -euo pipefail

DOMAIN=""; DEMO=0
for arg in "$@"; do
  case "$arg" in
    --demo) DEMO=1 ;;
    -*) echo "Unknown option $arg"; exit 1 ;;
    *) DOMAIN="$arg" ;;
  esac
done
[ -n "$DOMAIN" ] || { echo "Usage: bash install-server.sh DOMAIN [--demo]"; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "Run this as root (or with sudo)."; exit 1; }
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || echo "Warning: written for Ubuntu 24.04; this is ${PRETTY_NAME:-unknown}."

APP_DIR=/opt/phaema
REPO=https://github.com/phaema/phaema-app.git
step() { printf '\n==> %s\n' "$*"; }
export DEBIAN_FRONTEND=noninteractive

step "Checking that $DOMAIN points at this server"
MY_IP=$(curl -fs4 https://api.ipify.org || true)
DNS_IP=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)
if [ -n "$MY_IP" ] && [ "$MY_IP" != "$DNS_IP" ]; then
  echo "  $DOMAIN points to '${DNS_IP:-nothing}', but this server is $MY_IP."
  echo "  Add or correct the A record, wait a few minutes, then run this again."
  echo "  (Without it, the HTTPS certificate cannot be issued.)"
  exit 1
fi
echo "  OK: $DOMAIN -> ${DNS_IP:-unknown}"

step "Updating the system and turning on automatic security updates"
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw fail2ban unattended-upgrades
dpkg-reconfigure -fnoninteractive unattended-upgrades

step "Firewall: allowing SSH, HTTP and HTTPS only"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443 >/dev/null
ufw --force enable >/dev/null
systemctl enable --now fail2ban >/dev/null

MEM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 6000 ] && ! swapon --show | grep -q .; then
  step "Adding 2 GB of swap space (this server has ${MEM_MB} MB of memory)"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if ! command -v docker >/dev/null; then
  step "Installing Docker"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker >/dev/null

step "Getting the PHAEMA code"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

if [ ! -f .env ]; then
  step "Writing the settings file (.env) with new random secrets"
  rand() { tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1"; }
  cat > .env <<EOF
# PHAEMA server settings. Keep this file private: it holds the database password and secret key.
COMPOSE_FILE=docker-compose.yml:docker-compose.server.yml
PHAEMA_DOMAIN=$DOMAIN
PHAEMA_BASE_URL=https://$DOMAIN
ALLOWED_HOSTS=$DOMAIN,localhost,127.0.0.1
BEHIND_HTTPS_PROXY=True
SECURE_COOKIES=True
DEBUG=False
SECRET_KEY=$(rand 60)
DB_PASSWORD=$(rand 32)
PHAEMA_ORGANISATION_NAME=Demonstration District Council
# Email for reminders (optional). Fill these in, then run: ./phaema.sh start
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=PHAEMA <phaema@$DOMAIN>
EOF
  chmod 600 .env
else
  echo "  Keeping the existing .env settings."
fi
if [ "$DEMO" -eq 1 ] && ! grep -q '^PHAEMA_DEMO_SITE=' .env; then
  printf '%s\n' "# A public test site with fictional data, reset every PHAEMA_DEMO_RESET_HOURS hours." \
    "PHAEMA_DEMO_SITE=True" "PHAEMA_DEMO_RESET_HOURS=48" >> .env
fi

step "Building and starting PHAEMA (the first build takes a few minutes)"
./phaema.sh start

if [ "$DEMO" -eq 1 ]; then
  step "Loading the fictional demonstration data, and resetting it every 48 hours"
  if [ ! -f backups/.last-demo-reset ]; then
    ./phaema.sh demo-data
    mkdir -p backups && touch backups/.last-demo-reset
  fi
  echo "# Checks at 03:00 each night; resets once PHAEMA_DEMO_RESET_HOURS (in .env) have passed." > /etc/cron.d/phaema-demo-reset
  echo "0 3 * * * root cd $APP_DIR && ./phaema.sh reset-demo --if-due >> /var/log/phaema-demo-reset.log 2>&1" >> /etc/cron.d/phaema-demo-reset
  chmod 644 /etc/cron.d/phaema-demo-reset
fi

step "Daily backups at 02:30, keeping the last 14"
cat > /etc/cron.d/phaema-backup <<EOF
30 2 * * * root cd $APP_DIR && ./phaema.sh backup >/dev/null 2>&1 && ./phaema.sh prune-backups 14 >/dev/null 2>&1
EOF
chmod 644 /etc/cron.d/phaema-backup

step "Checking the public address"
for _ in $(seq 1 30); do
  if curl -fs "https://$DOMAIN/health/" >/dev/null 2>&1; then
    echo "  PHAEMA is live at https://$DOMAIN"
    break
  fi
  sleep 5
done
curl -fs "https://$DOMAIN/health/" >/dev/null 2>&1 || \
  echo "  Not answering over HTTPS yet. Wait a minute, then check: cd $APP_DIR && ./phaema.sh logs"

cat <<EOF

Done. Next steps:
  1. Create your administrator sign-in:   cd $APP_DIR && ./phaema.sh admin
  2. Sign in at https://$DOMAIN and add accounts for testers under Manage data, Users.
  3. To update later:                     cd $APP_DIR && ./phaema.sh update
Backups are saved in $APP_DIR/backups. Copy them off the server from time to time.
EOF
