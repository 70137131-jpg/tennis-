"""Explicit synthetic demonstration fixtures, never mixed with real evaluation."""

import json
import math
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from courtside.feedback import apply_rules, load_rules, summarize_tips
from courtside.pipeline import ROOT
from courtside.schemas import Metric, Report, Shot, ShotType, VideoInfo
from courtside.video import encode_video


def synthetic_clip(directory):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "demo.mp4"
    if target.exists():
        return
    raw = directory / "demo.avi"
    writer = cv2.VideoWriter(str(raw), cv2.VideoWriter.fourcc(*"MJPG"), 30, (960, 540))
    for frame in range(180):
        canvas = np.full((540, 960, 3), (47, 78, 54), np.uint8)
        court = np.array([[285, 135], [675, 135], [880, 515], [80, 515]], np.int32)
        cv2.fillConvexPoly(canvas, court, (111, 114, 73))
        cv2.polylines(canvas, [court], True, (204, 224, 209), 3, cv2.LINE_AA)
        for a, b in [
            ((230, 235), (730, 235)),
            ((160, 360), (800, 360)),
            ((390, 135), (275, 515)),
            ((570, 135), (685, 515)),
            ((480, 235), (480, 360)),
            ((188, 305), (772, 305)),
        ]:
            cv2.line(canvas, a, b, (210, 226, 210), 2, cv2.LINE_AA)
        cv2.line(canvas, (185, 303), (775, 303), (33, 51, 34), 8)
        phase = frame / 30 * 2
        x = 490 + int(math.sin(phase * 0.35) * 40)
        joints = [
            (x, 324),
            (x - 14, 345),
            (x + 14, 345),
            (x - 31, 367),
            (x + 33, 355),
            (x - 40, 385),
            (x + 42 + int(math.sin(phase) * 45), 337 + int(math.cos(phase) * 30)),
            (x - 11, 397),
            (x + 11, 397),
            (x - 24, 429),
            (x + 19, 432),
            (x - 34, 469),
            (x + 29, 468),
        ]
        cv2.circle(canvas, joints[0], 13, (195, 226, 204), -1)
        for joint_a, joint_b in [
            (0, 1),
            (0, 2),
            (1, 2),
            (1, 3),
            (3, 5),
            (2, 4),
            (4, 6),
            (1, 7),
            (2, 8),
            (7, 8),
            (7, 9),
            (9, 11),
            (8, 10),
            (10, 12),
        ]:
            cv2.line(canvas, joints[joint_a], joints[joint_b], (148, 235, 194), 3, cv2.LINE_AA)
        for point in joints[1:]:
            cv2.circle(canvas, point, 5, (188, 238, 208), -1)
        ball = (int(250 + (frame % 75) / 75 * 450), int(235 + math.sin(frame / 20) * 70))
        cv2.circle(canvas, ball, 5, (70, 239, 224), -1)
        cv2.putText(
            canvas,
            "COURTSIDE / SYNTHETIC DEMO",
            (25, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (208, 237, 219),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "FOREHAND  |  SKELETON OVERLAY",
            (25, 507),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (208, 237, 219),
            1,
            cv2.LINE_AA,
        )
        writer.write(canvas)
        if frame == 60:
            cv2.imwrite(str(directory / "poster.jpg"), canvas)
    writer.release()
    encode_video(raw, target)
    raw.unlink(missing_ok=True)


def seed_demo(store):
    with store.connection() as db:
        if db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]:
            return
    rules = load_rules(ROOT / "configs/feedback_rules.yaml")
    rules = {**rules, "version": "synthetic-demo-1", "coach_validated": True}
    for index, title in enumerate(
        [
            "Baseline practice",
            "Serve & return",
            "Evening rally",
            "Match day",
            "Footwork & forehands",
            "Sunday on court",
        ]
    ):
        count = [48, 36, 54, 64, 42, 40][index]
        shots = []
        for i in range(count):
            types: list[ShotType] = [
                "forehand",
                "backhand",
                "forehand",
                "serve",
                "volley",
                "forehand",
                "backhand",
                "serve",
            ]
            shot_type = types[i % 8]
            knee = float(137 + (i * 7 + index * 4) % 35)
            elbow = float(143 + (i * 3) % 35)
            metrics = [
                Metric(
                    name="knee_angle",
                    label="Knee bend",
                    phase="preparation",
                    value=knee,
                    unit="°",
                    confidence=0.93,
                    measurable=True,
                    target=[110, 160],
                ),
                Metric(
                    name="elbow_extension",
                    label="Arm extension",
                    phase="contact",
                    value=elbow,
                    unit="°",
                    confidence=0.94,
                    measurable=True,
                    target=[145, 180],
                ),
                Metric(
                    name="finish_height",
                    label="Finish height",
                    phase="finish",
                    value=round(0.58 + (i % 10) / 10, 2),
                    unit="× torso",
                    confidence=0.90,
                    measurable=True,
                    target=[0.7, 1.8],
                ),
                Metric(
                    name="contact_in_front",
                    label="Contact in front",
                    phase="contact",
                    value=None,
                    unit="",
                    confidence=0,
                    measurable=False,
                    reason="Not measurable from this 2D camera angle",
                ),
            ]
            contact = 18 + i * 22
            tips = apply_rules(metrics, shot_type, rules)
            shots.append(
                Shot(
                    id=f"shot-{i + 1:04d}",
                    player_id="player-near",
                    type=shot_type,
                    start=contact - 1.2,
                    contact=contact,
                    end=contact + 1.5,
                    confidence=0.87 + (i % 7) * 0.015,
                    metrics=metrics,
                    tips=tips,
                    clip="demo.mp4",
                    court_position=[2 + (i % 5), 18 + (i % 4)],
                )
            )
        duration = 1200 + index * 150
        report = Report(
            feedback_rules_version="synthetic-demo-1",
            coach_validated=False,
            is_demo=True,
            video=VideoInfo(width=1920, height=1080, fps=60, frames=duration * 60, duration=duration),
            shots=shots,
            summary_tips=summarize_tips([t for s in shots for t in s.tips], rules),
            players=[{"id": "player-near", "side": "near"}],
            annotated_video="demo.mp4",
            warnings=[
                "Illustrative synthetic session. Metrics, tips and video are examples, not an analysis of a real player."
            ],
            diagnostics={"processing_seconds": 94, "pose_frames": 1200, "ball_detection_rate": 0.91},
        )
        stamp = (datetime.now(timezone.utc) - timedelta(days=index * 3, hours=2)).isoformat()
        sid = f"demo-{index + 1}"
        directory = store.root / "sessions" / sid
        synthetic_clip(directory)
        (directory / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        with store.connection() as db:
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,'completed',100,'Complete',NULL,?,?,?,1,?)",
                (
                    sid,
                    title,
                    stamp,
                    json.dumps(
                        {
                            "player_name": "Ali Haider",
                            "handedness": "right",
                            "level": "competitive",
                            "session_type": "Practice",
                            "court": "Court 01",
                            "consent": {"synthetic": True},
                        }
                    ),
                    report.video.model_dump_json(),
                    report.model_dump_json(),
                    stamp,
                ),
            )
