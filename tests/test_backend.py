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

    def test_built_frontend_is_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("OVRO-LWA Solar Monitor", response.text)


if __name__ == "__main__":
    unittest.main()
