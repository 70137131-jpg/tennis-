import asyncio
import math
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect

from courtside.live import LiveAnalyzer
from courtside.schemas import Keypoint


class Estimator:
    def __init__(self):
        self.closed = False

    def detect(self, image, timestamp):
        points = [Keypoint(x=150, y=40, confidence=0.99) for _ in range(17)]
        for i, xy in {
            5: (100, 80),
            6: (180, 80),
            7: (90, 110),
            8: (200, 110),
            9: (80, 140),
            10: (220 + 70 * math.sin(timestamp / 90), 120),
            11: (110, 150),
            12: (170, 150),
            13: (110, 190),
            14: (170, 190),
            15: (110, 220),
            16: (170, 220),
        }.items():
            points[i] = Keypoint(x=xy[0], y=xy[1], confidence=0.99)
        return [points]

    def close(self):
        self.closed = True


@pytest.fixture
def jpeg():
    image = np.full((240, 320, 3), (45, 80, 55), np.uint8)
    cv2.circle(image, (120, 100), 4, (0, 230, 230), -1)
    return cv2.imencode(".jpg", image)[1].tobytes()


def test_live_tracks_players_ball_and_measured_suggestions_with_bounded_state(jpeg):
    estimator = Estimator()
    engine = LiveAnalyzer({"experimental_feedback": True}, estimator)
    for timestamp in range(0, 12000, 67):
        result = engine.process(jpeg, timestamp)
    assert result["players_detected"] == 1
    assert result["shots_total"] > 0 and result["latest_shot"]["metrics"]
    assert result["latest_shot"]["experimental"]
    assert result["latest_shot"]["classification_source"] == "heuristic"
    assert result["latest_shot"]["classification_evidence"]
    assert result["latest_shot"]["technique"]["expected_checks"] == 2
    assert result["latest_shot"]["technique"]["score"] == result["latest_shot"]["rating"]
    assert result["session_rating"] is not None
    assert any(m["measurable"] for m in result["latest_shot"]["metrics"])
    assert len(engine.poses) <= engine.live_config["max_buffer_poses"]
    assert all(
        p.time >= result["timestamp"] / 1000 - engine.live_config["history_seconds"] for p in engine.poses
    )
    assert engine.latest_shot["tips"]
    engine.close()
    assert estimator.closed and not engine.poses and not engine.pending


def test_live_preview_disabled_and_invalid_frames_are_unscored(jpeg):
    engine = LiveAnalyzer({"experimental_feedback": False}, Estimator())
    for timestamp in range(0, 4000, 67):
        result = engine.process(jpeg, timestamp)
    assert result["latest_shot"]["tips"] == [] and result["latest_shot"]["rating"] is None
    assert result["latest_shot"]["technique"]["status"] == "disabled"
    with pytest.raises(ValueError, match="increase"):
        engine.process(jpeg, 0)
    with pytest.raises(ValueError, match="JPEG"):
        engine.process(b"not an image", 5000)
    with pytest.raises(ValueError, match="byte limit"):
        engine.process(b"a" * 750001, 5100)
    other = cv2.imencode(".jpg", np.zeros((100, 100, 3), np.uint8))[1].tobytes()
    result = engine.process(other, 5200)
    assert result["width"] == 100 and result["height"] == 100
    assert len(engine.poses) == 1
    engine.close()


def test_live_retains_minimum_gap_between_sliding_window_candidates(jpeg, monkeypatch):
    from courtside.schemas import Shot

    calls = iter([1.0, 1.1])

    def candidates(*args):
        contact = next(calls)
        return [
            Shot(
                id="s",
                player_id="player-near",
                type="forehand",
                start=0,
                contact=contact,
                end=contact,
                confidence=0.78,
            )
        ]

    monkeypatch.setattr("courtside.live.segment_shots", candidates)
    engine = LiveAnalyzer(estimator=Estimator())
    engine.process(jpeg, 1000)
    engine.process(jpeg, 1100)
    assert len(engine.pending) == 1
    engine.close()


def test_closed_analyzer_rejects_frames_even_with_a_fake_estimator(jpeg):
    engine = LiveAnalyzer(estimator=Estimator())
    engine.close()
    with pytest.raises(RuntimeError, match="closed"):
        engine.process(jpeg, 0)


@pytest.mark.parametrize("timestamp", [True, 0.5, float("nan"), float("inf")])
def test_noninteger_timestamps_are_rejected_before_native_inference(jpeg, timestamp):
    engine = LiveAnalyzer(estimator=Estimator())
    with pytest.raises(ValueError, match="timestamps"):
        engine.process(jpeg, timestamp)
    engine.close()


@pytest.mark.parametrize("failure", ["calibration", "classifier"])
def test_failed_setup_does_not_allocate_native_estimator(monkeypatch, tmp_path, failure):
    allocated = []
    monkeypatch.setattr("courtside.live.PoseEstimator", lambda path: allocated.append(path))
    options = {}
    if failure == "calibration":
        options["court_corners"] = [[0, 0]] * 4
    else:
        monkeypatch.setenv("COURTSIDE_CLASSIFIER", str(tmp_path / "missing.json"))
    with pytest.raises((ValueError, FileNotFoundError)):
        LiveAnalyzer(options)
    assert allocated == []


def test_close_clears_frame_and_pose_memory_even_when_native_close_fails(jpeg):
    class BrokenClose(Estimator):
        def close(self):
            raise RuntimeError("native close failed")

    engine = LiveAnalyzer(estimator=BrokenClose())
    engine.process(jpeg, 0)
    assert engine.tracker.tracks and engine.ball_tracker.previous is not None
    with pytest.raises(RuntimeError, match="native close"):
        engine.close()
    assert not engine.poses and not engine.pending and not engine.tracker.tracks
    assert engine.ball_tracker.previous is None and engine.latest_shot is None
    engine.close()  # Idempotent, including after a failed native close.


def test_camera_gap_discards_pending_shots_and_stale_latest_result(jpeg):
    engine = LiveAnalyzer({"experimental_feedback": True}, Estimator())
    for timestamp in range(0, 4000, 67):
        result = engine.process(jpeg, timestamp)
    assert result["latest_shot"] is not None
    result = engine.process(jpeg, 10000)
    assert result["latest_shot"] is None and not engine.pending and len(engine.poses) == 1
    engine.close()


def test_live_uses_classifier_shot_type_before_selecting_metric_targets(jpeg, monkeypatch):
    import courtside.live as live

    original_segment = live.segment_shots

    def forehand_candidates(*args):
        shots = original_segment(*args)
        for shot in shots:
            shot.type = "forehand"
        return shots

    monkeypatch.setattr(live, "segment_shots", forehand_candidates)
    engine = LiveAnalyzer({"experimental_feedback": True}, Estimator())
    engine.classifier = SimpleNamespace(predict=lambda sequence: ("serve", 0.99))
    for timestamp in range(0, 4000, 67):
        result = engine.process(jpeg, timestamp)
    shot = result["latest_shot"]
    assert shot["type"] == "serve"
    assert shot["classification_source"] == "trained"
    targets = {metric["name"]: metric["target"] for metric in shot["metrics"]}
    assert targets["elbow_extension"] == [145, 180]
    assert targets["finish_height"] is None
    engine.close()


def test_real_pose_live_smoke_has_no_fabricated_people(jpeg):
    engine = LiveAnalyzer()
    result = engine.process(jpeg, 0)
    engine.close()
    assert result["poses"] == [] and result["shots_total"] == 0
    assert result["latest_shot"] is None and result["session_rating"] is None


def test_websocket_consent_auth_and_frame_lifecycle(client, jpeg, monkeypatch):
    class FakeLive:
        closed = False

        def __init__(self, options):
            self.options = options

        def process(self, frame, timestamp):
            assert frame == jpeg
            return {"type": "frame", "timestamp": timestamp, "poses": []}

        def close(self):
            FakeLive.closed = True

    monkeypatch.setattr("api.live.LiveAnalyzer", FakeLive)
    with client.websocket_connect("/api/live") as ws:
        ws.send_json({"type": "start", "options": {}})
        assert ws.receive_json()["type"] == "error"
    with client.websocket_connect("/api/live") as ws:
        ws.send_json({"type": "start", "options": {"processing_consent": True}})
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(jpeg)
        assert ws.receive_json()["type"] == "frame"
        ws.send_text("stop")
        assert ws.receive_json()["type"] == "stopped"
    assert FakeLive.closed and not client.app.state.live_active
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/live", headers={"Origin": "https://untrusted.example"}):
            pass


def test_websocket_junior_consent_and_single_live_session(client, monkeypatch):
    monkeypatch.setattr("api.live.LiveAnalyzer", lambda options: Estimator())
    with client.websocket_connect("/api/live") as ws:
        ws.send_json({"type": "start", "options": {"processing_consent": True, "age_group": "junior"}})
        assert "Guardian" in ws.receive_json()["message"]
    client.app.state.live_active = True
    with client.websocket_connect("/api/live") as ws:
        ws.send_json({"type": "start", "options": {"processing_consent": True}})
        assert "Another live session" in ws.receive_json()["message"]
    assert client.app.state.live_active
    client.app.state.live_active = False


def test_jpeg_header_rejects_excessive_dimensions_before_decoding(jpeg):
    from courtside.live import jpeg_dimensions

    assert jpeg_dimensions(jpeg) == (320, 240)
    data = bytearray(jpeg)
    index = data.find(b"\xff\xc0")
    data[index + 5 : index + 9] = b"\xff\xff\xff\xff"
    engine = LiveAnalyzer(estimator=Estimator())
    with pytest.raises(ValueError, match="1080p"):
        engine.process(bytes(data), 0)
    engine.close()


def test_websocket_token_enforcement_and_frame_limits(tmp_path, monkeypatch, jpeg):
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("COURTSIDE_TOKEN", "private-test-token-at-least-24-characters")

    class FakeLive:
        def __init__(self, options):
            pass

        def close(self):
            pass

    monkeypatch.setattr("api.live.LiveAnalyzer", FakeLive)
    with TestClient(create_app(tmp_path, False, False)) as client:
        with client.websocket_connect("/api/live") as ws:
            ws.send_json({"type": "start", "options": {"processing_consent": True}})
            assert "token" in ws.receive_json()["message"]
        with client.websocket_connect("/api/live") as ws:
            ws.send_json(
                {
                    "type": "start",
                    "token": "private-test-token-at-least-24-characters",
                    "options": {"processing_consent": True},
                }
            )
            assert ws.receive_json()["type"] == "ready"
            ws.send_bytes(b"a" * 750001)
            assert "byte limit" in ws.receive_json()["message"]
        assert not client.app.state.live_active


@pytest.mark.parametrize("error_during_receive", [False, True])
def test_disconnect_during_error_or_close_still_releases_live_session(monkeypatch, error_during_receive):
    from fastapi import FastAPI

    from api.live import register_live

    estimator = Estimator()
    monkeypatch.setattr("api.live.LiveAnalyzer", lambda options: estimator)

    class DisconnectedSocket:
        headers = {}
        url = "ws://127.0.0.1/api/live"
        client = SimpleNamespace(host="127.0.0.1")

        async def accept(self):
            pass

        async def receive_json(self):
            return {"type": "start", "options": {"processing_consent": True}}

        async def receive(self):
            if error_during_receive:
                raise ValueError("Malformed frame")
            return {"type": "websocket.disconnect"}

        async def send_json(self, message):
            if message["type"] == "error":
                raise WebSocketDisconnect(code=1006)

        async def close(self):
            raise WebSocketDisconnect(code=1006)

    app = FastAPI()
    register_live(app, "", [])
    endpoint = next(route.endpoint for route in app.routes if route.path == "/api/live")
    asyncio.run(endpoint(DisconnectedSocket()))
    assert estimator.closed and not app.state.live_active
