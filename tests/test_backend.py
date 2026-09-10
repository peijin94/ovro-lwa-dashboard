import asyncio
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import main
from backend.flare_records import FlareRecordStore


class GoesPayloadTests(unittest.TestCase):
    def test_formats_and_sorts_goes_channels(self) -> None:
        records = [
            {
                "time_tag": "2026-08-25T12:01:00Z",
                "satellite": 18,
                "flux": 2e-6,
                "energy": "0.1-0.8nm",
            },
            {
                "time_tag": "2026-08-25T12:00:00Z",
                "satellite": 18,
                "flux": 4e-8,
                "energy": "0.05-0.4nm",
            },
            {
                "time_tag": "2026-08-25T12:00:00Z",
                "satellite": 18,
                "flux": 1e-6,
                "energy": "0.1-0.8nm",
            },
            {
                "time_tag": "2026-08-25T12:00:00Z",
                "satellite": 18,
                "flux": 99,
                "energy": "unsupported",
            },
        ]

        payload = main._format_goes_payload(records)

        self.assertEqual(payload["satellite"], 18)
        self.assertEqual(len(payload["points"]), 2)
        self.assertEqual(payload["points"][0]["long"], 1e-6)
        self.assertEqual(payload["current_flux"], 2e-6)
        self.assertEqual(payload["peak_flux"], 2e-6)


class EphemerisPayloadTests(unittest.TestCase):
    def test_parses_shared_ephemeris_response(self) -> None:
        payload = main._parse_ephemeris_info(
            "time=2026-08-30T03:40:04+00:00 alt=-14.87deg az=293.92deg "
            "sunup=0 sunrise=2026-08-30T13:22:00+00:00 "
            "sunset=2026-08-31T02:24:44+00:00"
        )

        self.assertEqual(payload["elevation_deg"], -14.87)
        self.assertEqual(payload["azimuth_deg"], 293.92)
        self.assertFalse(payload["sun_up"])
        self.assertEqual(payload["updated"], "2026-08-30T03:40:04+00:00")


class RadioFluxTests(unittest.TestCase):
    def test_extracts_normalized_40_60_80_mhz_fluxes(self) -> None:
        frame = [0.0] * 768
        frame[268] = 240_000
        frame[476] = 480_000
        frame[685] = 720_000

        self.assertEqual(main._radio_flux3ch(frame), [1.0, 2.0, 3.0])


class FlareRecordStoreTests(unittest.TestCase):
    def test_persists_and_filters_recent_probability_records(self) -> None:
        with TemporaryDirectory() as directory:
            store = FlareRecordStore(Path(directory) / "flarecast_record.sqlite3")
            store.initialize()
            store.append("2026-09-10T18:59:59.000Z", 0.1, 0.05, 0.01)
            store.append("2026-09-10T19:15:00.000Z", 0.7, 0.3, 0.1)

            points = store.recent(
                30,
                now=datetime(2026, 9, 10, 19, 30, tzinfo=timezone.utc),
            )

        self.assertEqual(points, [
            {
                "timeUT": "2026-09-10T19:15:00.000Z",
                "R1p": 0.7,
                "R2p": 0.3,
                "R3p": 0.1,
            }
        ])


class FlareRecorderTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocking_work_is_compatible_without_asyncio_to_thread(self) -> None:
        with patch.object(asyncio, "to_thread", None, create=True):
            result = await main._run_blocking(lambda value: value + 1, 41)

        self.assertEqual(result, 42)

    async def test_records_nowcast_only_while_sun_is_up(self) -> None:
        forecast = {
            ">M1": {"probability": 0.7},
            ">M5": {"probability": 0.3},
            ">X1": {"probability": 0.1},
        }
        with TemporaryDirectory() as directory:
            store = FlareRecordStore(Path(directory) / "flarecast_record.sqlite3")
            store.initialize()
            with (
                patch.object(main, "flare_record_store", store),
                patch.object(main, "_latest_flare_nowcast", None),
                patch.object(
                    main,
                    "_get_text",
                    AsyncMock(return_value="time=x alt=12.0deg az=100.0deg sunup=1"),
                ),
                patch.object(
                    main,
                    "_fetch_current_flare_nowcast",
                    AsyncMock(return_value=forecast),
                ),
                patch.object(main, "_utc_now_text", return_value="2026-09-10T19:30:00.000Z"),
            ):
                recorded = await main._record_current_flare_probability()

            points = store.recent(
                30,
                now=datetime(2026, 9, 10, 19, 31, tzinfo=timezone.utc),
            )

        self.assertTrue(recorded)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["R1p"], 0.7)

    async def test_skips_nowcast_query_while_sun_is_down(self) -> None:
        nowcast = AsyncMock()
        with (
            patch.object(
                main,
                "_get_text",
                AsyncMock(return_value="time=x alt=-0.1deg az=280.0deg sunup=0"),
            ),
            patch.object(main, "_fetch_current_flare_nowcast", nowcast),
        ):
            recorded = await main._record_current_flare_probability()

        self.assertFalse(recorded)
        nowcast.assert_not_awaited()


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_health_reports_live_768_channel_stream(self) -> None:
        with patch.object(main, "_get_json", AsyncMock(return_value=[1.0] * 768)):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["spectrum_channels"], 768)

    def test_history_frame_limit_is_validated(self) -> None:
        response = self.client.get("/api/spectrum/history?n_frames=601")
        self.assertEqual(response.status_code, 422)

    def test_ephemeris_normalizes_shared_api_response(self) -> None:
        raw = "time=2026-08-30T03:40:04+00:00 alt=9.5deg az=120.0deg sunup=0"
        with patch.object(main, "_get_text", AsyncMock(return_value=raw)):
            response = self.client.get("/api/ephemeris")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["elevation_deg"], 9.5)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_flare_nowcast_uses_current_normalized_radio_flux(self) -> None:
        frame = [0.0] * 768
        frame[268] = 240_000
        frame[476] = 480_000
        frame[685] = 720_000
        forecast = {
            "feature_sfu": 2.0,
            "horizon_min": 5.0,
            ">M1": {"probability": 0.7},
            ">M5": {"probability": 0.3},
            ">X1": {"probability": 0.1},
        }
        with (
            patch.object(main, "_get_json", AsyncMock(return_value=frame)),
            patch.object(main, "_post_json", AsyncMock(return_value=forecast)) as post,
            patch.object(main, "_latest_flare_nowcast", None),
        ):
            response = self.client.get("/api/flare/nowcast")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[">M1"]["probability"], 0.7)
        post.assert_awaited_once_with(
            main.FLARE_NOWCAST_URL,
            {"flux3ch": [1.0, 2.0, 3.0]},
            timeout=15.0,
        )

    def test_flare_history_returns_database_records(self) -> None:
        with TemporaryDirectory() as directory:
            store = FlareRecordStore(Path(directory) / "flarecast_record.sqlite3")
            store.initialize()
            store.append(main._utc_now_text(), 0.7, 0.3, 0.1)
            with patch.object(main, "flare_record_store", store):
                response = self.client.get("/api/flare/history?minutes=30")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["window_minutes"], 30)
        self.assertEqual(response.json()["points"][0]["R1p"], 0.7)

    def test_flare_nowcast_returns_recorder_cache_without_database_read(self) -> None:
        cached = {
            ">M1": {"probability": 0.7},
            ">M5": {"probability": 0.3},
            ">X1": {"probability": 0.1},
            "recorded_at": "2026-09-10T19:30:00.000Z",
        }
        fetch = AsyncMock()
        with (
            patch.object(main, "_latest_flare_nowcast", cached),
            patch.object(main, "_fetch_current_flare_nowcast", fetch),
        ):
            response = self.client.get("/api/flare/nowcast")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recorded_at"], cached["recorded_at"])
        fetch.assert_not_awaited()

    def test_built_frontend_is_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("OVRO-LWA Solar Radio Monitor", response.text)


if __name__ == "__main__":
    unittest.main()
