# OVRO-LWA Solar Dashboard

A real-time solar activity dashboard for OVRO-LWA. The application combines the
existing live dynamic-spectrum stream with a derived 50 MHz light curve and
public NOAA GOES data.

## Dashboard panels

- OVRO-LWA 15–85 MHz rolling dynamic spectrum (300 seconds)
- 50 MHz live light curve derived from the middle spectrum channel
- NOAA GOES primary-satellite X-ray flux and current flare class
- Latest NOAA GOES/SUVI 195 Å solar image
- Reserved placeholder for the future live OVRO-LWA image pipeline
- Current OVRO-LWA Type III detection status

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

```apache
ProxyPass        /dashboard/ http://127.0.0.1:9528/
ProxyPassReverse /dashboard/ http://127.0.0.1:9528/
<Location /dashboard/>
    Require all granted
    ProxyPreserveHost On
</Location>
```

Start or restart the app in its `tmux` session:

```bash
tmux new-session -d -s dashboard \
  'cd /home/peijin/ovro-lwa-dashboard && exec .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 9528'
```

The idempotent `deploy/install-apache-route.sh` helper backs up the active SSL
virtual host, adds the proxy block above, validates the configuration, and only
then reloads Apache. It must be run with `sudo` on `ovsa`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LIVE_SPECTRUM_URL` | `http://127.0.0.1:9527` | Existing SunSpecStreamSys service |
| `GOES_XRAY_URL` | NOAA primary 1-day feed | GOES X-ray JSON source |
| `GOES_IMAGE_URL` | NOAA primary SUVI 195 Å image | Latest solar image source |
