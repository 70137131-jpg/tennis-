"""Bounded, stateful live-frame analysis. Frames are processed in memory only."""

import os
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np
import yaml

from courtside.assessment import assess_technique, shot_metrics
from courtside.court import CourtCalibration
from courtside.feedback import apply_rules, load_rules
from courtside.schemas import PoseFrame
from courtside.shots import segment_shots
from courtside.vision import BallTracker, PlayerTracker, PoseEstimator

ROOT = Path(__file__).resolve().parents[2]


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Read JPEG dimensions before OpenCV allocates a decompressed image."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Send a valid JPEG frame")
    offset = 2
    while offset + 4 < len(data):
        if data[offset] != 255:
            break
        while offset < len(data) and data[offset] == 255:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {1, 216} or 208 <= marker <= 215:
            continue
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in {192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207} and length >= 8:
            return int.from_bytes(data[offset + 5 : offset + 7], "big"), int.from_bytes(
                data[offset + 3 : offset + 5], "big"
            )
        offset += length
    raise ValueError("Send a valid JPEG frame")


def metric_rating(metrics) -> float | None:
    measurable = [m for m in metrics if m.measurable and m.value is not None and m.target]
    if not measurable:
        return None
    matches = sum(m.target[0] <= m.value <= m.target[1] for m in measurable)
    return round(matches / len(measurable) * 100, 1)


class LiveAnalyzer:
    def __init__(self, options=None, estimator=None):
        self.options = options or {}
        self.config = yaml.safe_load((ROOT / "configs/pipeline.yaml").read_text())
        self.live_config = yaml.safe_load((ROOT / "configs/live.yaml").read_text())
        self.rules = load_rules(ROOT / "configs/feedback_rules.yaml")
        self.estimator = estimator or PoseEstimator(
            Path(os.environ.get("COURTSIDE_MODEL", ROOT / "models/pose_landmarker_full.task"))
        )
        self.tracker = PlayerTracker(self.config["smoothing_alpha"], self.config["max_track_gap_seconds"])
        self.ball_tracker = BallTracker(self.config)
        self.poses: deque[PoseFrame] = deque(maxlen=self.live_config["max_buffer_poses"])
        self.balls: deque[dict] = deque(maxlen=self.live_config["max_buffer_poses"])
        self.pending: dict = {}
        self.seen: set[tuple] = set()
        self.counts: Counter = Counter()
        self.frame = 0
        self.last_timestamp = -1
        self.calibration = None
        self.dimensions = None
        self.classifier = None
        self.latest_shot = None
        self.ratings: deque[float] = deque(maxlen=100)
        if os.environ.get("COURTSIDE_CLASSIFIER"):
            from courtside.classifier import ShotClassifier

            self.classifier = ShotClassifier(
                Path(os.environ["COURTSIDE_CLASSIFIER"]),
                yaml.safe_load((ROOT / "configs/training.yaml").read_text()),
            )

    def close(self):
        self.estimator.close()
        self.poses.clear()
        self.balls.clear()
        self.pending.clear()
        self.seen.clear()

    def process(self, jpeg: bytes, timestamp: int) -> dict:
        started = time.perf_counter()
        if timestamp <= self.last_timestamp or timestamp < 0:
            raise ValueError("Live frame timestamps must increase")
        if not jpeg or len(jpeg) > self.live_config["max_frame_bytes"]:
            raise ValueError("Live frame exceeds the configured byte limit")
        input_width, input_height = jpeg_dimensions(jpeg)
        if (
            input_width <= 0
            or input_height <= 0
            or input_width * input_height > self.live_config["max_frame_pixels"]
        ):
            raise ValueError("Send a JPEG frame no larger than 1080p")
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0] * image.shape[1] > self.live_config["max_frame_pixels"]:
            raise ValueError("Send a JPEG frame no larger than 1080p")
        scale = min(1.0, self.live_config["max_width"] / image.shape[1])
        if scale < 1:
            image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
        height, width = image.shape[:2]
        if self.dimensions and self.dimensions != (width, height):
            # Adaptive capture changes the coordinate system; never mix old/new joints.
            self.dimensions = None
            self.calibration = None
            self.tracker = PlayerTracker(self.config["smoothing_alpha"], self.config["max_track_gap_seconds"])
            self.ball_tracker = BallTracker(self.config)
            self.poses.clear()
            self.balls.clear()
            self.pending.clear()
            self.seen.clear()
        if self.dimensions is None:
            self.dimensions = (width, height)
            if self.options.get("court_corners"):
                self.calibration = CourtCalibration(self.options["court_corners"], width, height)
        self.last_timestamp = timestamp
        stamp = timestamp / 1000
        detections = self.estimator.detect(image, timestamp)
        poses = self.tracker.update(detections, self.frame, stamp, self.calibration)
        self.frame += 1
        self.poses.extend(poses)
        ball = self.ball_tracker.update(image, stamp)
        if ball:
            self.balls.append(ball)
        cutoff = stamp - self.live_config["history_seconds"]
        while self.poses and self.poses[0].time < cutoff:
            self.poses.popleft()
        while self.balls and self.balls[0]["time"] < cutoff:
            self.balls.popleft()
        self.seen = {key for key in self.seen if key[1] >= round(cutoff * 1000)}
        candidates = segment_shots(
            list(self.poses),
            stamp,
            self.config,
            self.options.get("handedness", "right"),
            self.calibration,
            list(self.balls),
        )
        for shot in candidates:
            key = (shot.player_id, round(shot.contact * 1000))
            if key in self.seen or len(self.pending) >= self.live_config["max_pending_shots"]:
                continue
            self.seen.add(key)
            shot.id = f"live-{key[1]}-{shot.player_id}"
            shot.end = shot.contact + self.config["clip_after_seconds"]
            self.pending[key] = shot
        for key, shot in list(self.pending.items()):
            if stamp < shot.end:
                continue
            sequence = [
                p for p in self.poses if p.player_id == shot.player_id and shot.start <= p.time <= shot.end
            ]
            del self.pending[key]
            if not sequence:
                continue

            if self.classifier:
                shot.type, probability = self.classifier.predict(sequence)
                shot.confidence = min(shot.confidence, probability)
                shot.classification_source = "trained"
                shot.classification_evidence = ["Promoted temporal pose classifier"]
            shot.metrics = shot_metrics(
                sequence,
                shot,
                self.options.get("handedness", "right"),
                self.config["min_keypoint_confidence"],
            )
            preview = self.options.get("experimental_feedback", False)
            shot.technique = assess_technique(
                shot, self.rules, self.options.get("age_group", "adult"),
                self.options.get("level", "competitive"), preview or self.rules["coach_validated"]
            )
            rules = {**self.rules, "coach_validated": self.rules["coach_validated"] or preview}
            shot.tips = apply_rules(
                shot.metrics,
                shot.type,
                rules,
                self.options.get("age_group", "adult"),
                self.options.get("level", "competitive"),
            )
            rating = shot.technique.score
            if rating is not None:
                self.ratings.append(rating)
            self.counts[shot.type] += 1
            self.latest_shot = {
                **shot.model_dump(),
                "rating": rating,
                "experimental": not self.rules["coach_validated"],
            }
        processing_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "type": "frame",
            "pipeline_version": self.config["version"],
            "timestamp": timestamp,
            "width": width,
            "height": height,
            "poses": [p.model_dump() for p in poses],
            "ball": ball,
            "ball_trail": [b for b in self.balls if stamp - b["time"] < 0.5],
            "players_detected": len(poses),
            "shot_counts": dict(self.counts),
            "shots_total": sum(self.counts.values()),
            "latest_shot": self.latest_shot,
            "session_rating": round(sum(self.ratings) / len(self.ratings), 1) if self.ratings else None,
            "processing_ms": processing_ms,
            "reduce_workload": processing_ms > self.live_config["live_budget_ms"],
            "coach_validated": self.rules["coach_validated"],
            "classifier": "trained" if self.classifier else "heuristic",
            "status": "Tracking live" if poses else "Keep your full body in the camera view",
        }
