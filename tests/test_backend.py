import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import main


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

    def test_built_frontend_is_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("OVRO-LWA Solar Monitor", response.text)


if __name__ == "__main__":
    unittest.main()
