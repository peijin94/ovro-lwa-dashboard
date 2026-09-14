import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
from fastapi import HTTPException

from backend import main
from backend.nowcast_engine import NowcastEngine, RadioBuffer
from backend import realtime_nowcast_lookup as lookup

ROOT = Path(__file__).resolve().parents[1]
ISSUE = 1_790_000_000


def goes_history(delay=180, rising=False):
    times = np.arange(ISSUE - 7200, ISSUE - delay + 1, 60)
    return {"points": [
        {"time": datetime.fromtimestamp(int(t), timezone.utc).isoformat(),
         "long": float(3e-6 * (1 + max(0, (t - (ISSUE - 600)) / 600))) if rising else 3e-6}
        for t in times
    ]}


def refresh(index, flux=10):
    frame = [0.0] * 768
    for channel in (268, 476, 685):
        frame[channel] = flux * 240_000
    return {"data": [frame, frame], "buffer_index": index}


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = NowcastEngine(ROOT / "models")

    def test_real_models_predict_xray_only_without_radio(self):
        result = self.engine.predict(ISSUE, goes_history(), None, "sun_below_12_deg")
        self.assertEqual(result["model_version"], "v0.3")
        self.assertEqual(result["horizon_min"], 10)
        self.assertEqual(result["lag_used_min"], 3)
        self.assertEqual(result["mode"], "xray_only")
        self.assertIsNone(result["feature_sfu"])
        for name in (">M1", ">M5", ">X1"):
            self.assertEqual(result[name]["probability"], result[name]["probability_sxr_only"])
            self.assertTrue(0 <= result[name]["probability"] <= 1)
        json.dumps(result, allow_nan=False)

    def test_real_models_use_radio_only_when_blend_gate_allows_it(self):
        bands = {f: np.full(180, 20.0) for f in (40, 60, 80)}
        quiet = self.engine.predict(ISSUE, goes_history(), bands, "available")
        rising = self.engine.predict(ISSUE, goes_history(rising=True), bands, "available")
        self.assertTrue(quiet["radio_available"])
        self.assertFalse(quiet["used_radio"])
        self.assertTrue(rising["used_radio"])
        self.assertEqual(rising["mode"], "radio_xray")

    def test_invalid_or_short_radio_falls_back(self):
        for bands in ({f: np.full(180, np.nan) for f in (40, 60, 80)},
                      {40: np.ones(20)}, {40: np.full(180, 5000)}):
            result = self.engine.predict(ISSUE, goes_history(), bands, "available")
            self.assertFalse(result["used_radio"])
            self.assertEqual(result[">M1"]["probability"], result[">M1"]["probability_sxr_only"])

    def test_latency_ceil_and_future_goes_is_ignored(self):
        history = goes_history(delay=181)
        history["points"].append({"time": datetime.fromtimestamp(ISSUE + 60, timezone.utc).isoformat(), "long": 1})
        result = self.engine.predict(ISSUE, history, None, "unavailable")
        self.assertEqual(result["lag_used_min"], 4)
        for delay, expected in [(0, 1), (60, 1), (61, 2), (360, 6), (361, 6)]:
            selected = lookup.select_lag(delay, tuple(self.engine.models))
            self.assertEqual(selected["lag_s"], expected * 60)
            self.assertEqual(selected["delay_exceeds_train"], delay > 360)

    def test_insufficient_or_missing_goes_skips_prediction(self):
        for history in ({"points": []}, {"points": goes_history()["points"][-5:]}, goes_history(delay=1800)):
            with self.assertRaises(ValueError):
                self.engine.predict(ISSUE, history, None, "unavailable")


class RadioBufferTests(unittest.TestCase):
    def test_warmup_calibration_frozen_stream_outage_and_recovery(self):
        buffer = RadioBuffer(180)
        buffer.ingest(refresh(0), 0)
        self.assertIsNone(buffer.bands(1))
        for second in range(1, 182):
            buffer.ingest(refresh(second), second)
        bands = buffer.bands(181)
        self.assertEqual(len(bands[40]), 180)
        np.testing.assert_allclose(bands[40], 10)
        buffer.ingest(refresh(181), 182)
        self.assertIsNone(buffer.bands(182))
        buffer.ingest(refresh(183), 183)
        self.assertIsNotNone(buffer.bands(183))
        self.assertIsNone(buffer.bands(187))
        buffer.reset()
        self.assertIsNone(buffer.bands(188))


class FallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_goes_does_not_record_or_replace_latest(self):
        store = Mock()
        cached = {"unix_s": 1}
        with (patch.object(main, "flare_record_store", store),
              patch.object(main, "_latest_flare_nowcast", cached),
              patch.object(main, "_fetch_current_flare_nowcast", AsyncMock(side_effect=HTTPException(503)))):
            with self.assertRaises(HTTPException):
                await main._record_current_flare_probability()
            self.assertIs(main._latest_flare_nowcast, cached)
        store.append.assert_not_called()

    async def test_elevation_boundary_and_ephemeris_outage(self):
        for altitude in (-20, 0, 11.99, 12, 50, None):
            with self.subTest(altitude=altitude):
                engine = Mock()
                engine.predict.return_value = {"mode": "test"}
                radio = Mock()
                radio.bands.return_value = {40: [1]}
                eph = AsyncMock(return_value=f"alt={altitude}deg az=100.0deg")
                if altitude is None:
                    eph.side_effect = HTTPException(502)
                with (patch.object(main, "nowcast_engine", engine),
                      patch.object(main, "radio_buffer", radio),
                      patch.object(main, "_get_text", eph),
                      patch.object(main, "_radio_enabled", False),
                      patch.object(main, "_get_goes_payload", AsyncMock(return_value=goes_history()))):
                    await main._fetch_current_flare_nowcast()
                passed_bands = engine.predict.call_args.args[2]
                if altitude is not None and altitude >= 12:
                    self.assertIsNotNone(passed_bands)
                else:
                    self.assertIsNone(passed_bands)
                    radio.reset.assert_called_once()

    async def test_missing_stream_still_runs_prediction_at_high_sun(self):
        engine = Mock()
        engine.predict.return_value = {"mode": "xray_only"}
        with (patch.object(main, "nowcast_engine", engine),
              patch.object(main, "radio_buffer", RadioBuffer(180)),
              patch.object(main, "_get_text", AsyncMock(return_value="alt=40.0deg az=100.0deg")),
              patch.object(main, "_radio_enabled", False),
              patch.object(main, "_get_goes_payload", AsyncMock(return_value=goes_history()))):
            result = await main._fetch_current_flare_nowcast()
        self.assertEqual(result["mode"], "xray_only")
        self.assertIsNone(engine.predict.call_args.args[2])
