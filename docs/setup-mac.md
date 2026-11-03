# Running PHAEMA on a Mac

These steps work on Apple Silicon (M1, M2, M3, M4) and Intel Macs. You only do steps 1 to 3 once.

## 1. Install the tools

Open the **Terminal** app and install Homebrew from https://brew.sh if you don't have it. Then run:

```
brew install git colima docker docker-compose
mkdir -p ~/.docker/cli-plugins
ln -sfn "$(brew --prefix)/opt/docker-compose/bin/docker-compose" ~/.docker/cli-plugins/docker-compose
```

The last two lines let you type `docker compose` (with a space), which the PHAEMA script uses.

## 2. Start Colima

Colima runs the containers. On Apple Silicon:

```
colima start --vm-type vz --vz-rosetta --cpu 4 --memory 6
```

After restarting your Mac you only need `colima start`.

## 3. Download PHAEMA

```
cd ~
git clone https://github.com/phaema/phaema-app.git
cd phaema-app
```

## 4. Start PHAEMA

```
./phaema.sh start
```

The first start takes several minutes while it builds. When it says PHAEMA is running, create your sign-in:

```
./phaema.sh admin
```

Choose a username and a password of at least 12 characters. Then open **http://localhost:8000** in your browser and sign in.

To try PHAEMA with example records, load the demonstration estate of the fictional Exampleton (Demonstration District Council):

```
./phaema.sh demo-data
```

Everything in it is invented: ZZ99 postcodes, 9999… UPRNs and ZZ title numbers. Run it again at any time to refresh the demo records, or `./phaema.sh demo-data --reset` to remove and reload them. Your own records are never touched.

To give other people access, use **Manage data > Users > Add user** and choose their role: Administrators, Surveyors or Viewers. See [users and roles](roles.md).

To enter data, use **Manage data** in the menu. Start by switching on the modules you want under *Module settings*.

## Everyday commands

Run these from the `phaema-app` folder (`cd ~/phaema-app`):

| Command | What it does |
|---|---|
| `./phaema.sh start` | Start PHAEMA |
| `./phaema.sh stop` | Stop PHAEMA (data is kept) |
| `./phaema.sh update` | Get the latest version from GitHub and restart |
| `./phaema.sh demo-data` | Load or refresh the demonstration estate |
| `./phaema.sh import-inspire ~/Downloads/file.zip` | Import HM Land Registry INSPIRE parcels from a downloaded zip |
| `./phaema.sh backup` | Save a copy of the database in the `backups` folder |
| `./phaema.sh logs` | Show what PHAEMA is doing (Ctrl+C to stop watching) |

## If something goes wrong

- **"Cannot connect to the Docker daemon"**: run `colima start`.
- **Downloads fail with "EOF" or time out**: restart Colima with public DNS: `colima stop` then `colima start --dns 1.1.1.1 --dns 8.8.8.8`.
- **"docker: 'compose' is not a docker command"**: repeat the last two lines of step 1.
- **Port 8000 is already in use**: stop the other program, or change `127.0.0.1:8000:8000` to `127.0.0.1:8001:8000` in `docker-compose.yml` and use http://localhost:8001.

## Keeping data safe

PHAEMA on your Mac is reachable only from your Mac. Turn on FileVault and keep Time Machine running, and use `./phaema.sh backup` before updates. Do not load real tenant personal data until the council has agreed how it will be protected.

## Reminder emails

A background service checks every hour for stepped rents that take effect and lease event reminders that are due. Until an email server is set, reminders are written to the log instead of being sent: see them with `./phaema.sh logs`. To send real emails, copy `.env.example` to `.env`, fill in the `EMAIL_` settings (for example your council's or IONOS's SMTP details) and run `./phaema.sh start` again. Reminder lead times are set in **Manage data > Module settings**.

## Maps

Maps use OpenStreetMap by default. To use Ordnance Survey mapping, get a free OS Maps API key from the OS Data Hub (councils have free access under the Public Sector Geospatial Agreement), then enter it in **Manage data > Module settings**. Users can then switch between the two under each map.
