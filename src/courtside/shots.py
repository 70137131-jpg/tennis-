import math
from collections import defaultdict

import numpy as np

from courtside.schemas import PoseFrame, Shot, ShotType


def torso_length(pose: PoseFrame) -> float:
    points = pose.keypoints
    hip = np.array([(points[11].x + points[12].x) / 2, (points[11].y + points[12].y) / 2])
    shoulder = np.array([(points[5].x + points[6].x) / 2, (points[5].y + points[6].y) / 2])
    return max(1.0, float(np.linalg.norm(shoulder - hip)))


def relative_wrist(pose: PoseFrame, wrist: int) -> np.ndarray:
    points = pose.keypoints
    hip = np.array([(points[11].x + points[12].x) / 2, (points[11].y + points[12].y) / 2])
    return (np.array([points[wrist].x, points[wrist].y]) - hip) / torso_length(pose)


def segment_shots(
    poses: list[PoseFrame], duration: float, config: dict, handedness="right", calibration=None, balls=None
) -> list[Shot]:
    shots: list[Shot] = []
    wrist = 9 if handedness == "left" else 10
    shoulder = 5 if handedness == "left" else 6
    grouped: dict[tuple[str, int], list[PoseFrame]] = defaultdict(list)
    for pose in poses:
        if pose.time <= duration:
            grouped[(pose.player_id, pose.track_epoch)].append(pose)
    for player_id, epoch in sorted(grouped):
        sequence = sorted(grouped[(player_id, epoch)], key=lambda p: p.time)
        # A repeated timestamp carries no temporal evidence and must not form a peak.
        repeated = {p.time for a, p in zip(sequence, sequence[1:]) if p.time == a.time}
        sequence = [p for p in sequence if p.time not in repeated]
        speeds = [0.0]
        for a, b in zip(sequence, sequence[1:]):
            gap = b.time - a.time
            delta = np.linalg.norm(relative_wrist(b, wrist) - relative_wrist(a, wrist))
            confidence = min(p.keypoints[i].confidence for p in [a, b] for i in [5, 6, wrist, 11, 12])
            speeds.append(
                float(delta / gap)
                if (
                    0 < gap < 0.3
                    and confidence >= config["min_keypoint_confidence"]
                    and math.isfinite(delta / gap)
                    and delta / gap <= config.get("max_wrist_speed", 40)
                )
                else 0.0
            )
        last_contact = -10.0
        player_shots = 0
        for index in range(1, len(sequence) - 1):
            if player_shots >= config["max_shots"]:
                break
            current = sequence[index]
            if (
                speeds[index] < config["wrist_speed_threshold"]
                or speeds[index] < speeds[index - 1]
                or speeds[index] <= speeds[index + 1]
            ):
                continue
            if current.time - last_contact < config["min_shot_gap_seconds"]:
                continue
            points = current.keypoints
            confidence = min(points[i].confidence for i in [5, 6, wrist, 11, 12])
            if confidence < config["min_keypoint_confidence"] or torso_length(current) < 10:
                continue
            position = (
                calibration.position((points[15].x + points[16].x) / 2, max(points[15].y, points[16].y))
                if calibration
                and min(points[i].confidence for i in [15, 16]) >= config["min_keypoint_confidence"]
                else None
            )
            recent = [p for p in sequence[max(0, index - 12) : index + 1] if current.time - p.time <= 0.6]
            # Do not reuse overhead or swing evidence from before an observation gap.
            for offset in range(len(recent) - 1, 0, -1):
                if recent[offset].time - recent[offset - 1].time >= 0.3:
                    recent = recent[offset:]
                    break
            displacement = max(
                float(np.linalg.norm(relative_wrist(current, wrist) - relative_wrist(p, wrist)))
                for p in recent
                if min(p.keypoints[i].confidence for i in [5, 6, wrist, 11, 12])
                >= config["min_keypoint_confidence"]
            )
            if displacement < config.get("min_swing_displacement", 0.35):
                continue
            raised = any(
                p.keypoints[wrist].y < p.keypoints[0].y
                and min(p.keypoints[wrist].confidence, p.keypoints[0].confidence)
                >= config["min_keypoint_confidence"]
                for p in recent
            )
            evidence = ["Body-relative hitting-wrist speed peak"]
            shot_type: ShotType
            if raised:
                if position and min(abs(position[1]), abs(position[1] - 23.77)) > 4:
                    shot_type = "unknown"
                    evidence.append("Overhead swing away from the baseline; possible smash")
                else:
                    shot_type = "serve"
                    evidence.append("Overhead wrist motion; a serve and smash may look similar")
            elif (
                position
                and abs(position[1] - 11.885) < 4
                and displacement <= config.get("volley_max_swing_displacement", 1.8)
            ):
                shot_type = "volley"
                evidence.append("Compact wrist motion near the calibrated net")
            else:
                # Anatomical shoulder order handles a player facing toward or away from the camera.
                other_shoulder = 6 if handedness == "left" else 5
                shoulder_direction = (points[shoulder].x - points[other_shoulder].x) / torso_length(current)
                offset = relative_wrist(current, wrist)[0]
                margin = config.get("stroke_side_margin", 0.15)
                if abs(shoulder_direction) < margin or abs(offset) < margin:
                    shot_type = "unknown"
                    evidence.append("Wrist side or shoulder orientation is ambiguous")
                else:
                    shot_type = "forehand" if offset * shoulder_direction > 0 else "backhand"
                    evidence.append(
                        "Wrist on the hitting-arm side"
                        if shot_type == "forehand"
                        else "Wrist across the body from the hitting-arm side"
                    )
            shot_confidence = min(confidence, 0.78)
            if balls:
                nearby = [
                    b
                    for b in balls
                    if isinstance(b, dict)
                    and not b.get("interpolated", False)
                    and all(
                        type(b.get(k)) in (int, float) and math.isfinite(b[k])
                        for k in ["time", "x", "y", "confidence"]
                    )
                    and config["min_keypoint_confidence"] <= b["confidence"] <= 1
                    and abs(b["time"] - current.time) <= 0.2
                ]
                if nearby and min(
                    np.hypot(b["x"] - points[wrist].x, b["y"] - points[wrist].y) for b in nearby
                ) < config.get("ball_contact_radius_torso", 1.5) * torso_length(current):
                    shot_confidence = min(confidence, 0.88)
                    evidence.append("Ball candidate near the hitting wrist; contact is unconfirmed")
            shots.append(
                Shot(
                    id=f"shot-{len(shots) + 1:04d}",
                    player_id=player_id,
                    track_epoch=epoch,
                    type=shot_type,
                    start=max(0, current.time - config["clip_before_seconds"]),
                    contact=current.time,
                    end=min(duration, current.time + config["clip_after_seconds"]),
                    confidence=round(shot_confidence, 3),
                    classification_evidence=evidence,
                    court_position=position,
                )
            )
            last_contact = current.time
            player_shots += 1
    result = sorted(shots, key=lambda shot: (shot.contact, shot.player_id))[: config["max_shots"]]
    for index, shot in enumerate(result, 1):
        shot.id = f"shot-{index:04d}"
    return result
