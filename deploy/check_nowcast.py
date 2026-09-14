"""Read-only model smoke check with live GOES and simulated radio eligibility.

Run from the repo root: python -m deploy.check_nowcast
Does not alter the running service or write probability records.
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

from backend import main
from backend.nowcast_engine import NowcastEngine, RadioBuffer


async def check():
    main.nowcast_engine = NowcastEngine(main.FLARE_MODEL_DIR)
    for name, elevation in (("below_12_deg", 11.9), ("stream_unavailable", 40.0)):
        main.radio_buffer = RadioBuffer(180)
        with patch.object(main, "_get_text", AsyncMock(return_value=f"alt={elevation}deg az=100.0deg")):
            result = await main._fetch_current_flare_nowcast()
        assert result["mode"] == "xray_only", result
        assert result["horizon_min"] == 10, result
        print(json.dumps({"scenario": name, **result}, allow_nan=False))


if __name__ == "__main__":
    asyncio.run(check())
