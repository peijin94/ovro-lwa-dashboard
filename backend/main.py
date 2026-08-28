"""FastAPI server for the OVRO-LWA real-time dashboard."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles


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

app = FastAPI(
    title="OVRO-LWA Solar Dashboard",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

if (FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

_goes_cache: Dict[str, Any] = {"expires": 0.0, "payload": None}
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
            _goes_cache["expires"] = now + 8.0

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
