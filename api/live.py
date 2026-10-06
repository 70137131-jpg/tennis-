"""Authenticated WebSocket frame transport with one in-flight frame and bounded state."""

import asyncio
import hmac
import logging
import time
from pathlib import Path
from typing import Literal

import yaml
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from courtside.live import LiveAnalyzer


class LiveOptions(BaseModel):
    handedness: Literal["left", "right"] = "right"
    level: Literal["beginner", "intermediate", "competitive"] = "competitive"
    age_group: Literal["junior", "adult"] = "adult"
    processing_consent: bool = False
    guardian_consent: bool = False
    guardian_name: str = Field(default="", max_length=100)
    player_assent: bool = False
    experimental_feedback: bool = False
    court_corners: list[list[float]] | None = None


def register_live(app, token: str, allowed_origins: list[str], trusted_gateway=False, capacity=None):
    app.state.live_active = False
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs/live.yaml").read_text())

    @app.websocket("/api/live")
    async def live_socket(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        current_origin = (
            str(websocket.url).split("/api/")[0].replace("ws://", "http://").replace("wss://", "https://")
        )
        if origin and origin not in allowed_origins and origin != current_origin:
            await websocket.close(code=1008, reason="Origin not allowed")
            return
        if (
            not token
            and not trusted_gateway
            and websocket.client
            and websocket.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}
        ):
            await websocket.close(code=1008, reason="Configure workspace token for remote access")
            return
        await websocket.accept()
        engine = None
        claimed = False
        capacity_claimed = False
        try:
            start = await asyncio.wait_for(websocket.receive_json(), timeout=15)
            if (
                not isinstance(start, dict)
                or start.get("type") != "start"
                or (not trusted_gateway and not hmac.compare_digest(str(start.get("token", "")), token))
            ):
                await websocket.send_json({"type": "error", "message": "Workspace access token required"})
                await websocket.close(code=1008)
                return
            options = LiveOptions.model_validate(start.get("options", {}))
            if not options.processing_consent:
                raise ValueError("Permission to process everyone in the camera view is required")
            if options.age_group == "junior" and not (
                options.guardian_consent and options.player_assent and options.guardian_name.strip()
            ):
                raise ValueError("Guardian consent, guardian name and player assent are required for juniors")
            if options.court_corners:
                from courtside.court import CourtCalibration

                CourtCalibration(options.court_corners, 1000, 1000)
            if app.state.live_active:
                raise ValueError("Another live session is running in this workspace. Stop it first.")
            if capacity is not None:
                capacity_claimed = capacity.acquire(blocking=False)
                if not capacity_claimed:
                    raise ValueError("Live processing capacity is busy. Try again when another court stops.")
            app.state.live_active = True
            claimed = True
            engine = await asyncio.to_thread(LiveAnalyzer, options.model_dump())
            await websocket.send_json(
                {"type": "ready", "target_fps": config["target_fps"], "max_width": config["max_width"]}
            )
            began = time.perf_counter()
            last_timestamp = -1
            while True:
                message = await asyncio.wait_for(websocket.receive(), timeout=config["idle_timeout_seconds"])
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text"):
                    if message["text"] == "stop":
                        await websocket.send_json({"type": "stopped"})
                        break
                    raise ValueError("Send binary JPEG frames or stop")
                frame = message.get("bytes")
                if not frame or len(frame) > config["max_frame_bytes"]:
                    raise ValueError("Live frame exceeds the configured byte limit")
                timestamp = max(last_timestamp + 1, round((time.perf_counter() - began) * 1000))
                last_timestamp = timestamp
                response = await asyncio.to_thread(engine.process, frame, timestamp)
                await websocket.send_json(response)
        except (ValueError, RuntimeError, ValidationError, asyncio.TimeoutError) as exc:
            try:
                await websocket.send_json({"type": "error", "message": str(exc) or "Camera stream timed out"})
            except (RuntimeError, WebSocketDisconnect):
                pass
        except WebSocketDisconnect:
            pass
        except Exception:
            logging.getLogger("courtside.live").exception("Live analysis failed")
            try:
                await websocket.send_json(
                    {"type": "error", "message": "Live analysis stopped. Check the local server log."}
                )
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            try:
                if engine:
                    await asyncio.to_thread(engine.close)
            finally:
                if claimed:
                    app.state.live_active = False
                if capacity_claimed:
                    capacity.release()
            try:
                await websocket.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
