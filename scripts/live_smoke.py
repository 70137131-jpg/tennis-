"""Exercise the real local WebSocket/model with a synthetic, person-free feed."""

import asyncio
import json
import time
from pathlib import Path

import cv2
import numpy as np
from websockets.asyncio.client import connect


async def main():
    latencies = []
    processing = []
    async with connect(
        "ws://127.0.0.1:8000/api/live", origin="http://127.0.0.1:8000", max_size=1024 * 1024
    ) as ws:
        await ws.send(
            json.dumps(
                {"type": "start", "options": {"processing_consent": True, "experimental_feedback": True}}
            )
        )
        ready = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if ready["type"] != "ready":
            raise RuntimeError(ready)
        for index in range(20):
            image = np.full((240, 320, 3), (45, 80, 55), np.uint8)
            cv2.circle(image, (30 + index * 8, 100), 4, (0, 230, 230), -1)
            jpeg = cv2.imencode(".jpg", image)[1].tobytes()
            before = time.perf_counter()
            await ws.send(jpeg)
            response = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert response["type"] == "frame", response
            assert response["players_detected"] == 0 and response["shots_total"] == 0
            latencies.append((time.perf_counter() - before) * 1000)
            processing.append(response["processing_ms"])
        await ws.send("stop")
        assert json.loads(await ws.recv())["type"] == "stopped"
    result = {
        "fixture": "synthetic, person-free 320x240 JPEG feed; no tennis accuracy claim",
        "frames": len(latencies),
        "roundtrip_mean_ms": round(float(np.mean(latencies)), 1),
        "roundtrip_p95_ms": round(float(np.percentile(latencies, 95)), 1),
        "processing_mean_ms": round(float(np.mean(processing)), 1),
        "no_fabricated_people_or_shots": True,
    }
    output = Path("test-results/live-smoke.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
