import hashlib
from itertools import permutations
from pathlib import Path
from typing import Literal, cast

import cv2
import numpy as np

from courtside.readiness import OFFICIAL_POSE_SHA256
from courtside.schemas import Keypoint, PoseFrame

COCO_FROM_MEDIAPIPE = [0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
CONNECTIONS = [
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
]


class PoseEstimator:
    def __init__(self, model_path: Path):
        if not model_path.is_file():
            raise RuntimeError(
                "Pose model missing. Run: python data/download_model.py, then restart the worker."
            )
        if (
            model_path.name == "pose_landmarker_full.task"
            and hashlib.sha256(model_path.read_bytes()).hexdigest() != OFFICIAL_POSE_SHA256
        ):
            raise RuntimeError("Official pose model failed SHA256 verification; download it again")
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError("Install the vision extra: pip install -e '.[vision]'") from exc
        self.mp = mp
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=2,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )

    def detect(self, image: np.ndarray, timestamp: int) -> list[list[Keypoint]]:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        result = self.detector.detect_for_video(
            self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), timestamp
        )
        return [
            [
                Keypoint(
                    x=pose[i].x * image.shape[1],
                    y=pose[i].y * image.shape[0],
                    confidence=max(0.0, min(1.0, min(pose[i].visibility, pose[i].presence))),
                )
                for i in COCO_FROM_MEDIAPIPE
            ]
            for pose in result.pose_landmarks
        ]

    def close(self):
        self.detector.close()


class PlayerTracker:
    def __init__(self, alpha=0.45, max_gap=1.0):
        self.alpha, self.max_gap = alpha, max_gap
        self.tracks: dict[str, PoseFrame] = {}
        self.epochs: dict[str, int] = {}

    def update(
        self, detections: list[list[Keypoint]], frame: int, time: float, calibration=None
    ) -> list[PoseFrame]:
        self.tracks = {k: v for k, v in self.tracks.items() if 0 <= time - v.time <= self.max_gap}
        if not detections:
            return []
        detections = detections[:2]
        live = {k: v for k, v in self.tracks.items() if time - v.time <= self.max_gap}

        def center(points):
            return np.array([(points[11].x + points[12].x) / 2, (points[11].y + points[12].y) / 2])

        slots = ["near", "far"]
        if live:
            assignment = list(
                min(
                    permutations(slots, len(detections)),
                    key=lambda candidate: sum(
                        np.linalg.norm(center(points) - center(live[side].keypoints)) if side in live else 500
                        for points, side in zip(detections, candidate)
                    ),
                )
            )
        else:
            ordered = sorted(range(len(detections)), key=lambda i: center(detections[i])[1], reverse=True)
            assignment = [""] * len(detections)
            for rank, index in enumerate(ordered):
                assignment[index] = slots[rank]
            if calibration and len(detections) == 1:
                point = calibration.position(*center(detections[0]))
                assignment[0] = "near" if point and point[1] >= 11.885 else "far"
        result = []
        for points, side in zip(detections, assignment):
            old = live.get(side)
            if old:
                old_points = old.keypoints
                old_scale = max(
                    10.0,
                    float(
                        np.linalg.norm(
                            center(old_points)
                            - np.array(
                                [
                                    (old_points[5].x + old_points[6].x) / 2,
                                    (old_points[5].y + old_points[6].y) / 2,
                                ]
                            )
                        )
                    ),
                )
                new_scale = max(
                    10.0,
                    float(
                        np.linalg.norm(
                            center(points)
                            - np.array([(points[5].x + points[6].x) / 2, (points[5].y + points[6].y) / 2])
                        )
                    ),
                )
                if (
                    np.linalg.norm(center(points) - center(old_points)) > 2 * max(old_scale, new_scale)
                    or not 0.5 <= new_scale / old_scale <= 2
                ):
                    old = None
            if old is None:
                self.epochs[side] = self.epochs.get(side, -1) + 1
            if old:
                points = [
                    Keypoint(
                        x=self.alpha * new.x + (1 - self.alpha) * prev.x,
                        y=self.alpha * new.y + (1 - self.alpha) * prev.y,
                        confidence=new.confidence,
                    )
                    if new.confidence >= 0.5 and prev.confidence >= 0.5
                    else new
                    for new, prev in zip(points, old.keypoints)
                ]
            pose = PoseFrame(
                frame=frame,
                time=time,
                player_id=f"player-{side}",
                side=cast(Literal["near", "far"], side),
                track_epoch=self.epochs[side],
                keypoints=points,
            )
            self.tracks[side] = pose
            result.append(pose)
        return result


class BallTracker:
    def __init__(self, config: dict):
        self.lower = np.array(config["ball_hsv_lower"], dtype=np.uint8)
        self.upper = np.array(config["ball_hsv_upper"], dtype=np.uint8)
        self.previous: np.ndarray | None = None
        self.last: dict | None = None

    def update(self, image: np.ndarray, time: float) -> dict | None:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        color = cv2.inRange(hsv, self.lower, self.upper)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.previous is not None:
            motion = cv2.threshold(cv2.absdiff(gray, self.previous), 12, 255, cv2.THRESH_BINARY)[1]
            color = cv2.bitwise_and(color, cv2.dilate(motion, np.ones((3, 3), np.uint8)))
        self.previous = gray
        contours, _ = cv2.findContours(color, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if not 2 <= area <= 180:
                continue
            (x, y), radius = cv2.minEnclosingCircle(contour)
            if radius > 12 or radius < 1:
                continue
            circularity = min(1.0, area / (np.pi * radius**2))
            distance = (
                np.linalg.norm(np.array([x, y]) - np.array([self.last["x"], self.last["y"]]))
                if self.last and time - self.last["time"] < 0.3
                else 0
            )
            candidates.append((circularity - distance / image.shape[1], x, y, circularity))
        if not candidates:
            return None
        _, x, y, confidence = max(candidates)
        self.last = {
            "time": time,
            "x": float(x),
            "y": float(y),
            "confidence": round(confidence, 3),
            "interpolated": False,
        }
        return self.last.copy()


def interpolate_ball(samples: list[dict | None], times: list[float], max_gap: float) -> list[dict | None]:
    output = list(samples)
    known = [i for i, sample in enumerate(samples) if sample is not None]
    for left, right in zip(known, known[1:]):
        a, b = samples[left], samples[right]
        if a is None or b is None or times[right] - times[left] > max_gap:
            continue
        for index in range(left + 1, right):
            fraction = (times[index] - times[left]) / (times[right] - times[left])
            output[index] = {
                "time": times[index],
                "x": a["x"] + fraction * (b["x"] - a["x"]),
                "y": a["y"] + fraction * (b["y"] - a["y"]),
                "confidence": min(a["confidence"], b["confidence"]) * 0.7,
                "interpolated": True,
            }
    return output
