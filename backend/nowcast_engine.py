"""Live-data adapter for the supplied occupancy GAM models."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from backend import realtime_nowcast_lookup as lookup

RADIO_CHANNELS = {40: 268, 60: 476, 80: 685}
STREAM_JY_PER_SFU = 240_000


class RadioBuffer:
    """One observed second per sample; gaps stay missing, never zero-filled.

    The live service's refresh timestamp is its HTTP response time, not a
    measurement time. Require its ring index to advance before accepting data.
    After startup or loss of radio eligibility, collect a full lookback again.
    """

    def __init__(self, seconds: int):
        self.seconds = seconds
        self.reset()

    def reset(self):
        self.samples = {}
        self.last_index = None
        self.first_second = None
        self.last_sample = None
        self.available = False

    def ingest(self, payload: dict, received_at: float):
        index = payload.get("buffer_index")
        frames = payload.get("data")
        if not isinstance(index, int) or not isinstance(frames, list) or not frames:
            self.reset()
            return
        if index == self.last_index:
            self.available = False
            return
        previous_index = self.last_index
        self.last_index = index
        if previous_index is None:
            return  # first response alone cannot prove that the stream is alive
        bands = {}
        for frequency, channel in RADIO_CHANNELS.items():
            values = []
            for frame in frames:
                if not isinstance(frame, list) or len(frame) != 768:
                    continue
                value = frame[channel]
                if isinstance(value, (int, float)) and math.isfinite(value):
                    flux = value / STREAM_JY_PER_SFU
                    # Reject missing/RFI values before averaging the 512 ms frames.
                    if 1 <= flux <= 2000:
                        values.append(flux)
            bands[frequency] = float(np.mean(values)) if values else float("nan")
        second = math.floor(received_at)
        self.samples[second] = bands
        self.first_second = second if self.first_second is None else self.first_second
        self.last_sample = received_at
        self.available = any(math.isfinite(value) for value in bands.values())
        self.samples = {s: v for s, v in self.samples.items() if s >= second - self.seconds - 5}

    def bands(self, issue_time: float):
        end = math.floor(issue_time)
        start = end - self.seconds
        if (not self.available or self.last_sample is None
                or not 0 <= issue_time - self.last_sample <= 3
                or self.first_second is None or self.first_second > start):
            return None
        return {
            frequency: np.array([
                self.samples.get(second, {}).get(frequency, float("nan"))
                for second in range(start, end)
            ])
            for frequency in RADIO_CHANNELS
        }


def utc_timestamp(value: str) -> float:
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.timestamp()


def json_finite(value):
    """Missing model features become JSON null, never nonstandard NaN."""
    if isinstance(value, dict):
        return {key: json_finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_finite(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


class NowcastEngine:
    def __init__(self, model_dir: Path):
        self.models = lookup.load_models(model_dir)
        self.requirements = lookup.buffer_requirements(self.models)

    def predict(self, issue_time: float, goes: dict, bands, reason: str):
        samples = {}
        for point in goes.get("points", []):
            flux = point.get("long")
            try:
                timestamp = utc_timestamp(point["time"])
            except (KeyError, ValueError, TypeError):
                continue
            if (timestamp <= issue_time and isinstance(flux, (int, float))
                    and math.isfinite(flux) and flux > 0):
                samples[timestamp] = flux
        times = sorted(samples)
        if not times or times[0] > issue_time - self.requirements["sxr_s"]:
            raise ValueError("Insufficient GOES history for the nowcast")
        result = lookup.nowcast(
            issue_time, np.array(times), np.array([samples[t] for t in times]),
            bands, self.models,
        )
        if not all(math.isfinite(result[name]["probability"]) for name in (">M1", ">M5", ">X1")):
            raise ValueError("Required GOES features are unavailable")
        result["created_utc"] = self.requirements["created_utc"]
        result["frequencies_mhz"] = list(RADIO_CHANNELS)
        result["mode"] = "radio_xray" if result["used_radio"] else "xray_only"
        result["radio_status"] = reason if bands is None else (
            "available" if result["radio_available"] else "insufficient_valid_radio"
        )
        return json_finite(result)
