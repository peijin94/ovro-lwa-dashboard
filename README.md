# OVRO-LWA Solar Dashboard

A real-time solar activity dashboard for OVRO-LWA. The application combines the
existing live dynamic-spectrum stream with a derived 50 MHz light curve and
public NOAA GOES data.

## Dashboard panels

- OVRO-LWA 15–85 MHz rolling dynamic spectrum (300 seconds)
- 50 MHz live light curve derived from the middle spectrum channel
- NOAA GOES primary-satellite X-ray flux and current flare class
- Thirty-minute RA1/RA2/RA3 flare-probability history with 10-second live updates
- Latest NOAA GOES/SUVI 195 Å solar image
- Reserved placeholder for the future live OVRO-LWA radio-image pipeline

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
LIVE_SPECTRUM_URL=https://ovsa.njit.edu/live \
  .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 9528
```

Open `http://127.0.0.1:9528/`. For frontend hot reload, run `npm run dev` in
`frontend/`; Vite proxies `/api` to port 9528.

## Production deployment

The production frontend is built with the `/dashboard/` base path. On `ovsa`,
the FastAPI service listens only on `127.0.0.1:9528`, while Apache exposes it at
`https://ovsa.njit.edu/dashboard/`.

Install the included systemd unit, then enable and start the service:

```bash
sudo install -m 0644 deploy/ovro-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ovro-dashboard.service
```

The idempotent `deploy/install-apache-route.sh` helper backs up the active SSL
virtual host, installs the required route, validates the configuration, and only
then reloads Apache. It must be run with `sudo` on `ovsa`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LIVE_SPECTRUM_URL` | `http://127.0.0.1:9527` | Existing SunSpecStreamSys service |
| `GOES_XRAY_URL` | NOAA primary 1-day feed | GOES X-ray JSON source |
| `GOES_IMAGE_URL` | NOAA primary SUVI 195 Å image | Latest solar image source |
| `EPHEMERIS_URL` | `https://ovsa.njit.edu/api/ephm/info` | Sun-up state used by the recorder |
| `FLARE_NOWCAST_URL` | `https://ovsa.njit.edu/api/flare/nowcast` | OVRO-LWA flare nowcast API |
| `FLARECAST_DB_PATH` | `data/flarecast_record.sqlite3` | SQLite probability-record database |

## Flare probability records

While the Sun is above the OVRO horizon, the backend queries the flare nowcast
every 10 seconds and stores `timeUT`, `R1p`, `R2p`, and `R3p` in the
`flarecast_record` SQLite table. The production systemd unit keeps the database
at `/var/lib/ovro-dashboard/flarecast_record.sqlite3` using `StateDirectory`, so
records survive application deployments and service restarts.

`GET /api/flare/history?minutes=30` returns the initial plot window. After that
one database read, each open browser appends live `/api/flare/nowcast` results
to its in-memory 30-minute series every 10 seconds.
