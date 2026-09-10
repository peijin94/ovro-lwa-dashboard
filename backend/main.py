"""FastAPI server for the OVRO-LWA real-time dashboard."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.flare_records import FlareRecordStore


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = ROOT / "frontend" / "dist"
LIVE_SPECTRUM_URL = os.environ.get(
    "LIVE_SPECTRUM_URL", "http://127.0.0.1:9527"
).rstrip("/")
GOES_XRAY_URL = os.environ.get(
    "GOES_XRAY_URL",
    "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
)
GOES_IMAGE_URL = os.environ.get(
    "GOES_IMAGE_URL",
    "https://services.swpc.noaa.gov/images/animations/suvi/primary/195/latest.png",
)
EPHEMERIS_URL = os.environ.get(
    "EPHEMERIS_URL", "https://ovsa.njit.edu/api/ephm/info"
)
FLARE_NOWCAST_URL = os.environ.get(
    "FLARE_NOWCAST_URL", "https://ovsa.njit.edu/api/flare/nowcast"
)
STREAM_JY_PER_SFU = 10_000 * 24
RADIO_CHANNELS = {40: 268, 60: 476, 80: 685}
FLARE_RECORD_INTERVAL_SECONDS = 10.0
FLARECAST_DB_PATH = Path(
    os.environ.get(
        "FLARECAST_DB_PATH", ROOT / "data" / "flarecast_record.sqlite3"
    )
)

logger = logging.getLogger(__name__)
flare_record_store = FlareRecordStore(FLARECAST_DB_PATH)


async def _run_blocking(function: Any, *args: Any) -> Any:
    """Run SQLite work without requiring Python 3.9's asyncio.to_thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(function, *args))


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _run_blocking(flare_record_store.initialize)
    recorder = asyncio.create_task(_flare_recording_loop())
    try:
        yield
    finally:
        recorder.cancel()
        with suppress(asyncio.CancelledError):
            await recorder

app = FastAPI(
    title="OVRO-LWA Solar Dashboard",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

if (FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

_goes_cache: Dict[str, Any] = {"expires": 0.0, "payload": None}
_latest_flare_nowcast: Optional[Dict[str, Any]] = None
_image_cache: Dict[str, Any] = {
    "expires": 0.0,
    "content": None,
    "content_type": "image/png",
}
_goes_lock = asyncio.Lock()
_image_lock = asyncio.Lock()


async def _get_json(url: str, *, timeout: float = 10.0) -> Any:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Upstream data source unavailable: {type(exc).__name__}"
        ) from exc


async def _get_text(url: str, *, timeout: float = 10.0) -> str:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Upstream data source unavailable: {type(exc).__name__}"
        ) from exc


async def _post_json(
    url: str, payload: Dict[str, Any], *, timeout: float = 10.0
) -> Any:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), follow_redirects=True
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Upstream data source unavailable: {type(exc).__name__}"
        ) from exc


def _parse_ephemeris_info(raw: str) -> Dict[str, Any]:
    def required_float(field: str) -> float:
        match = re.search(rf"(?:^|\s){field}=([+-]?\d+(?:\.\d+)?)deg(?:\s|$)", raw)
        if not match:
            raise ValueError(f"Missing ephemeris field: {field}")
        return float(match.group(1))

    def optional_field(field: str) -> Optional[str]:
        match = re.search(rf"(?:^|\s){field}=([^\s]+)", raw)
        return match.group(1) if match else None

    sun_up = optional_field("sunup")
    return {
        "elevation_deg": required_float("alt"),
        "azimuth_deg": required_float("az"),
        "sun_up": sun_up == "1" if sun_up is not None else None,
        "sunrise": optional_field("sunrise"),
        "sunset": optional_field("sunset"),
        "updated": optional_field("time"),
    }


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    """Report dashboard and live-spectrum service health."""
    try:
        frame = await _get_json(f"{LIVE_SPECTRUM_URL}/data", timeout=3.0)
        live_ok = isinstance(frame, list) and len(frame) == 768
    except HTTPException:
        live_ok = False
    return {
        "status": "ok" if live_ok else "degraded",
        "live_spectrum": live_ok,
        "spectrum_channels": len(frame) if live_ok else 0,
        "timestamp": time.time(),
    }


@app.get("/api/spectrum/latest")
async def spectrum_latest() -> JSONResponse:
    """Return the latest 768-channel Stokes-I frame."""
    payload = await _get_json(f"{LIVE_SPECTRUM_URL}/data", timeout=5.0)
    if not isinstance(payload, list):
        raise HTTPException(status_code=502, detail="Invalid live spectrum response")
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/spectrum/history")
async def spectrum_history(
    n_frames: int = Query(default=600, ge=1, le=600),
) -> JSONResponse:
    """Return the rolling live-spectrum buffer."""
    payload = await _get_json(
        f"{LIVE_SPECTRUM_URL}/refresh?n_frames={n_frames}", timeout=15.0
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise HTTPException(status_code=502, detail="Invalid spectrum history response")
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/events")
async def events() -> JSONResponse:
    """Return current burst detections from SunSpecStreamSys."""
    payload = await _get_json(f"{LIVE_SPECTRUM_URL}/type3detect", timeout=5.0)
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


def _radio_flux3ch(frame: List[Any]) -> List[float]:
    if len(frame) <= max(RADIO_CHANNELS.values()):
        raise ValueError("Spectrum frame does not contain the required channels")

    fluxes = []
    for frequency in (40, 60, 80):
        value = frame[RADIO_CHANNELS[frequency]]
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Invalid {frequency} MHz spectrum value")
        fluxes.append(float(value) / STREAM_JY_PER_SFU)
    return fluxes


def _probabilities_from_nowcast(payload: Dict[str, Any]) -> tuple[float, float, float]:
    probabilities: List[float] = []
    probability_map = payload.get("probability")
    for class_name in (">M1", ">M5", ">X1"):
        class_payload = payload.get(class_name)
        value = class_payload.get("probability") if isinstance(class_payload, dict) else None
        if value is None and isinstance(probability_map, dict):
            value = probability_map.get(class_name)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Missing probability for {class_name}")
        probability = float(value)
        if probability < 0 or probability > 1:
            raise ValueError(f"Invalid probability for {class_name}")
        probabilities.append(probability)
    return probabilities[0], probabilities[1], probabilities[2]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


async def _fetch_current_flare_nowcast() -> Dict[str, Any]:
    frame = await _get_json(f"{LIVE_SPECTRUM_URL}/data", timeout=5.0)
    if not isinstance(frame, list):
        raise HTTPException(status_code=502, detail="Invalid live spectrum response")
    try:
        flux3ch = _radio_flux3ch(frame)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = await _post_json(
        FLARE_NOWCAST_URL, {"flux3ch": flux3ch}, timeout=15.0
    )
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Invalid flare nowcast response")
    return payload


@app.get("/api/flare/nowcast")
async def flare_nowcast() -> JSONResponse:
    """Return the recorder's latest nowcast without reading SQLite."""
    payload = _latest_flare_nowcast
    if payload is None:
        current = await _fetch_current_flare_nowcast()
        payload = {**current, "recorded_at": _utc_now_text()}
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/flare/history")
async def flare_history(
    minutes: int = Query(default=30, ge=1, le=1440),
) -> JSONResponse:
    """Return persisted flare probabilities for the requested trailing window."""
    try:
        await _run_blocking(flare_record_store.initialize)
        points = await _run_blocking(flare_record_store.recent, minutes)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="Flare history unavailable") from exc
    return JSONResponse(
        {"points": points, "window_minutes": minutes},
        headers={"Cache-Control": "no-store"},
    )


async def _record_current_flare_probability() -> bool:
    global _latest_flare_nowcast

    raw_ephemeris = await _get_text(EPHEMERIS_URL, timeout=5.0)
    try:
        ephemeris_payload = _parse_ephemeris_info(raw_ephemeris)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid ephemeris response") from exc
    if ephemeris_payload["elevation_deg"] <= 0:
        return False

    payload = await _fetch_current_flare_nowcast()
    try:
        r1p, r2p, r3p = _probabilities_from_nowcast(payload)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid flare nowcast response") from exc
    recorded_at = _utc_now_text()
    await _run_blocking(
        flare_record_store.append,
        recorded_at,
        r1p,
        r2p,
        r3p,
    )
    _latest_flare_nowcast = {**payload, "recorded_at": recorded_at}
    return True


async def _flare_recording_loop() -> None:
    while True:
        cycle_started = time.monotonic()
        try:
            await _record_current_flare_probability()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # keep the long-running recorder alive
            logger.warning("Flare probability recording cycle failed: %s", exc)
        elapsed = time.monotonic() - cycle_started
        await asyncio.sleep(max(0.0, FLARE_RECORD_INTERVAL_SECONDS - elapsed))


@app.get("/api/ephemeris")
async def ephemeris() -> JSONResponse:
    """Return normalized OVRO Sun position from the shared ephemeris API."""
    raw = await _get_text(EPHEMERIS_URL, timeout=5.0)
    try:
        payload = _parse_ephemeris_info(raw)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid ephemeris response") from exc
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


def _format_goes_payload(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_time: Dict[str, Dict[str, Any]] = {}
    satellite: Optional[int] = None

    for record in records:
        time_tag = record.get("time_tag")
        energy = record.get("energy")
        flux = record.get("flux")
        if not isinstance(time_tag, str) or not isinstance(flux, (int, float)):
            continue
        if energy not in {"0.05-0.4nm", "0.1-0.8nm"}:
            continue
        point = by_time.setdefault(time_tag, {"time": time_tag})
        point["short" if energy == "0.05-0.4nm" else "long"] = max(
            float(flux), 1e-10
        )
        if isinstance(record.get("satellite"), int):
            satellite = record["satellite"]

    points = [
        point
        for _, point in sorted(by_time.items())
        if "short" in point or "long" in point
    ]
    long_flux = [point["long"] for point in points if "long" in point]
    return {
        "satellite": satellite,
        "points": points,
        "current_flux": long_flux[-1] if long_flux else None,
        "peak_flux": max(long_flux) if long_flux else None,
        "updated": points[-1]["time"] if points else None,
    }


@app.get("/api/goes/xray")
async def goes_xray() -> JSONResponse:
    """Return normalized GOES X-ray flux with a short shared upstream cache."""
    now = time.monotonic()
    if _goes_cache["payload"] is not None and now < _goes_cache["expires"]:
        return JSONResponse(
            _goes_cache["payload"], headers={"Cache-Control": "no-store"}
        )

    async with _goes_lock:
        now = time.monotonic()
        if _goes_cache["payload"] is None or now >= _goes_cache["expires"]:
            records = await _get_json(GOES_XRAY_URL, timeout=15.0)
            if not isinstance(records, list):
                raise HTTPException(status_code=502, detail="Invalid GOES response")
            _goes_cache["payload"] = _format_goes_payload(records)
            _goes_cache["expires"] = now + 25.0

    return JSONResponse(
        _goes_cache["payload"], headers={"Cache-Control": "no-store"}
    )


@app.get("/api/goes/image")
async def goes_image() -> Response:
    """Proxy and cache the latest NOAA GOES/SUVI 195 Å image."""
    now = time.monotonic()
    if _image_cache["content"] is None or now >= _image_cache["expires"]:
        async with _image_lock:
            now = time.monotonic()
            if _image_cache["content"] is None or now >= _image_cache["expires"]:
                try:
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(20.0), follow_redirects=True
                    ) as client:
                        response = await client.get(GOES_IMAGE_URL)
                        response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise HTTPException(
                        status_code=502, detail="GOES image unavailable"
                    ) from exc
                _image_cache["content"] = response.content
                _image_cache["content_type"] = response.headers.get(
                    "content-type", "image/png"
                )
                _image_cache["expires"] = now + 300.0

    return Response(
        content=_image_cache["content"],
        media_type=_image_cache["content_type"],
        headers={"Cache-Control": "public, max-age=180"},
    )


@app.get("/", include_in_schema=False)
async def index() -> Response:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return JSONResponse(
        {"error": "Frontend build not found. Run `npm run build` in frontend/."},
        status_code=503,
    )


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str) -> Response:
    """Return frontend files or the SPA entry point for client-side routes."""
    candidate = (FRONTEND_DIST / path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST.resolve())
    except ValueError:
        raise HTTPException(status_code=404) from None
    if candidate.is_file():
        return FileResponse(candidate)
    return await index()
