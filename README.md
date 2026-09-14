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

Use Python 3.11 or newer for the shipped NumPy/pyGAM models.

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
python3 -m venv .venv-nowcast  # Python 3.11+ (OVSA: /home/peijin/miniconda3/bin/python)
.venv-nowcast/bin/pip install -r requirements.txt
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
| `EPHEMERIS_URL` | `https://ovsa.njit.edu/api/ephm/info` | Radio eligibility: solar elevation ≥12° |
| `FLARE_MODEL_DIR` | `models/` | Six unchanged v0.3 occupancy GAM archives |
| `FLARECAST_DB_PATH` | `data/flarecast_record.sqlite3` | SQLite probability-record database |

## Flare probability records

The backend runs the supplied v0.3 occupancy model locally every 10 seconds,
24 hours a day, and stores `timeUT`, `R1p`, `R2p`, and `R3p` in the
`flarecast_record` SQLite table. The production systemd unit keeps the database
at `/var/lib/ovro-dashboard/flarecast_record.sqlite3` using `StateDirectory`, so
records survive application deployments and service restarts.

`GET /api/flare/history?minutes=30` returns the initial plot window. After that
one database read, each open browser appends live `/api/flare/nowcast` results
to its in-memory 30-minute series every 10 seconds.

GOES XRS-B is required in both modes. At elevations below 12°, on ephemeris
failure, or while the radio stream is unavailable, the model uses X-rays alone.
At ≥12°, the backend samples the advancing live ring buffer once per second,
converts 40/60/80 MHz flux using raw / 240000 SFU, and supplies a trailing
180-second history. Missing seconds remain NaN; values outside 1–2000 SFU
are rejected before combining frames. Startup and radio recovery use X-rays
alone until sufficient history exists. The model's rising-SXR gate decides
whether usable radio contributes to the displayed probabilities.

The GOES one-day feed supplies the required 71-minute causal history. The
model selects a lag by rounding the actual GOES delay up to 1–6 minutes.
The UI shows the active mode, a stale-prediction notice after 30 seconds,
and a delay warning when GOES exceeds the trained six-minute range. Missing
GOES history/features skip recording rather than manufacturing predictions.

See [the supplied model instructions](docs/REALTIME_NOWCAST_INSTRUCTIONS.md).
`backend/realtime_nowcast_lookup.py` is the supplied script with one status-only
correction: `used_radio` describes actual blend selection; `radio_available`
separately describes finite radio fluence. Prediction formulas and model NPZs
are unchanged. Archives are trusted model assets containing pickled GAMs;
only load files supplied by the model authors.
