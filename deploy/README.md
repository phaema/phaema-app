# Installing PHAEMA on a server

These steps put PHAEMA on the internet with HTTPS, on any VPS running Ubuntu 24.04 (for example IONOS,
OVHcloud or Hetzner). A server with 2 cores and 4 GB of memory is enough for a test site.

## Before you start

1. **Server**: Ubuntu 24.04, with SSH access as root (or a user who can use `sudo`).
2. **Firewall** in the provider's control panel: allow ports 22, 80 and 443.
3. **DNS**: an A record for your chosen name (for example `demo.phaema.co.uk`) pointing at the server's IP
   address. Check from your own computer that `dig +short demo.phaema.co.uk` returns that address.

## Install

Connect to the server (`ssh root@YOUR-SERVER-IP`) and run:

```
curl -fsSL https://raw.githubusercontent.com/phaema/phaema-app/main/deploy/install-server.sh -o install-server.sh
bash install-server.sh demo.phaema.co.uk --demo
```

Leave out `--demo` on a server for real data: it loads the fictional demonstration estate.

The script:

- checks that the domain points at the server;
- installs security updates and turns on automatic updates, the firewall (ufw) and fail2ban;
- adds swap space on servers with less than 6 GB of memory;
- installs Docker and gets the PHAEMA code into `/opt/phaema`;
- writes `/opt/phaema/.env` with a new random database password and secret key (keep this file private);
- builds and starts PHAEMA, with Caddy in front getting a free Let's Encrypt certificate and renewing it;
- sets up a backup every night at 02:30, keeping 14 days.

Then create your administrator sign-in and open the site:

```
cd /opt/phaema
./phaema.sh admin
```

Add testers under **Manage data**, **Users**. Give each their own account and access areas.

## Running it

All commands are run in `/opt/phaema`:

| Task | Command |
|---|---|
| Update to the latest version | `./phaema.sh update` |
| See whether it is running | `./phaema.sh status` |
| Watch the logs | `./phaema.sh logs` |
| Back up now | `./phaema.sh backup` |
| Restore a backup | `./phaema.sh restore backups/phaema-YYYYMMDD-HHMMSS.sql.gz` |
| Reload the demonstration data | `./phaema.sh demo-data --reset` |
| Reset a test site now | `./phaema.sh reset-demo` |

Backups are in `/opt/phaema/backups`: a database file and a matching files archive for each night. Copy them
off the server regularly, for example with `scp root@YOUR-SERVER-IP:/opt/phaema/backups/* .` from your own
computer. To move to a new server, install there, copy a backup across, and restore it.

## Test sites: resetting every 48 hours

Installing with `--demo` marks the server as a public test site (`PHAEMA_DEMO_SITE=True` in `.env`). Every
page then tells testers that the data is fictional and reset every 48 hours, and a nightly job at 03:00 resets
it once 48 hours have passed. A reset backs up first, wipes everything (including anything testers added),
reloads the demonstration data with today's dates, and puts back every sign-in that is not a demonstration
person, with its password, role and access areas. Change the interval with `PHAEMA_DEMO_RESET_HOURS` in `.env`.
The log is in `/var/log/phaema-demo-reset.log`. Never set `PHAEMA_DEMO_SITE` on a server with real data.

## Email (optional)

To send reminders, fill in the `EMAIL_` settings in `/opt/phaema/.env` with the council's mail server or a
mail service, then run `./phaema.sh start`.
